"""Terminal Engine — the terminal-first command chain (features 51/58/89).

Bridges the existing ARVEN layers into one honest chain:

    USER REQUEST
    -> INTENT (keyword resolution over the registry's capabilities)
    -> PLAN / single tool
    -> AUTHORIZATION/CLASSIFICATION (core.safety + optional PermissionManager)
    -> CONFIRMATION (core.confirmation.CONFIRMATION; never auto-trusts)
    -> EXECUTION (tools.builder registry.invoke)
    -> RESULT
    -> STATE UPDATE (planner / missions)
    -> AUDIT / MEMORY / EVENT (per-layer, optional but provable)
    -> USER-VISIBLE RESULT (structured dict -> CLI)

No fabricated success: unknown intents return ``NO_MATCH``, gated tools return
``confirm_required`` unless approved, and every execution returns the registry's
honest wrapped result plus a ``chain`` trace of which layers participated.
"""

import re
import time
from datetime import datetime

from core.kv import KeyValueStore

_STOPWORDS = {
    "the", "a", "an", "please", "can", "you", "i", "me", "my", "could",
    "would", "will", "want", "need", "to", "for", "of", "and", "or", "on",
    "in", "with", "about", "how", "what", "show", "get", "give", "do",
    "let", "s", "t", "are", "is", "it", "that", "this", "now",
}

_STATUS_ORDER = ["AVAILABLE", "UNAVAILABLE", "OFFLINE", "REQUIRES_AUTH",
                 "REQUIRES_PERMISSION", "NOT_CONFIGURED", "FAILED"]


def _tokenise(text):
    words = [w for w in re.split(r"[^a-z0-9]+", str(text).lower()) if w]
    return [w for w in words if w not in _STOPWORDS]


