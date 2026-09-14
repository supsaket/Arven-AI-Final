"""Graceful ARVEN application shutdown.

The order matters and is guaranteed here:
  1. say "Bye Boss." (fully finish speech playback)
  2. stop voice / listening resources
  3. unregister the global hotkey
  4. stop background workers (Brain worker, scheduler, TTS)
  5. save pending state / memory
  6. close the window
  7. terminate the process

Only the ARVEN *application* is shut down. This module NEVER issues a Windows
shutdown/restart command. It is dependency-injected so tests can assert the
ordering without touching real audio, hotkeys, or the OS.
"""

from desktop.state import AppState

# The ordered step names (used for reporting / testing).
STEPS = [
    "say_bye",
    "finish_speech",
    "stop_voice",
    "unregister_hotkey",
    "stop_workers",
    "save_state",
    "close_window",
    "terminate",
]


class ShutdownError(RuntimeError):
    pass


class ShutdownPlan:
    """A runnable, injectable shutdown plan.

    Each step is a zero-argument callable returning None. A step that raises is
    caught and reported (so a broken subsystem never blocks the rest of the
    shutdown, and never prevents the app from closing). Failures are collected
    and returned rather than crashing the process.
    """

    def __init__(self):
        self.steps = {
            "say_bye": lambda: None,
            "finish_speech": lambda: None,
            "stop_voice": lambda: None,
            "unregister_hotkey": lambda: None,
            "stop_workers": lambda: None,
            "save_state": lambda: None,
            "close_window": lambda: None,
            "terminate": lambda: None,
        }

    def set(self, name, fn):
        if name not in self.steps:
            raise KeyError(f"unknown shutdown step: {name}")
        self.steps[name] = fn
        return self

    def run(self):
        """Execute all steps in order.

        Returns (completed_steps, errors) where completed_steps is the ordered
        list of steps that succeeded and errors is a dict of step->exception for
        any that raised. A failed step does NOT skip the later ones.
        """
        completed = []
        errors = {}
        for name in STEPS:
            try:
                self.steps[name]()
                completed.append(name)
            except Exception as exc:  # never block the remaining steps
                errors[name] = exc
        return completed, errors

    @property
    def state_after(self):
        """The AppState an app should be in once shutdown has run."""
        return AppState.CLOSED
