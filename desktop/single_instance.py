"""Windows single-instance enforcement for ARVEN AI.

Uses a named mutex so a second launch of the app is refused instead of spawning
a second process/window, and provides a helper to focus an already-running
ARVEN window (used by the launcher and by the ALT+A hotkey).
"""

import ctypes
from ctypes import wintypes

MUTEX_NAME = "Global\\ARVEN_AI_SingleInstance"
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32

SW_RESTORE = 9


def acquire_single_instance(name=MUTEX_NAME):
    """Create (or open) the named mutex.

    Returns (handle, is_primary) where is_primary is True for the first/primary
    instance and False if another instance already owns the mutex. The caller
    is responsible for closing the handle on shutdown.
    """
    handle = _kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None, False
    last_error = ctypes.get_last_error() or _kernel32.GetLastError()
    is_primary = last_error != ERROR_ALREADY_EXISTS
    return handle, is_primary


def release_single_instance(handle):
    """Close the mutex handle, releasing the single-instance lock."""
    if handle:
        try:
            _kernel32.CloseHandle(handle)
        except Exception:
            pass


def _find_arvwn_by_title(title):
    """Return the HWND of the first top-level window whose title matches, or 0."""
    _user32.SetLastError(0)
    return _user32.FindWindowW(None, title)


def focus_window(title):
    """Bring an existing window (matched by title) to the foreground.

    Minimized windows are restored first. Returns True if a window was found and
    raised, else False.
    """
    hwnd = _find_arvwn_by_title(title)
    if not hwnd:
        return False
    if not _user32.IsWindow(hwnd):
        return False
    _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)
    return True
