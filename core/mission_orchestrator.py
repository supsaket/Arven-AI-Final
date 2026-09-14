"""Feature 111 — Advanced Autonomous Command & Mission Orchestration.

Bridges the existing ARVEN layers into one supervised command surface:

* planning (``core.planner.AdaptivePlanner``) creates the tracking plan
* missions (``core.missions.MissionsEngine``) supervise execution with the
  real step state machine and restart recovery
* dispatch runs through ``tools.builder`` registry (CONFIRMATION-aware); a
  step whose tool is unknown or requires confirmation is never fabricated
* ``resume`` only advances open steps; ``cancel`` is audited and
  non-destructive; escalation exists via plan blocking + mission audit

Everything is bounded: steps run inside ``BoundedOperation`` timeouts, and
the orchestrator never loops on its own — a blocked step surfaces honestly.
"""

import copy
import time

from core.kv import KeyValueStore
from core.output import OutputManager

_DEFAULT_KV = "data/orchestrator.json"
_DEFAULT_REPORT_DIR = "Output/orchestrator"


def _steps_from_list(steps):
    """Normalise free-form steps into mission step dicts.

    Strings may be plain narrative ('write the summary') or tool-bearing
    ('run diagnostics_run'); dicts pass through with title/tool/args.
    """
    if isinstance(steps, str):
        parts = steps.replace(";", "\n").split("\n")
        return [s.strip() for s in parts if s.strip()], False
    if isinstance(steps, (list, tuple)):
        out = []
        for raw in steps:
            if isinstance(raw, str):
                out.append(raw.strip() and raw)
            else:
                out.append(raw)
        return [s for s in out if s], True
    return [], False


