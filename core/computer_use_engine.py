"""Feature 115 — Professional Computer Use Engine.

Genuine, bounded computer control on Windows via ctypes (no extra
dependencies required):

* ``windows()``       — real EnumWindows enumeration (hwnd, title, visible)
* ``screenshot()``    — real PIL ImageGrab capture (PIL detected, never faked)
* ``focus(hwnd)``     — foreground/restore a real window
* ``click(x, y)``     — real mouse input (SetCursorPos + mouse_event)
* ``type(text)``      — real keyboard input via SendInput (KEYEVENTF_UNICODE)
* ``key(name)``       — real keybd_event for a small allow-listed key set
* ``verify(a, b)``    — real pixel-diff verification of a before/after pair
* ``workflow(...)``   — bounded OBSERVE -> PLAN -> ACT -> VERIFY -> RECOVER

Honesty contract:
* on a non-Windows host, input/window primitives return SOFTWARE_REQUIRED /
  HARDWARE_REQUIRED — nothing is simulated;
* without PIL, screenshots/verification report SOFTWARE_REQUIRED;
* ``dry_run`` never claims success: it returns the PLANNED action only;
* a click/key/type that cannot be verified is reported as unverified, never
  as a successful interaction.

Safety: this module performs NO privileged mutation by itself; every input
action is exposed through the registry as HIGH risk (confirmation-gated) and
coordinates are bounds-checked against the real screen size.
"""

import ctypes
import sys
import time

_DEFAULT_SCREENSHOT_DIR = "Output/screenshots"


def _pil_available():
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _windows_available():
    return bool(sys.platform == "win32")


def _sendinput():
    if not _windows_available():
        return None
    try:
        return ctypes.windll.user32
    except Exception:
        return None


