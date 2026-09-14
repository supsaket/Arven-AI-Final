"""Lifecycle management.

Makes startup/shutdown deterministic and safe:
* state machine: stopped -> starting -> running -> stopping -> stopped
* start hooks run in registration order; stop hooks in REVERSE order
* a hook failure is reported but leaves the lifecycle usable (recovers)
* start/stop are idempotent and shutdown is safe to call twice
* ``BoundedOperation`` measures wall-clock time and captures interruption
"""

import threading
import time
from enum import Enum


class LifecycleState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class BoundedOperation:
    """Run a callable with a wall-clock bound; captures interruption."""

    def __init__(self):
        self._lock = threading.Lock()
        self._was_interrupted = False

    @property
    def interrupted(self):
        return self._was_interrupted

    @classmethod
    def run(cls, function, timeout=5.0):
        op = cls()
        result = {}

        def runner():
            try:
                result["value"] = function()
                result["ok"] = True
            except Exception as exc:
                result["ok"] = False
                result["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        t0 = time.monotonic()
        thread.start()
        thread.join(timeout=float(timeout))
        elapsed = time.monotonic() - t0
        if thread.is_alive():
            op._was_interrupted = True
            return op, "interrupted", None
        if not result.get("ok"):
            return op, "error", repr(result["error"])
        return op, "ok", result["value"]


class LifecycleManager:

    def __init__(self):
        self._state = LifecycleState.STOPPED
        self._lock = threading.Lock()
        self._start_hooks = []
        self._stop_hooks = []
        self._started_at = None
        self._interrupted_operation = None
        self._startup_failure = None
        self._initialized = False

    # ------------------------------------------------------------------
    def state(self):
        with self._lock:
            return self._state.value

    def is_running(self):
        with self._lock:
            return self._state is LifecycleState.RUNNING

    def uptime(self):
        with self._lock:
            if self._started_at is None:
                return 0.0
            return time.monotonic() - self._started_at

    def initialize(self):
        """Prepare resources once; idempotent."""
        with self._lock:
            if self._initialized:
                return False
            self._initialized = True
            return True

    # ------------------------------------------------------------------
    def add_start_hook(self, hook, order=0):
        self._start_hooks.append((order, hook))
        self._start_hooks.sort(key=lambda item: item[0])

    def add_stop_hook(self, hook, order=0):
        self._stop_hooks.append((order, hook))

    # ------------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._state in (LifecycleState.STARTING, LifecycleState.RUNNING):
                return True  # idempotent
            if self._state is LifecycleState.STOPPING:
                raise RuntimeError("cannot start while stopping")
            self._state = LifecycleState.STARTING
            self._startup_failure = None
            hooks = list(self._start_hooks)
        try:
            for _, hook in hooks:
                try:
                    hook()
                except Exception as exc:
                    # reported but lifecycle recovers and continues
                    self._startup_failure = repr(exc)
            with self._lock:
                self._state = LifecycleState.RUNNING
                if self._started_at is None:
                    self._started_at = time.monotonic()
                return True
        except Exception:
            with self._lock:
                self._state = LifecycleState.STOPPED
            raise

    def stop(self):
        with self._lock:
            was_stopping = self._state is LifecycleState.STOPPING
            self._state = LifecycleState.STOPPING
            hooks = list(self._stop_hooks)
        for _, hook in hooks:
            try:
                hook()
            except Exception:
                pass  # shutdown never crashes on a hook failure
        with self._lock:
            self._state = LifecycleState.STOPPED
            self._started_at = None
            self._startup_failure = None
        return True

    def capture(self, operation):
        self._interrupted_operation = operation

    @property
    def last_interrupted_operation(self):
        return self._interrupted_operation

    @property
    def startup_failure(self):
        return self._startup_failure


__all__ = [
    "LifecycleManager", "LifecycleState", "BoundedOperation",
]