class TerminalEngine:

    def __init__(self, registry=None, kv=None, planner=None, responder=None,
                 missions=None, memory=None, permissions=None,
                 principal="boss", undo=None):
        self.kv = kv or KeyValueStore("data/terminal_engine.json")
        self.principal = principal
        self._registry = registry
        self.planner = planner
        self.responder = responder
        self.missions = missions
        self.memory = memory
        self.permissions = permissions
        self.undo = undo

    # ------------------------------------------------------------------
    # dependencies
    # ------------------------------------------------------------------
    def _registry_instance(self):
        if self._registry is not None:
            return self._registry
        from tools.builder import get_registry
        return get_registry()

    def _now(self):
        return datetime.now().isoformat()

    # ------------------------------------------------------------------
    # intent resolution
    # ------------------------------------------------------------------
    def resolve_intent(self, request, top=5):
        """Resolve a free-form request to the best-matching registered tool.

        Scoring is honest and conservative:
        * a word inside a tool name is a full hit (+3), a plural stem is a
          partial hit (+2);
        * a candidate whose name/category covers EVERY meaningful request
          token earns a phrase bonus (+10);
        * an exact-tool-name match is decisive (+20);
        * requests with no full-token hit and no phrase coverage are NO_MATCH
          rather than a weak guess.
        """
        tokens = _tokenise(request)
        registry = self._registry_instance()
        if not tokens:
            return {"tool": None, "candidates": [],
                    "reason": "empty request"}

        def stem(word):
            return word[:-1] if len(word) > 3 and word.endswith("s") else word

        request_norm = "_".join(stem(t) for t in tokens)
        bucket = {}
        for name in registry.names():
            tool = registry.get(name)
            words = set(name.replace("-", "_").split("_"))
            words |= {w for w in str(tool.category).lower().split() if w}
            words |= {w for w in re.split(r"[^a-z0-9]+",
                                          str(tool.description).lower()) if w}
            full = 0
            covered = True
            score = 0
            for token in tokens:
                if token in words:
                    full += 1
                    score += 3
                elif any(token in w or stem(token) in w for w in words):
                    score += 2
                else:
                    covered = False
            if covered and (full or score):
                score += 10
            if name == request_norm:
                score += 20
            if score > 0:
                bucket[name] = score

        if not bucket:
            return {"tool": None, "candidates": [],
                    "reason": "no ARVEN capability matched your request"}
        ordered = sorted(bucket.items(), key=lambda item: (-item[1], item[0]))
        best_score = ordered[0][1]
        if best_score < 4:
            return {"tool": None, "candidates": [],
                    "reason": "request was too vague to map to a capability"}
        return {"tool": ordered[0][0],
                "candidates": [name for name, _ in ordered[:top]],
                "reason": f"{len(bucket)} capability keywords matched"}

    # ------------------------------------------------------------------
    # audit / memory / event hooks
    # ------------------------------------------------------------------
    def _audit(self):
        return self.kv.get("audit", [])

    def _record_audit(self, entry):
        audit = self.kv.get("audit", [])
        audit.append(entry)
        self.kv.set("audit", audit[-500:])

    def audit(self, limit=50):
        return list(reversed(self._audit()[-int(limit):]))

    def _classify(self, tool):
        from core.safety import SAFETY
        if tool is not None and hasattr(tool, "risk"):
            return tool.risk
        return SAFETY.risk_label(str(tool))

    def _infer_simple_args(self, request):
        """Fill an obvious single-argument param from the request tail.

        Conservative: only ``topic`` and ``target`` are inferred (single,
        last-meaningful-token semantics). Everything else must be passed
        explicitly — no fabrication of parameter values.
        """
        tool_name = self.resolve_intent(request).get("tool") or ""
        if not tool_name:
            return {}
        schema = self._registry_instance().describe(tool_name)
        if not isinstance(schema, dict) or "error" in schema:
            return {}
        required = {p["name"] for p in schema.get("parameters", [])
                    if p.get("required")}
        simple = {"topic", "target"}
        wanted = required & simple
        if not wanted:
            return {}
        tokens = _tokenise(request)
        if not tokens:
            return {}
        raw_words = [w for w in re.split(r"[^a-z0-9_]+", str(request).lower())
                     if w]
        tail = raw_words[-1] if raw_words else tokens[-1]
        return {name: tail for name in wanted}

    def _authorize(self, tool_name, principal):
        """Authorization check. Returns (allowed, note).

        Without a PermissionManager the engine inherits the registry gate
        (confirmation is the active boundary); with ``permissions`` configured
        an explicit grant for (scope=tool.category, action=invoke) is required.
        """
        if self.permissions is None:
            return True, "inherit: registry confirmation gate"
        tool = self._registry_instance().get(tool_name)
        scope = tool.category if tool is not None else tool_name
        allowed = self.permissions.check(scope, "invoke", principal)
        return bool(allowed), "permission_manager"

    def _remember(self, tool_name, result):
        if self.memory is None or not hasattr(self.memory, "add"):
            return {"stored": False, "reason": "memory engine not configured"}
        try:
            snippet = str(result.get("message") or result.get("status") or "")
            memory_id = self.memory.add(
                content=f"ARVEN executed {tool_name}: {snippet[:120]}",
                category="operations", importance=3,
                memory_type="log", value=None)
            return {"stored": True, "memory_id": memory_id}
        except Exception as exc:
            return {"stored": False, "reason": repr(exc)}

    def _emit_event(self, tool_name, severity, payload):
        if self.responder is None or not hasattr(self.responder, "ingest"):
            return {"emitted": False, "reason": "event responder not configured"}
        try:
            outcome = self.responder.ingest(
                source="terminal",
                event_type=f"terminal.{tool_name}",
                severity=severity, payload=payload)
            outcome["emitted"] = True
            return outcome
        except Exception as exc:
            return {"emitted": False, "reason": repr(exc)}

    # ------------------------------------------------------------------
    # single-intent execution  (the core chain)
    # ------------------------------------------------------------------
    def act(self, request, param=None, approve=False, principal=None):
        """Execute one user request through the full chain."""
        principal = principal or self.principal
        started = self._now()
        param = dict(param or {})
        param.update(self._infer_simple_args(request))
        chain = {
            "intent": None, "authorization": None, "confirmation": None,
            "execution": None, "memory": {"stored": False,
                                          "reason": "not attempted"},
            "event": {"emitted": False, "reason": "not attempted"},
            "audit": None, "plan": {"used": False}, "at": started,
        }

        intent = self.resolve_intent(request)
        chain["intent"] = intent
        if intent["tool"] is None:
            result = {
                "status": "NO_MATCH", "success": False, "action": request,
                "message": intent["reason"],
                "try": ["state a registered capability, e.g. 'plan list', "
                        "'diagnostics run', 'security scope list', "
                        "'backup list', 'perf report', 'event stats'"],
                "chain": chain,
            }
            return result

        tool_name = intent["tool"]
        registry = self._registry_instance()
        tool = registry.get(tool_name)

        allowed, auth_note = self._authorize(tool_name, principal)
        chain["authorization"] = {"allowed": allowed, "mode": auth_note}
        if not allowed:
            result = {"status": "REQUIRES_PERMISSION", "success": False,
                      "action": tool_name,
                      "message": f"{principal} is not authorized to invoke "
                                 f"'{tool_name}' in the configured scope",
                      "chain": chain}
            chain["audit"] = self._record_au(result, principal, started)
            return result

        risk = self._classify(tool)
        chain["confirmation"] = {"risk": risk,
                                 "confirm_required": bool(tool.confirm_required),
                                 "approved": False}
        if tool.confirm_required and not approve:
            from core.confirmation import CONFIRMATION
            request_id = CONFIRMATION.require(f"terminal:{tool_name}")
            chain["confirmation"]["request_id"] = request_id
            result = {
                "status": "confirm_required", "success": False,
                "action": tool_name,
                "message": f"{tool_name} requires confirmation — re-run with "
                           f"approve=True (or answer '{request_id}')",
                "request_id": request_id, "chain": chain,
            }
            chain["audit"] = self._record_au(result, principal, started)
            return result

        missing = [p["name"] for p in tool.schema()["parameters"]
                   if p.get("required") and p["name"] not in param]
        if missing:
            result = {"status": "invalid_argument", "success": False,
                      "action": tool_name,
                      "message": f"missing required argument(s): {missing}",
                      "chain": chain}
            chain["audit"] = self._record_au(result, principal, started)
            return result

        # EXECUTE — gated via the registry when confirmation is required.
        if tool.confirm_required:
            from core.confirmation import CONFIRMATION
            request_id = CONFIRMATION.require(f"terminal:{tool_name}")
            chain["confirmation"]["approved"] = True
            chain["confirmation"]["request_id"] = request_id
            result = registry.invoke(tool_name, confirmed=True,
                                     request_id=request_id, **param)
        else:
            result = registry.invoke(tool_name, **param)
        chain["execution"] = {"tool": tool_name, "risk": risk,
                              "status": result.get("status")}

        severity = "low" if result.get("success") is True else "high"
        event = self._emit_event(tool_name, severity,
                                 {"status": result.get("status")})
        chain["event"] = event
        chain["memory"] = self._remember(tool_name, result)
        chain["audit"] = self._record_au(result, principal, started)

        result = dict(result)
        result["chain"] = chain
        return result

    def _record_au(self, result, principal, at):
        entry = {"principal": principal, "action": result.get("action"),
                 "status": result.get("status"), "at": at}
        self._record_audit(entry)
        return entry

    def answer(self, request_id, verdict):
        """Resolve a pending confirmation from free text ('yes'/'no')."""
        from core.confirmation import CONFIRMATION
        ok, message = CONFIRMATION.resolve(request_id, verdict)
        self._record_audit({"principal": self.principal,
                            "action": "confirmation.answer",
                            "status": "ok" if ok else "no",
                            "request_id": request_id, "at": self._now(),
                            "message": message})
        return {"ok": ok, "message": message, "request_id": request_id}

    # ------------------------------------------------------------------
    # mission execution with gated tool dispatch  (features 50/54)
    # ------------------------------------------------------------------
    def mission(self, title, steps, approve=False, step_timeout=10.0,
                mission_id=None):
        """Create + supervise a mission whose tool steps run through the gate.

        A step dict may carry ``tool`` and ``args``; the dispatcher routes it
        through ``registry.invoke`` (honouring CONFIRMATION when required) and
        RAISES on a failed result so ``run_step`` records STEP_FAILED rather
        than a dishonestly DONE step.
        """
        if self.missions is None:
            return {"status": "error", "success": False,
                    "message": "missions engine not configured"}
        registry = self._registry_instance()
        from core.confirmation import CONFIRMATION

        def dispatcher(step):
            def _run():
                tool_name = str(step.get("tool") or "").strip()
                args = dict(step.get("args") or {})
                if not tool_name:
                    raise RuntimeError("step has no tool")
                tool = registry.get(tool_name)
                if tool is None:
                    raise RuntimeError(f"unknown tool '{tool_name}'")
                if tool.confirm_required:
                    if not approve:
                        raise PermissionError(
                            f"{tool_name} requires confirmation")
                    request_id = CONFIRMATION.require(f"mission:{tool_name}")
                    result = registry.invoke(tool_name, confirmed=True,
                                             request_id=request_id, **args)
                else:
                    result = registry.invoke(tool_name, **args)
                if not isinstance(result, dict) or result.get("success") is not True:
                    raise RuntimeError(
                        str(result.get("message") or result.get("status")
                            or "step failed"))
                return result
            return _run

        mid = str(mission_id) if mission_id else f"m3_{time.time_ns()}"
        created = self.missions.create_mission(
            title, steps, mission_id=mid)
        normalized = self.missions.steps(mid)
        step_records = []
        for index, raw in enumerate(steps):
            step = normalized[index] if index < len(normalized) else raw
            step_id = step["id"]
            record = {"id": step_id, "title": step.get("title"),
                      "status": "running"}
            if str(raw.get("tool") or "").strip():
                try:
                    outcome = self.missions.run_step(
                        mid, step_id, fn=dispatcher(raw),
                        timeout=step_timeout)
                    record["status"] = outcome.get("status")
                    if outcome.get("status") == "done":
                        record["result_status"] = "ok"
                except Exception as exc:
                    record["status"] = "failed"
                    record["error"] = repr(exc)
            else:
                record["status"] = "done" if step.get("status") == "done" \
                    else "open"
            step_records.append(record)
            self._emit_event(f"mission.{mid}", "low",
                             {"step": step_id, "status": record["status"]})

        summary = self.missions.summary(mid)
        all_done = all(r["status"] == "done" for r in step_records)
        mission_status = None
        if all_done:
            try:
                self.missions.finish(mid)
                mission_status = "completed"
            except ValueError:
                mission_status = summary["status"]
        else:
            mission_status = summary["status"]

        result = {
            "status": "COMPLETE" if all_done else summary["status"],
            "success": all_done,
            "mission_id": mid,
            "mission_status": mission_status,
            "steps": step_records,
            "summary": summary,
        }
        self._record_audit({"principal": self.principal, "action": "mission",
                            "mission_id": mid, "status": mission_status,
                            "at": self._now()})
        return result

    # ------------------------------------------------------------------
    # rollup
    # ------------------------------------------------------------------
    def status(self):
        registry = self._registry_instance()
        info = {
            "registry_tools": len(registry.names()),
            "categories": registry.categories(),
            "plans": len(self.planner.list_plans()) if self.planner else None,
            "missions": (len(self.missions.list_missions())
                         if self.missions else None),
        }
        if self.responder is not None and hasattr(self.responder, "stats"):
            info["events"] = self.responder.stats()
        return info

    def health(self):
        from core.providers.registry import providers_registry
        rows = providers_registry.status_all()
        statuses = [r.get("status") for r in rows
                    if r.get("status") in _STATUS_ORDER]
        worst = min(statuses, key=_STATUS_ORDER.index) if statuses \
            else "AVAILABLE"
        return {
            "provider_statuses": {r.get("name"): r.get("status")
                                  for r in rows},
            "worst_status": worst,
            "registry_tools": len(self._registry_instance().names()),
        }


__all__ = ["TerminalEngine"]