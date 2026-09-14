"""Feature 113 tools — mid-turn mission steering surface (terminal-first).

One tool steers a live mission (classified + applied), the others expose the
queue and history. Failure states are honest (unknown classification, terminal
missions, missing missions are never guessed around).
"""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_list

_steer_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _steer_tools.append(spec)


@lru_cache(maxsize=1)
def _engine():
    from core.mission_steering import MissionSteering
    return MissionSteering()


def _steer_mission(**kw):
    mission_id = str(kw.get("mission_id") or "").strip()
    instruction = kw.get("instruction")
    options = {}
    if kw.get("title"):
        options["title"] = kw["title"]
    if kw.get("steps") is not None:
        options["steps"] = _parse_list(kw["steps"])
    if kw.get("detail"):
        options["detail"] = kw["detail"]
    if not instruction or not str(instruction).strip():
        return {"success": False, "status": "invalid_argument",
                "message": "instruction is empty"}
    return _engine().apply(instruction, mission_id, options=options)


def _steering_queue(**kw):
    mission_id = kw.get("mission_id")
    return _engine().history(mission_id=str(mission_id).strip()
                             if mission_id else None)


def _steering_status(**kw):
    return _engine().status()


# --- Feature 113 ----------------------------------------------------------
_add("steer_mission", "medium", "steering",
     "Classify and apply a mid-turn steering instruction to a live mission "
     "(pause/resume/cancel/extend/redirect/modify/query)",
     [("instruction", True, "what the operator wants to change"),
      ("mission_id", False, "target mission"),
      ("title", False, "redirect target title/goal"),
      ("steps", False, "steps to append for kind=extend"),
      ("detail", False, "modify directive detail")],
     _steer_mission)
_add("steering_queue", "low", "steering",
     "Pending/applied steering events (optionally per mission)",
     [("mission_id", False, "optional mission filter")], _steering_queue)
_add("steering_status", "low", "steering",
     "Steering engine summary: events by kind, unknowns pending review",
     [], _steering_status)


TOOLS = _steer_tools

__all__ = ["TOOLS"]