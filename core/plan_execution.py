"""Plan Runner — executes AdaptivePlanner plans against the tool registry (74).

Feature 74 matures from coordinator-only to executor: ``PlanRunner.run`` walks
the planned steps of an existing plan, dispatches each ``step["tool"]`` through
``tools.builder.get_registry().invoke`` (including the confirmation gate), marks
steps complete on real success, replans via ``replace_step`` using a step's
declared ``fallbacks`` when a step fails, and escalates when it cannot recover.
Interruptions from the wall-clock bound in ``core.lifecycle.BoundedOperation``
become honest failure events, never fake timeouts.

Nothing here invents capabilities: only existing registered tools are executed.
"""

from datetime import datetime

from core.kv import KeyValueStore
from core.lifecycle import BoundedOperation

_OK_STATUSES = {
    "ok", "done", "available", "complete", "executed", "armed",
    "learned", "replayed", "passed",
}

_BLOCKED_STATUSES = {"denied", "confirm_required", "blocked", "unavailable",
                     "invalid_argument", "not_configured", "authorization_required"}


class PlanRunner:

    def __init__(self, planner=None, registry=None, responder=None, kv=None):
        self.planner = planner
        self.responder = responder
        self.kv = kv or KeyValueStore("data/plan_execution.json")

        # ``registry`` may be injected (hermetic tests) or resolved lazily.
        self._registry = registry

    # ------------------------------------------------------------------
    def _registry_instance(self):
        if self._registry is not None:
            return self._registry
        from tools.builder import get_registry
        return get_registry()

    def _now(self):
        return datetime.now().isoformat()

    def _runs(self):
        return self.kv.get("runs", [])

    def _record_run(self, entry):
        runs = self.kv.get("runs", [])
        runs.append(entry)
        self.kv.set("runs", runs[-500:])

    def _escalations(self):
        return self.kv.get("escalations", [])

    def _record_escalation(self, entry):
        entries = self.kv.get("escalations", [])
        entries.append(entry)
        self.kv.set("escalations", entries[-100:])

    def _emit(self, plan_id, event_type, severity, payload):
        if self.responder is None or not hasattr(self.responder, "ingest"):
            return {"emitted": False, "reason": "no responder"}
        try:
            outcome = self.responder.ingest(
                source=f"plan:{plan_id}",
                event_type=event_type,
                severity=severity,
                payload=payload,
            )
            outcome["emitted"] = True
            return outcome
        except Exception as exc:
            return {"emitted": False, "reason": repr(exc)}

    # ------------------------------------------------------------------
    def _invoke_step(self, plan_id, tool_name, args, approve):
        """Run one tool through the registry with confirmation handling.

        High-risk steps are never auto-trusted: ``approve`` is the ONLY switch
        that mints and passes a pending confirmation request_id, matching the
        registry's gate contract (gate consumes the pending request).
        """
        registry = self._registry_instance()
        tool = registry.get(tool_name)
        if tool is None:
            return {"status": "error", "success": False,
                    "action": tool_name, "message": f"unknown tool '{tool_name}'"}
        if not approve and tool.confirm_required:
            return {"status": "confirm_required", "success": False,
                    "action": tool_name,
                    "message": f"{tool_name} requires confirmation"}
        if not tool.confirm_required:
            return registry.invoke(tool_name, **args)
        from core.confirmation import CONFIRMATION
        request_id = CONFIRMATION.require(f"plan:{plan_id}")
        return registry.invoke(tool_name, confirmed=True,
                               request_id=request_id, **args)

    def _is_ok(self, result):
        if not isinstance(result, dict):
            return False
        if result.get("success") is not True:
            return False
        status = str(result.get("status", "")).lower()
        if status in _BLOCKED_STATUSES:
            return False
        return True

    # ------------------------------------------------------------------
    def run(self, plan_id, approve=True, per_step_timeout=10, max_replans=2):
        """Execute the remaining planned steps of a plan.

        Only steps still in ``planned`` state are touched, so calling ``run``
        again after a restart (or after fixing a blocker) resumes exactly where
        the plan stopped — the restart-recovery behaviour of feature 74.
        """
        if self.planner is None:
            raise RuntimeError("PlanRunner needs a planner")
        plan = self.planner.get_plan(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        if plan.get("deprecated"):
            return {"plan_id": plan_id, "status": "deprecated",
                    "message": "plan deprecated; refusing to run"}

        replans_used = len(plan.get("replan_events", []))
        stop = False
        outcome = {"plan_id": plan_id, "status": plan["status"],
                   "steps": [], "confirm_required": False, "escalated": False}

        while not stop:
            touched = False
            for step in plan["steps"]:
                if step.get("status") != "planned":
                    continue
                ref = step["ref"]
                tool_name = str(step.get("tool") or step.get("action") or "").strip()
                args = dict(step.get("args") or {})
                entry = {"ref": ref, "tool": tool_name, "status": "planned"}

                # Steps prefixed with "@" are human/manual markers — the runner
                # NEVER dispatches them; they are recorded as blocked-review.
                if tool_name.startswith("@"):
                    entry.update({"status": "blocked", "manual": True,
                                  "message": "manual review required"})
                    outcome["steps"].append(entry)
                    outcome["escalated"] = True
                    self._record_run({"plan_id": plan_id, "at": self._now(),
                                      "step": ref, "tool": tool_name,
                                      "status": "blocked",
                                      "message": "manual review required"})
                    self._emit(plan_id, "plan.step_blocked", "high",
                               {"step": ref, "reason": "manual review required"})
                    stop = True
                    continue

                if not tool_name:
                    entry.update({"status": "blocked",
                                  "message": "step has no tool/action"})
                    self._record_run({"plan_id": plan_id, "at": self._now(),
                                      "step": ref, "tool": None,
                                      "status": "blocked",
                                      "message": "no tool/action"})
                    outcome["steps"].append(entry)
                    outcome["escalated"] = True
                    self._emit(plan_id, "plan.step_blocked", "medium",
                               {"step": ref, "reason": "no tool/action"})
                    stop = True
                    continue

                op, kind, value = BoundedOperation.run(
                    lambda name=tool_name, a=args: self._invoke_step(
                        plan_id, name, a, approve),
                    timeout=float(per_step_timeout))

                if kind == "interrupted":
                    result = {"status": "failed", "success": False,
                              "action": tool_name,
                              "message": f"step exceeded {per_step_timeout}s"}
                    t_kind = "timeout"
                elif kind == "error":
                    result = {"status": "failed", "success": False,
                              "action": tool_name, "message": str(value)}
                    t_kind = "failure"
                else:
                    result = value if isinstance(value, dict) else \
                        {"status": "ok", "success": True, "result": value}
                    t_kind = "failure" if not self._is_ok(result) else "ok"
                    if result.get("status") == "confirm_required":
                        t_kind = "confirm_required"

                if t_kind == "ok":
                    self.planner.complete_step(plan_id, ref)
                    entry.update({"status": "complete",
                                  "result_status": result.get("status")})
                    outcome["steps"].append(entry)
                    self._record_run({"plan_id": plan_id, "at": self._now(),
                                      "step": ref, "tool": tool_name,
                                      "status": "complete",
                                      "result_status": result.get("status")})
                    self._emit(plan_id, "plan.step_done", "low",
                               {"step": ref, "tool": tool_name,
                                "status": result.get("status")})
                    touched = True
                    continue

                if t_kind == "confirm_required":
                    entry.update({"status": "confirm_required"})
                    outcome["steps"].append(entry)
                    outcome["confirm_required"] = True
                    self._record_run({"plan_id": plan_id, "at": self._now(),
                                      "step": ref, "tool": tool_name,
                                      "status": "confirm_required"})
                    stop = True
                    continue

                # Real failure / timeout: try declared fallbacks, else escalate.
                fallbacks = list(step.get("fallbacks") or [])
                if fallbacks and replans_used < max_replans:
                    try:
                        self.planner.replace_step(plan_id, ref, fallbacks)
                    except ValueError as exc:
                        fallbacks = []
                        result["message"] = f"{result.get('message')}; {exc}"
                    if fallbacks:
                        replans_used += 1
                        entry.update({"status": "replanned",
                                      "message": result.get("message")})
                        outcome["steps"].append(entry)
                        self._record_run({"plan_id": plan_id,
                                          "at": self._now(), "step": ref,
                                          "tool": tool_name,
                                          "status": "replanned",
                                          "message": result.get("message")})
                        self._emit(plan_id, "plan.step_replanned", "medium",
                                   {"step": ref, "tool": tool_name,
                                    "reason": result.get("message")})
                        touched = True
                        continue

                if not fallbacks:
                    self.planner.replace_step(plan_id, ref,
                                              [{"action": "@manual_review",
                                                "args": {}}])
                entry.update({"status": "blocked", "escalated": True,
                              "message": result.get("message")})
                outcome["steps"].append(entry)
                outcome["escalated"] = True
                self._record_run({"plan_id": plan_id, "at": self._now(),
                                  "step": ref, "tool": tool_name,
                                  "status": "blocked",
                                  "message": result.get("message")})
                self._record_escalation({"plan_id": plan_id, "at": self._now(),
                                         "step": ref, "tool": tool_name,
                                         "reason": result.get("message")})
                self._emit(plan_id, "plan.step_blocked", "high",
                           {"step": ref, "tool": tool_name,
                            "reason": result.get("message")})
                stop = True

            if not touched:
                stop = True

        plan = self.planner.get_plan(plan_id)
        outcome["status"] = plan["status"]
        if outcome["escalated"]:
            outcome["message"] = "plan blocked; human review required"
        outcome["escalations"] = list(reversed(self._escalations()[-20:]))
        return outcome

    def resume(self, plan_id, **kwargs):
        """Re-run a plan — only remaining planned steps are processed now."""
        return self.run(plan_id, **kwargs)

    def history(self, limit=50):
        return list(reversed(self._runs()[-int(limit):]))

    def confirm_required_steps(self):
        """Steps of any running plan currently waiting on user confirmation."""
        found = []
        if self.planner is None:
            return found
        for plan in self.planner.list_plans():
            for step in plan["steps"]:
                if step.get("status") == "confirm_required":
                    found.append({"plan_id": plan["id"], "step": step["ref"],
                                  "tool": step.get("tool")})
        return found


__all__ = ["PlanRunner"]