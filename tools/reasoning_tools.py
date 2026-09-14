"""Feature 114 tools — dynamic reasoning control surface (terminal-first).

Estimate the recommended effort for a task, set the active level (manual,
mission-bound or mid-mission), and inspect the honest provider cap.
"""

from functools import lru_cache

from tools.day2_tools import _safe

_reasoning_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _reasoning_tools.append(spec)


@lru_cache(maxsize=1)
def _engine():
    from core.reasoning_control import ReasoningControl
    return ReasoningControl()


def _reasoning_estimate(**kw):
    text = kw.get("text")
    if not text or not str(text).strip():
        return {"success": False, "status": "invalid_argument",
                "message": "text is empty"}
    return _engine().estimate(str(text))


def _reasoning_set(**kw):
    level = kw.get("level")
    mission_id = kw.get("mission_id")
    return _engine().set_level(
        level, source=str(kw.get("source") or "manual").strip(),
        mission_id=mission_id, note=str(kw.get("note") or ""))


def _reasoning_status(**kw):
    mission_id = kw.get("mission_id")
    return _engine().status(mission_id=mission_id)


# --- Feature 114 ----------------------------------------------------------
_add("reasoning_estimate", "low", "reasoning",
     "Recommend a reasoning effort level for a task (deterministic heuristic)",
     [("text", True, "the task/request text")], _reasoning_estimate)
_add("reasoning_set", "medium", "reasoning",
     "Set the active reasoning level (auto|manual|mission|mid_mission)",
     [("level", True, "LOW|MEDIUM|HIGH|XHIGH|MAX"),
      ("source", False, "auto | manual | mission | mid_mission"),
      ("mission_id", False, "bind the override to a mission"),
      ("note", False, "free-form rationale")],
     _reasoning_set)
_add("reasoning_status", "low", "reasoning",
     "Configured vs provider-supported reasoning level (honest cap)",
     [("mission_id", False, "optional mission-specific view")],
     _reasoning_status)


TOOLS = _reasoning_tools

__all__ = ["TOOLS"]