class MissionOrchestrator:
    """Orchestrate goals into supervised, gated, persistent missions."""

    def __init__(self, kv_path=None, planner=None, runner=None, missions=None,
                 terminal=None, registry=None, report_dir=None, steering=None):
        self.path = str(kv_path) if kv_path else _DEFAULT_KV
        self.report_dir = str(report_dir) if report_dir else \
            _DEFAULT_REPORT_DIR
        self.store = KeyValueStore(self.path)
        self.output = OutputManager()
        self.planner = planner
        self.runner = runner
        self.missions = missions
        self.terminal = terminal
        self._registry = registry
        self.steering = steering  # feature 113 mid-turn hook (optional)

    # ------------------------------------------------------------------
    # dependencies
    # ------------------------------------------------------------------
    def _registry_instance(self):
        if self._registry is not None:
            return self._registry
        from tools.builder import get_registry
        return get_registry()

    def _planner_instance(self):
        if self.planner is not None:
            return self.planner
        from core.planner import AdaptivePlanner
        return AdaptivePlanner()

    def _missions_instance(self):
        if self.missions is not None:
            return self.missions
        from core.missions import MissionsEngine
        return MissionsEngine()

    def _terminal_instance(self):
        if self.terminal is not None:
            return self.terminal
        from core.terminal_engine import TerminalEngine
        return TerminalEngine()

    def _records(self):
        return dict(self.store.get("orchestrations") or {})

    def _save_record(self, record):
        records = self._records()
        records[record["mission_id"]] = record
        self.store.set("orchestrations", records)
        return record

    # ------------------------------------------------------------------
    # capability gate
    # ------------------------------------------------------------------
    def capable(self, goal):
        """Honest check: which registered tools could cover this goal?"""
        if not str(goal or "").strip():
            return {"supported": False, "tools": [],
                    "reason": "empty goal"}
        import re
        tokens = [t for t in re.split(r"[^a-z0-9]+", str(goal).lower()) if t]
        registry = self._registry_instance()
        matched = set()
        for token in tokens:
            if len(token) < 3:
                continue
            for name in registry.find(token):
                matched.add(name)
        return {
            "supported": bool(matched),
            "tools": sorted(matched)[:20],
            "token_count": len(tokens),
            "reason": f"{len(matched)} registry tools cover the goal"
                      if matched else
                      "no registered tool matched any goal keyword — "
                      "the goal needs explicit tool steps or delegation",
        }

    # ------------------------------------------------------------------
    # create / run
    # ------------------------------------------------------------------
    def create(self, goal, steps):
        """Create a plan + mission binding for a goal. No execution."""
        if not str(goal or "").strip():
            raise ValueError("orchestration goal must be non-empty")
        raw_steps, _graceful = _steps_from_list(steps)
        resolved = self._resolve_steps(raw_steps)
        if not resolved:
            raise ValueError("orchestration needs at least one step")

        planner = self._planner_instance()
        missions = self._missions_instance()
        plan = planner.create_plan(
            goal, [s["title"] if s.get("tool") is None
                   else {"tool": s["tool"], "args": s.get("args", {}),
                         "action": s["title"]}
                   for s in resolved])
        mission = missions.create_mission(
            goal, [{"title": s["title"], "tool": s.get("tool"),
                    "args": s.get("args", {}) or None}
                   for s in resolved])
        record = self._save_record({
            "goal": str(goal),
            "plan_id": plan["id"],
            "mission_id": mission["id"],
            "created_at": time.time(),
            "report_path": None,
            "steps": [{k: s[k] for k in ("title", "tool", "args")
                       if k in s} for s in resolved],
        })
        return {
            "success": True,
            "status": "ok",
            "goal": str(goal),
            "plan_id": plan["id"],
            "mission_id": mission["id"],
            "steps": [s.get("title") for s in resolved],
            "tool_steps": [s.get("tool") for s in resolved
                           if s.get("tool")],
            "resolved_steps": record["steps"],
            "record": record,
        }

    def _resolve_steps(self, raw_steps):
        """Map each narrative step to a registered tool when one exists.

        A step resolves to ``tool=None`` when no registered tool matches —
        it is kept as a planning-only step (never fabricated into an action).
        """
        resolver = self._terminal_instance()
        registry = self._registry_instance()
        resolved = []
        for raw in raw_steps:
            if isinstance(raw, dict):
                title = str(raw.get("title") or raw.get("text") or "").strip()
                tool = str(raw.get("tool") or "").strip() or None
                args = dict(raw.get("args") or {})
                if tool and registry.get(tool) is None:
                    tool = None
                    args = {}
            else:
                title = str(raw or "").strip()
                tool, args = None, {}
                if title:
                    try:
                        intent = resolver.resolve_intent(title)
                    except Exception:
                        intent = {"tool": None}
                    if intent.get("tool"):
                        tool = intent["tool"]
                        try:
                            args = resolver._infer_simple_args(title)
                        except Exception:
                            args = {}
            if not title:
                continue
            resolved.append({"title": title, "tool": tool, "args": args})
        return resolved

    # ------------------------------------------------------------------
    # run / resume via the terminal mission chain (gated dispatch)
    # ------------------------------------------------------------------
    def _dispatch_step(self, step, approve):
        """Gated dispatch for one mission step (used by run/resume).

        Mirrors ``TerminalEngine.mission`` semantics: a failed result raises
        so ``MissionsEngine.run_step`` records STEP_FAILED — never a fake DONE.
        """
        tool_name = str(step.get("tool") or "").strip()
        if not tool_name:
            return {"status": "skipped", "success": False,
                    "action": step.get("title"),
                    "message": "planning-only step (no tool resolved)"}
        registry = self._registry_instance()
        tool = registry.get(tool_name)
        if tool is None:
            raise RuntimeError(f"unknown tool '{tool_name}'")
        args = dict(step.get("args") or {})
        from core.confirmation import CONFIRMATION
        if tool.confirm_required:
            if not approve:
                raise PermissionError(
                    f"{tool_name} requires confirmation")
            request_id = CONFIRMATION.require(f"orchestrator:{tool_name}")
            result = registry.invoke(tool_name, confirmed=True,
                                     request_id=request_id, **args)
        else:
            result = registry.invoke(tool_name, **args)
        if not isinstance(result, dict) or result.get("success") is not True:
            raise RuntimeError(
                str(result.get("message") or result.get("status")
                    or "step failed"))
        return result

    def _execute_steps(self, mission_id, raw_steps, approve, step_timeout):
        """Run raw (tool-bearing) steps through the mission state machine.

        raw_steps map 1:1 onto the mission's normalized steps by index.
        Steps without a tool are planning-only and remain open (honest).
        """
        missions = self._missions_instance()
        normalized = missions.steps(mission_id)
        step_records = []
        for index, raw in enumerate(raw_steps):
            step = normalized[index] if index < len(normalized) else raw
            record = {"id": step["id"], "title": step.get("title"),
                      "status": "open"}
            record.update({"step": step["id"]})
            if str(raw.get("tool") or "").strip():
                try:
                    outcome = missions.run_step(
                        mission_id, step["id"],
                        fn=lambda s=raw: self._dispatch_step(s, approve),
                        timeout=float(step_timeout))
                    record["status"] = outcome.get("status")
                    if outcome.get("status") == "done":
                        record["tool"] = raw["tool"]
                        record["result_status"] = \
                            (outcome.get("result") or {}).get("status", "ok")
                except Exception as exc:
                    record["status"] = "failed"
                    record["error"] = repr(exc)
            else:
                record["note"] = "planning-only step"
            step_records.append(record)
            # Feature 113: mid-turn steering checkpoint between steps.
            if self.steering is not None and record["status"] != "failed":
                checkpoint = self.steering.checkpoint(mission_id)
                if checkpoint.get("halt"):
                    record["note"] = (record.get("note", "") + " "
                                      "mission halted by mid-turn steering "
                                      f"[{','.join(checkpoint['applied'])}]"
                                      ).strip()
                    break
        return step_records

    def run(self, goal, steps, approve=False, step_timeout=10.0):
        """Create and execute an orchestration. Bounded and gated."""
        try:
            created = self.create(goal, steps)
        except ValueError as exc:
            return {"success": False, "status": "invalid_argument",
                    "message": str(exc)}
        mission_id = created["mission_id"]
        missions = self._missions_instance()
        step_records = self._execute_steps(
            mission_id, created["resolved_steps"], approve, step_timeout)
        summary = missions.summary(mission_id)
        all_done = all(r["status"] == "done" for r in step_records)
        mission_status = summary["status"]
        if all_done:
            try:
                missions.finish(mission_id)
                mission_status = "completed"
            except ValueError:
                mission_status = summary["status"]
        created["status"] = "COMPLETE" if all_done else mission_status
        created["step_records"] = step_records
        created["summary"] = summary
        return created

    def resume(self, mission_id, approve=False, step_timeout=10.0):
        """Resume a paused orchestration: advance only open/broken steps."""
        missions = self._missions_instance()
        try:
            current = missions.get_mission(mission_id)
        except KeyError as exc:
            return {"success": False, "status": "invalid_argument",
                    "message": str(exc), "mission_id": mission_id}
        if current["status"] in ("completed", "failed", "archived"):
            return {"success": False, "status": "ok",
                    "message": f"mission is {current['status']}; nothing to "
                               "resume", "mission_id": mission_id}
        try:
            missions.resume(mission_id, reason="orchestrator.resume")
        except ValueError:
            pass  # already active — nothing to flip

        records = self._records()
        record = records.get(str(mission_id))
        raw_steps = (record or {}).get("steps") or []
        if not raw_steps:
            normalized = missions.steps(mission_id)
            raw_steps = [{"title": s.get("title"), "tool": None, "args": {}}
                         for s in normalized]
        summary = missions.summary(mission_id)
        if not raw_steps or all(
                m["status"] == "done" for m in missions.steps(mission_id)):
            all_done = all(m["status"] == "done"
                           for m in missions.steps(mission_id))
            return {"success": all_done,
                    "status": "COMPLETE" if all_done else summary["status"],
                    "mission_id": mission_id, "processed_steps": [],
                    "summary": summary, "pending_remaining": False}
        step_records = self._execute_steps(
            mission_id, raw_steps, approve, step_timeout)
        all_done = all(m["status"] == "done"
                       for m in missions.steps(mission_id))
        return {"success": all_done, "status": "COMPLETE" if all_done
                else summary["status"], "mission_id": mission_id,
                "processed_steps": step_records, "summary": summary,
                "pending_remaining": not all_done}

    def cancel(self, mission_id, reason="cancelled by orchestrator"):
        missions = self._missions_instance()
        try:
            missions.cancel(mission_id, reason=reason)
        except (KeyError, ValueError) as exc:
            return {"success": False, "status": "invalid_argument",
                    "message": str(exc), "mission_id": mission_id}
        records = self._records()
        record = records.get(str(mission_id))
        if record is not None and record.get("plan_id"):
            try:
                self._planner_instance().deprecate(record["plan_id"])
            except KeyError:
                pass
        return {"success": True, "status": "ok",
                "message": f"mission {mission_id} cancelled (audited, "
                           "non-destructive)", "mission_id": mission_id}

    # ------------------------------------------------------------------
    # status / report
    # ------------------------------------------------------------------
    def status(self):
        missions = self._missions_instance()
        planner = self._planner_instance()
        records = self._records()
        try:
            plans = planner.list_plans()
        except Exception:
            plans = []
        confirm_steps = []
        escalations = []
        if self.runner is not None:
            try:
                confirm_steps = self.runner.confirm_required_steps()
            except Exception:
                confirm_steps = []
            try:
                escalations = list(self.runner.kv.get("escalations", [])
                                   or [])[-20:]
            except Exception:
                escalations = []
        return {
            "orchestrations": len(records),
            "active_missions": len(missions.list_missions("active")),
            "paused_missions": len(missions.list_missions("paused")),
            "blocked_missions": len(missions.list_missions("blocked")),
            "plans": len(plans),
            "confirm_required_steps": len(confirm_steps),
            "confirm_required_detail": confirm_steps[-10:],
            "escalations": list(reversed(escalations)),
            "registry_tools": len(self._registry_instance().names()),
        }

    def report(self, mission_id):
        missions = self._missions_instance()
        try:
            mission = missions.get_mission(mission_id)
            summary = missions.summary(mission_id)
            audit = missions.audit(mission_id)
        except KeyError as exc:
            return {"success": False, "status": "invalid_argument",
                    "message": str(exc), "mission_id": mission_id}
        records = self._records()
        record = records.get(str(mission_id)) or {}
        lines = [
            "# ARVEN Orchestration Report",
            "",
            f"- mission: `{mission_id}`",
            f"- goal: {mission['title']}",
            f"- status: {mission['status']}",
            f"- progress: {summary['progress_pct']}% "
            f"({summary['steps_done']}/{summary['steps_total']})",
            "",
            "## Steps",
            "",
        ]
        for step in mission["steps"]:
            tool = step.get("tool")
            lines.append(
                f"- `{step['id']}` [{step['status']}] {step['title']}"
                + (f" -> `{tool}`" if tool else " (planning only)"))
        lines += ["", "## Audit", ""]
        for entry in audit[-20:]:
            lines.append(f"- {entry.get('event')} ({entry.get('detail')})")
        lines += ["", "## Evidence", "",
                  f"- mission summary: {summary_tab(summary)}",
                  f"- plan id: {record.get('plan_id') or 'n/a'}",
                  ""]
        body = "\n".join(lines).rstrip() + "\n"
        try:
            written = self.output.write(
                self.report_dir, f"{mission_id}.md", body,
                metadata={"type": "ARVEN_ORCHESTRATOR_REPORT",
                          "mission_id": mission_id,
                          "goal": mission["title"]})
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"report write failed: {exc}"}
        if record:
            record["report_path"] = written["path"]
            self._save_record(record)
        return {"success": True, "status": "ok",
                "message": f"report written: {written['path']}",
                "mission_id": mission_id, "path": written["path"],
                "sidecar": written["sidecar"], "summary": summary}


def summary_tab(summary):
    parts = [f"{summary['steps_done']}/{summary['steps_total']}",
             summary["status"]]
    return " ; ".join(parts)


mission_orchestrator = MissionOrchestrator()

__all__ = [
    "MissionOrchestrator",
    "mission_orchestrator",
    "_steps_from_list",
]