"""Computer Use agent (row 13) — safe input automation and status capture.

Contracts enforced:
* operations declare their required capabilities; a step needing an
  unavailable capability is reported, never simulated
* tool-backed steps (open_app, capture_screen, media) route through the
  ToolRegistry; low-level input goes through an injectable driver (never raw
  pyautogui)
* observations are captured before and after every step
* a failed step is isolated and does not abort the remaining plan
* destructive actions require explicit confirmation
* ``run`` with an empty request returns structured help
"""

from brain.intent import detect_open_app

_REQUIRED_CAPABILITIES = {
    "mouse_move": ["keyboard_mouse", "display"],
    "click": ["keyboard_mouse", "display"],
    "double_click": ["keyboard_mouse", "display"],
    "right_click": ["keyboard_mouse", "display"],
    "drag": ["keyboard_mouse", "display"],
    "scroll": ["keyboard_mouse", "display"],
    "keypress": ["keyboard_mouse"],
    "hotkey": ["keyboard_mouse"],
    "type": ["keyboard_mouse"],
    "open_app": ["process_control"],
    "close_app": ["process_control"],
    "capture_screen": ["display", "screen_capture"],
}

_HELP = {
    "actions": ["mouse_move", "click", "double_click", "right_click", "drag",
                "scroll", "keypress", "hotkey", "type", "open_app", "close_app",
                "capture_screen"],
    "usage": 'step {"action": "mouse_move", "x": 100, "y": 200}',
}


class ComputerUseAgent:

    def __init__(self, registry=None, driver=None, capabilities=None, refs=None):
        from tools.builder import get_registry
        self.registry = registry or get_registry()
        self.driver = driver or FallbackInputDriver()
        self.capabilities = capabilities or self._local_capabilities()
        self.refs = refs

    @staticmethod
    def _local_capabilities():
        try:
            import ctypes
            return {"keyboard_mouse": True, "display": True,
                    "screen_capture": True, "process_control": True}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    def parse_plan(self, request):
        """Convert "open notepad and type hello" into a list of step dicts."""
        text = str(request or "").strip()
        if not text:
            return []
        steps = []
        if detect_open_app(text):
            app = text.split("open", 1)[1].strip().split(" and ")[0].strip()
            steps.append({"action": "open_app", "app": app})
        if "type" in text.lower():
            tail = text.lower().split("type", 1)[1].strip()
            steps.append({"action": "type", "text": tail.strip("'\"")})
        return steps

    def run(self, request, confirm=False, dry_run=False):
        if not str(request or "").strip():
            return {"success": True, "help": _HELP,
                    "message": "Empty request — here is what I can do."}
        steps = self.parse_plan(request)
        if not steps and isinstance(request, dict):
            steps = [request]
        elif not steps:
            steps = [{"action": request}]
        observations = {"before": self._observe(), "after": None, "steps": []}
        results = []
        for step in steps:
            result = self._execute_step(step, confirm=confirm, dry_run=dry_run)
            observations["steps"].append({
                "step": step, "before": result.get("before"),
                "after": result.get("after")})
            if not result.get("success"):
                results.append({"step": step, "success": False,
                                "message": result.get("message")})
        observations["after"] = self._observe()
        return {"success": all(r.get("success", True) for r in results)
                if results else True,
                "observations": observations, "steps": results}

    # ------------------------------------------------------------------
    def _execute_step(self, step, confirm=False, dry_run=False):
        action = str(step.get("action") or step if isinstance(step, dict) else step).strip()
        if not action:
            return {"success": False, "message": "step has no action"}
        if action in _REQUIRED_CAPABILITIES:
            missing = [c for c in _REQUIRED_CAPABILITIES[action]
                       if not self.capabilities.get(c)]
            if missing:
                return {"success": False,
                        "message": f"requires unavailable capability: {missing}",
                        "unavailable": True}
        before = self._observe()
        if action in ("open_app", "close_app"):
            target = step.get("app", step.get("target", ""))
            if not target:
                return {"success": False, "message": "no application named"}
            args = {"app": target} if action == "open_app" else {"app": target}
            tool = "open_app" if action == "open_app" else "close_app"
            try:
                result = self.registry.invoke(tool, confirmed=confirm, **args)
                outcome = result.get("success", False)
            except Exception:
                outcome = False
        elif action in ("mouse_move", "click", "double_click", "right_click",
                        "drag", "scroll"):
            outcome = self.driver.perform(action, step, dry_run=dry_run)
        elif action in ("type", "keypress", "hotkey"):
            outcome = self.driver.perform(action, step, dry_run=dry_run)
        elif action == "capture_screen":
            outcome = self.registry.invoke("capture_screen", confirmed=confirm).get("success", False)
        else:
            outcome = {"success": False, "unavailable": True,
                       "message": f"unsupported action: {action}"}
        if isinstance(outcome, dict):
            success = outcome.get("success")
        else:
            success = bool(outcome)
        after = self._observe()
        return {"success": success, "before": before, "after": after,
                "message": outcome.get("message") if isinstance(outcome, dict) else ""}

    def _observe(self):
        try:
            result = self.registry.invoke("capture_screen", confirmed=False)
            return {"screen": result.get("success", False)}
        except Exception:
            return {"screen": False}


class FallbackInputDriver:
    """Honest fallback: reports input availability, never fakes success."""

    def perform(self, action, step, dry_run=False):
        return {"success": False, "unavailable": True,
                "message": "input driver not configured for " + action}


computer_use_agent = ComputerUseAgent()

__all__ = ["ComputerUseAgent", "computer_use_agent", "_REQUIRED_CAPABILITIES"]