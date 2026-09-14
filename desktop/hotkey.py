"""Windows global hotkey (Ctrl/Alt/Shift + key) support for ALT+A.

Uses the Win32 RegisterHotKey API with its own message pump on a daemon thread,
so ARVEN can react to ALT+A even when another application has keyboard focus.

- Safe registration: if RegisterHotKey fails (in use, etc.) we log a clear error
  and continue without crashing.
- Safe unregistration on stop.
- The trigger callback is injected, so the *same* hotkey machinery drives both
  "focus ARVEN" (when the app is running) and "launch ARVEN" (from the
  background auto-start agent).
"""

import ctypes
import ctypes.wintypes as wt
import logging
import threading

log = logging.getLogger("arven.desktop.hotkey")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_REMOVE = 0x0001

# Default: ALT + A
DEFAULT_VK = 0x41
DEFAULT_MODS = MOD_ALT

_user32 = ctypes.windll.user32


class HotkeyError(RuntimeError):
    pass


class GlobalHotkey(threading.Thread):
    """Registers a global hotkey on a background message-pump thread.

    ``callback`` is invoked whenever the hotkey is pressed. It runs on this
    thread, so it should be cheap (schedule real work elsewhere).
    """

    def __init__(self, vk=DEFAULT_VK, mods=DEFAULT_MODS, hotkey_id=0x4156,
                 callback=None):
        super().__init__(daemon=True, name="arven-hotkey")
        self.vk = vk
        self.mods = mods
        self.hotkey_id = hotkey_id
        self.callback = callback or (lambda: None)
        self._registered = False
        self._stop_event = threading.Event()
        self.message_wnd = None

    def register(self):
        """Attempt to register the hotkey. Returns None on success or raises
        HotkeyError with a clear message on failure."""
        # A window handle is required for the message loop.
        self.message_wnd = _user32.CreateWindowExW(
            0, "STATIC", "ArvenHotkey", 0, 0, 0, 0, 0, None, None, None, None)
        if not self.message_wnd:
            raise HotkeyError("Failed to create the hotkey message window.")
        if not _user32.RegisterHotKey(self.message_wnd, self.hotkey_id,
                                      self.mods, self.vk):
            raise HotkeyError(
                "ARVEN AI could not register the ALT+A global hotkey on this "
                "Windows session (it may already be in use). The app still "
                "runs; the hotkey is just unavailable."
            )
        self._registered = True

    def run(self):
        if not self._registered:
            return
        msg = wt.MSG()
        while not self._stop_event.is_set():
            result = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:  # 0 => WM_QUIT, -1 => error
                break
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                try:
                    self.callback()
                except Exception as exc:  # never kill the pump
                    log.error("hotkey callback failed: %s", exc)
            else:
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        self._cleanup()

    def stop(self):
        self._stop_event.set()
        if self.message_wnd:
            _user32.PostMessageW(self.message_wnd, WM_QUIT, 0, 0)
        if self.is_alive():
            self.join(timeout=2)

    def _cleanup(self):
        if self._registered and self.message_wnd:
            try:
                _user32.UnregisterHotKey(self.message_wnd, self.hotkey_id)
            except Exception:
                pass
            try:
                _user32.DestroyWindow(self.message_wnd)
            except Exception:
                pass
            self._registered = False
