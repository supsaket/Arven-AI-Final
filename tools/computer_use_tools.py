"""Feature 115 tools — professional computer use surface (terminal-first).

Expose the engine read-only primitives (status/windows/screenshot/verify) as
LOW, and every real input action as HIGH (confirmation-gated). ``dry_run``
defaults are available so operators and tests can plan without sending input.
"""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_list

_cu_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _cu_tools.append(spec)


@lru_cache(maxsize=1)
def _engine():
    from core.computer_use_engine import ComputerUseEngine
    return ComputerUseEngine()


def _cu_status(**kw):
    return _engine().status()


def _cu_observe(**kw):
    kind = str(kw.get("kind") or "windows").strip()
    if kind == "windows":
        return _engine().windows(limit=int(kw.get("limit", 50)))
    if kind == "screenshot":
        return _engine().screenshot(str(kw.get("name") or "arven_screen"))
    return {"success": False, "status": "invalid_argument",
            "message": "kind must be windows | screenshot"}


def _cu_act(**kw):
    action = str(kw.get("action") or "").strip()
    dry_run = bool(kw.get("dry_run", False))
    engine = _engine()
    if action == "click":
        return engine.click(kw.get("x"), kw.get("y"), dry_run=dry_run)
    if action == "type":
        return engine.type_text(kw.get("text"), dry_run=dry_run)
    if action == "key":
        return engine.key(kw.get("name"), dry_run=dry_run)
    if action == "focus":
        if dry_run:
            return {"success": True, "status": "planned",
                    "message": "dry_run — focus planned, NOT sent",
                    "planned": True, "hwnd": int(kw.get("hwnd", 0))}
        return engine.focus(kw.get("hwnd"))
    if action == "open":
        return _open_app(kw.get("app"), dry_run=dry_run)
    if action == "screenshot":
        return engine.screenshot(str(kw.get("name") or "arven_screen"))
    return {"success": False, "status": "invalid_argument",
            "message": "action must be click|type|key|focus|open|screenshot"}


def _open_app(app, dry_run=False):
    from tools.builder import get_registry
    name = str(app or "").strip()
    if not name:
        return {"success": False, "status": "invalid_argument",
                "message": "app name is empty"}
    if dry_run:
        return {"success": True, "status": "planned",
                "message": f"dry_run — opening '{name}' planned, NOT sent",
                "planned": True}
    return get_registry().invoke("open_app", app=name)


def _cu_verify(**kw):
    before = kw.get("before")
    after = kw.get("after")
    if not before or not after:
        return {"success": False, "status": "invalid_argument",
                "message": "verify needs 'before' and 'after' screenshot paths"}
    return _engine().verify(str(before), str(after))


def _cu_workflow(**kw):
    return _engine().workflow(
        kw.get("goal"),
        dry_run=bool(kw.get("dry_run", True)),
        max_iterations=int(kw.get("max_iterations", 3)))


# --- Feature 115 ----------------------------------------------------------
_add("computer_use_status", "low", "computer_use",
     "Computer-use backend report: windows, screen capture, input primitives",
     [], _cu_status)
_add("computer_use_observe", "low", "computer_use",
     "Observe the desktop: window list or a real screenshot",
     [("kind", False, "windows | screenshot"),
      ("limit", False, "max windows"), ("name", False, "screenshot name")],
     _cu_observe)
_add("computer_use_act", "high", "computer_use",
     "Send a real input action (click/type/key/focus/open/screenshot) — "
     "confirmation-gated; dry_run only plans",
     [("action", True, "click | type | key | focus | open | screenshot"),
      ("x", False, "click x"), ("y", False, "click y"),
      ("text", False, "text to type"), ("name", False, "key name"),
      ("hwnd", False, "window handle"),
      ("app", False, "app to open"), ("dry_run", False, "plan only")],
     _cu_act)
_add("computer_use_verify", "low", "computer_use",
     "Verify before/after screenshots with a real pixel diff",
     [("before", True, "path"), ("after", True, "path")], _cu_verify)
_add("computer_use_workflow", "high", "computer_use",
     "Bounded OBSERVE->PLAN->ACT->VERIFY->RECOVER workflow for a goal",
     [("goal", True, "what to do"),
      ("dry_run", False, "plan + verify only (default True)"),
      ("max_iterations", False, "1-3")],
     _cu_workflow)


TOOLS = _cu_tools

__all__ = ["TOOLS"]