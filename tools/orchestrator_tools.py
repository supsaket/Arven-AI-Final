"""Feature 111 tools — mission orchestration surface (terminal-first).

``orchestrate`` is HIGH risk: the registry gate demands pending confirmation
before any dispatch. Everything below it stays bounded (step timeouts) and
reports failures honestly.
"""

from functools import lru_cache

from tools.day2_tools import _safe

_orch_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _orch_tools.append(spec)


@lru_cache(maxsize=1)
def _engine_orch():
    from core.mission_orchestrator import MissionOrchestrator
    return MissionOrchestrator()


def _orchestrate(**kw):
    goal = str(kw.get("goal") or "").strip()
    if not goal:
        return {"success": False, "status": "invalid_argument",
                "message": "goal is empty"}
    steps = kw.get("steps")
    return _engine_orch().run(goal, steps,
                              approve=bool(kw.get("approve", False)),
                              step_timeout=float(kw.get("step_timeout", 10.0)))


def _orchestrator_status(**kw):
    return _engine_orch().status()


def _orchestrator_plan(**kw):
    goal = str(kw.get("goal") or "").strip()
    steps = kw.get("steps")
    try:
        return _engine_orch().create(goal, steps)
    except ValueError as exc:
        return {"success": False, "status": "invalid_argument",
                "message": str(exc)}


def _orchestrator_resume(**kw):
    mission_id = str(kw.get("mission_id") or "").strip()
    if not mission_id:
        return {"success": False, "status": "invalid_argument",
                "message": "mission_id is empty"}
    return _engine_orch().resume(
        mission_id, approve=bool(kw.get("approve", False)),
        step_timeout=float(kw.get("step_timeout", 10.0)))


def _orchestrator_cancel(**kw):
    mission_id = str(kw.get("mission_id") or "").strip()
    if not mission_id:
        return {"success": False, "status": "invalid_argument",
                "message": "mission_id is empty"}
    return _engine_orch().cancel(mission_id)


def _orchestrator_report(**kw):
    mission_id = str(kw.get("mission_id") or "").strip()
    if not mission_id:
        return {"success": False, "status": "invalid_argument",
                "message": "mission_id is empty"}
    return _engine_orch().report(mission_id)


def _orchestrator_capable(**kw):
    return _engine_orch().capable(kw.get("goal"))


# --- Feature 111 ----------------------------------------------------------
_add("orchestrate", "high", "orchestrator",
     "Run a supervised goal mission through the gated registry",
     [("goal", True, "the goal"),
      ("steps", False, "'do X; do Y' or explicit tool steps"),
      ("approve", False, "bool"), ("step_timeout", False, "float seconds")],
     _orchestrate)
_add("orchestrator_status", "low", "orchestrator",
     "Orchestrator status: missions, plans, confirmations, escalations",
     [], _orchestrator_status)
_add("orchestrator_plan", "medium", "orchestrator",
     "Create a plan+mission binding for a goal (no execution)",
     [("goal", True, ""), ("steps", False, "step list/text")],
     _orchestrator_plan)
_add("orchestrator_resume", "high", "orchestrator",
     "Resume a paused orchestration (executes remaining open steps)",
     [("mission_id", True, ""), ("approve", False, "bool"),
      ("step_timeout", False, "float seconds")], _orchestrator_resume)
_add("orchestrator_cancel", "medium", "orchestrator",
     "Cancel an orchestration (audited, non-destructive)",
     [("mission_id", True, "")], _orchestrator_cancel)
_add("orchestrator_report", "low", "orchestrator",
     "Export a mission report markdown artifact",
     [("mission_id", True, "")], _orchestrator_report)
_add("orchestrator_capable", "low", "orchestrator",
     "Honest check of which regulated tools cover a goal",
     [("goal", True, "")], _orchestrator_capable)


TOOLS = _orch_tools

__all__ = ["TOOLS"]