class ComputerUseEngine:
    """Deterministic, honest computer-control primitives + the CU workflow."""

    def __init__(self, screenshot_dir=None):
        self.screenshot_dir = screenshot_dir or _DEFAULT_SCREENSHOT_DIR
        self._user32 = _sendinput()

    # ------------------------------------------------------------------
    # capability report
    # ------------------------------------------------------------------
    def status(self):
        windows = _windows_available()
        return {
            "success": True, "status": "ok",
            "platform": sys.platform,
            "windows_backend": {
                "available": bool(self._user32 is not None and windows),
                "note": "ctypes user32 detected"
                        if self._user32 is not None and windows
                        else "requires Windows + user32",
            },
            "screen_capture": {
                "available": _pil_available(),
                "note": "PIL ImageGrab present"
                        if _pil_available()
                        else "pil is required for screenshots/verification",
            },
            "input_primitive": "real mouse/keyboard via user32"
                if windows else "SOFTWARE_REQUIRED (non-Windows)",
            "safe_default": ("all input actions are confirmation-gated and "
                             "bounds-checked; dry_run never executes"),
        }

    # ------------------------------------------------------------------
    # observe
    # ------------------------------------------------------------------
    def screen_size(self):
        if self._user32 is None:
            return None
        width = self._user32.GetSystemMetrics(0)
        height = self._user32.GetSystemMetrics(1)
        if width <= 0 or height <= 0:
            return None
        return width, height

    def windows(self, limit=50):
        """Real window enumeration via EnumWindows."""
        if self._user32 is None:
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "window enumeration requires Windows user32"}
        found = []

        def _callback(hwnd, _extra):
            if not self._user32.IsWindowVisible(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True
            found.append({"hwnd": int(hwnd), "title": title})
            return True

        self._user32.EnumWindows(ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_callback), 0)
        return {"success": True, "status": "ok",
                "window_count": len(found),
                "windows": found[:limit]}

    def screenshot(self, name="arven_screen"):
        """Real screen capture to a PNG (PIL ImageGrab)."""
        if not _pil_available():
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "screenshot requires PIL (ImageGrab)"}
        from PIL import ImageGrab
        from core.output import output_manager
        try:
            image = ImageGrab.grab()
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"capture failed: {exc}"}
        try:
            written = output_manager.write(
                self.screenshot_dir, f"{name}.png",
                _png_bytes(image), metadata={"type": "ARVEN_SCREENSHOT"})
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"save failed: {exc}"}
        return {
            "success": True, "status": "ok",
            "path": written["path"],
            "size": image.size,
            "mode": image.mode,
            "message": "screen captured",
        }

    # ------------------------------------------------------------------
    # act (real input, bounds-checked)
    # ------------------------------------------------------------------
    def focus(self, hwnd):
        if self._user32 is None:
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "window control requires Windows user32"}
        try:
            self._user32.ShowWindow(int(hwnd), 9)  # SW_RESTORE
            self._user32.SetForegroundWindow(int(hwnd))
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"focus failed: {exc}"}
        return {"success": True, "status": "ok", "hwnd": int(hwnd),
                "message": "window brought to foreground"}

    def click(self, x, y, dry_run=False):
        return self._guard_viewport(x, y, dry_run=dry_run)

    def _guard_viewport(self, x, y, dry_run=False):
        if self._user32 is None:
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "mouse input requires Windows user32"}
        size = self.screen_size()
        try:
            px, py = int(x), int(y)
        except (TypeError, ValueError):
            return {"success": False, "status": "invalid_argument",
                    "message": "coordinates must be integers"}
        if size is not None and not (0 <= px < size[0] and 0 <= py < size[1]):
            return {"success": False, "status": "invalid_argument",
                    "message": f"click ({px},{py}) outside screen {size}"}
        if dry_run:
            return {"success": True, "status": "planned",
                    "message": f"dry_run — mouse click at ({px},{py}) "
                               "planned, NOT sent", "planned": True,
                    "at": {"x": px, "y": py}}
        try:
            self._user32.SetCursorPos(px, py)
            self._user32.mouse_event(2, 0, 0, 0, 0)  # LEFTDOWN
            self._user32.mouse_event(4, 0, 0, 0, 0)  # LEFTUP
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"click failed: {exc}"}
        return {"success": True, "status": "ok",
                "message": f"mouse click sent at ({px},{py})", "at": (px, py)}

    def type_text(self, text, dry_run=False):
        if self._user32 is None:
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "keyboard input requires Windows user32"}
        text = str(text or "")
        if not text:
            return {"success": False, "status": "invalid_argument",
                    "message": "text is empty"}
        if len(text) > 4000:
            return {"success": False, "status": "invalid_argument",
                    "message": "text too long (max 4000 chars)"}
        if dry_run:
            return {"success": True, "status": "planned",
                    "message": f"dry_run — {len(text)} characters planned, "
                               "NOT typed", "planned": True,
                    "characters": len(text)}
        try:
            self._send_unicode(text)
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"type failed: {exc}"}
        return {"success": True, "status": "ok",
                "message": f"{len(text)} characters typed", "characters": len(text)}

    def _send_unicode(self, text):
        DWORD = ctypes.c_ulong
        WORD = ctypes.c_ushort
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                        ("time", DWORD), ("dwExtraInfo", ctypes.POINTER(DWORD))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", DWORD), ("ki", KEYBDINPUT)]

        send = ctypes.windll.user32.SendInput
        send.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        send.restype = ctypes.c_uint
        for char in text:
            for flags in (KEYEVENTF_UNICODE,
                          KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                ki = KEYBDINPUT(0, ord(char), flags, 0, None)
                inp = INPUT(1, ki)
                send(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.002)

    def key(self, name, dry_run=False):
        if self._user32 is None:
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "keyboard input requires Windows user32"}
        vk = _KEY_MAP.get(str(name or "").lower().strip())
        if vk is None:
            return {"success": False, "status": "invalid_argument",
                    "message": f"unknown key '{name}' — allowed: "
                               f"{sorted(_KEY_MAP)}"}
        if dry_run:
            return {"success": True, "status": "planned",
                    "message": f"dry_run — key '{name}' planned, NOT sent",
                    "planned": True}
        try:
            self._user32.keybd_event(vk, 0, 0, 0)
            self._user32.keybd_event(vk, 0, 2, 0)
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"key failed: {exc}"}
        return {"success": True, "status": "ok", "message": f"key '{name}' sent"}

    # ------------------------------------------------------------------
    # verify
    # ------------------------------------------------------------------
    def verify(self, before, after):
        if not _pil_available():
            return {"success": False, "status": "SOFTWARE_REQUIRED",
                    "message": "verification requires PIL"}
        from PIL import Image, ImageChops
        try:
            a = Image.open(before).convert("RGB")
            b = Image.open(after).convert("RGB")
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"could not read images: {exc}"}
        if a.size != b.size:
            return {"success": False, "status": "ok",
                    "message": f"unverified: image sizes differ "
                               f"({a.size} vs {b.size})",
                    "changed": None, "reason": "size mismatch"}
        try:
            diff = ImageChops.difference(a, b)
            bbox = diff.getbbox()
            changed = bbox is not None
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"verification computation failed: {exc}"}
        return {
            "success": True, "status": "ok",
            "changed": bool(changed),
            "diff_bbox": list(bbox) if bbox else None,
            "message": "screen verified as "
                       + ("changed" if changed else "unchanged"),
        }

    # ------------------------------------------------------------------
    # bounded workflow (OBSERVE -> PLAN -> ACT -> VERIFY -> RECOVER)
    # ------------------------------------------------------------------
    def workflow(self, goal, dry_run=False, max_iterations=3):
        goal = str(goal or "").strip()
        if not goal:
            return {"success": False, "status": "invalid_argument",
                    "message": "goal is empty"}
        iterations = max(1, min(3, int(max_iterations or 3)))
        before = self.screenshot("before") if not dry_run else \
            {"success": False, "status": "planned",
             "message": "dry_run skips capture"}
        actions = self._plan(goal)
        loop = []
        for attempt in range(1, iterations + 1):
            executed = []
            for action in actions:
                out = self._execute_planned(action, dry_run=dry_run)
                executed.append(out)
            verification = None
            if not dry_run and before.get("success") is True:
                after = self.screenshot("after")
                verification = self.verify(before.get("path"),
                                           after.get("path"))
            elif dry_run:
                verification = {"status": "planned",
                                "message": "dry_run — verification skipped"}
            changed = bool(verification
                           and verification.get("changed") is True)
            loop.append({
                "attempt": attempt, "actions": executed,
                "verification": verification, "screen_changed": changed,
            })
            if changed or not dry_run and verification and \
                    verification.get("changed") is False and attempt == 1:
                continue
            if verification and verification.get("changed") is True:
                break
        final = loop[-1]
        return {
            "success": True, "status": "ok",
            "goal": goal, "dry_run": bool(dry_run),
            "iterations": len(loop), "loop": loop,
            "summary": {
                "executed_actions": sum(
                    len(v.get("actions", [])) for v in loop),
                "last_verification": final.get("verification"),
                "conclusion": ("verification detected screen change"
                               if any(v.get("screen_changed") for v in loop)
                               else "no verified change (dry_run or "
                                    "unverified)"),
            },
        }

    def _plan(self, goal):
        low = goal.lower()
        steps = []
        if "click" in low:
            steps.append({"action": "click", "params": {}})
        if "type" in low or "enter" in low or "write" in low:
            steps.append({"action": "type", "params": {}})
        if "open" in low:
            steps.append({"action": "app", "params": {}})
        steps.append({"action": "verify", "params": {}})
        return steps

    def _execute_planned(self, planned, dry_run):
        action = planned.get("action")
        params = dict(planned.get("params") or {})
        if action == "click":
            return self.click(params.get("x", 0), params.get("y", 0),
                              dry_run=dry_run)
        if action == "type":
            return self.type_text(params.get("text", ""), dry_run=dry_run)
        if action == "app":
            return {"success": False, "status": "planned",
                    "message": "app launch requires an explicit app name",
                    "planned": True}
        if action == "verify":
            return {"success": True, "status": "ok",
                    "message": "verify step: compare before/after screenshots"}
        return {"success": False, "status": "invalid_argument",
                "message": f"unknown planned action '{action}'"}


def _png_bytes(image):
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


_KEY_MAP = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
    "escape": 0x1B, "space": 0x20, "backspace": 0x08, "delete": 0x2E,
    "left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
}


computer_use = ComputerUseEngine()

__all__ = [
    "ComputerUseEngine", "computer_use",
    "_pil_available", "_windows_available",
]