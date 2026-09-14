"""Error recovery and execution guard.

Provides:
* ``ExecutionGuard`` — at-most-once execution keyed by (tool, args).
* ``RecoveryAction`` — outcome classification after a tool call.
* ``run_tool_with_recovery`` — bounded retries + graceful structured failure.
* ``classify`` — map a value/exception to a ``RecoveryAction``.

Contract (from verify_recovery.py / nodeids):
``run_tool_with_recovery(function, kwargs, destructive, action)`` returns a
``dict`` with ``status``/``success``/``message`` (plus ``action``). Safe tools
retry transient failures with backoff; destructive tools run EXACTLY once and
are never retried.
"""

import functools
import threading
import time

# Outcome taxonomy
OK = "ok"
RETRYABLE = "retryable"
FAILED = "failed"
BLOCKED = "blocked"


class RecoveryAction:
    """Classification of a single tool invocation outcome."""

    __slots__ = ("status", "message", "detail")

    def __init__(self, status, message="", detail=None):
        self.status = status
        self.message = message or "no details"
        self.detail = detail

    def __bool__(self):
        return self.status == OK

    def __eq__(self, other):
        if isinstance(other, RecoveryAction):
            return self.status == other.status
        if isinstance(other, str):
            return self.status == other
        return NotImplemented

    def __repr__(self):
        return f"RecoveryAction(status={self.status!r}, message={self.message!r})"


def classify(value, message=""):
    """Classify an arbitrary tool result/exception into a RecoveryAction."""
    if isinstance(value, RecoveryAction):
        return value

    if isinstance(value, Exception):
        text = f"{type(value).__name__}: {value}"

        if isinstance(value, TimeoutError):
            return RecoveryAction(RETRYABLE, text)
        if isinstance(value, OSError) and getattr(value, "errno", None) in (
            11,      # EAGAIN
            35,      # EAGAIN (alias)
            10053,   # WSAECONNABORTED
            10054,   # WSAECONNRESET
            11001,   # host not found
        ):
            return RecoveryAction(RETRYABLE, text)

        return RecoveryAction(FAILED, text)

    if isinstance(value, dict):
        status = str(value.get("status", "")).lower()
        msg = str(value.get("message") or message or "tool returned")

        if status in ("ok", "success"):
            return RecoveryAction(OK, msg)
        if status in ("retry", "retryable", "transient", "timeout"):
            return RecoveryAction(RETRYABLE, msg)
        if status in ("blocked", "denied", "unavailable", "not_configured"):
            return RecoveryAction(BLOCKED, msg)

        return RecoveryAction(FAILED, msg)

    # A plain truthy result is success.
    return RecoveryAction(OK, message or "ok")


class ExecutionGuard:
    """At-most-once guard keyed by (tool, args)."""

    def __init__(self):
        self._locks = {}
        self._seen = set()
        self._guard = threading.Lock()

    def _key(self, key):
        if isinstance(key, (tuple, list)):
            return (str(key[0]), str(key[1] if len(key) > 1 else ""))
        return (str(key), "")

    def acquire(self, key, timeout=None):
        k = self._key(key)
        lock = self._locks.setdefault(k, threading.Lock())
        if timeout is None:
            got = lock.acquire()
        else:
            got = lock.acquire(timeout=timeout)
        if got:
            self._seen.add(k)
        return got

    def release(self, key):
        k = self._key(key)
        lock = self._locks.get(k)
        if lock is None:
            return True
        try:
            lock.release()
            return True
        except RuntimeError:
            return True

    def is_active(self, key):
        k = self._key(key)
        lock = self._locks.get(k)
        if lock is None:
            return False
        return lock.locked()

    def was_run(self, key):
        return self._key(key) in self._seen

    def track(self, key):
        self._seen.add(self._key(key))


def _call(function, kwargs):
    try:
        value = function(**kwargs)
        return value, None
    except Exception as exc:  # noqa: BLE001 — recovery boundary
        return None, exc


def run_tool_with_recovery(function, kwargs=None, destructive=False, action=None, attempts=3):
    """Run a tool with bounded retries for transient failures.

    * Safe tools: retry transient failures (attempts, exponential backoff).
    * Destructive tools: run EXACTLY once, never retried.
    * Never raises for runtime failures; returns a structured dict.

    If the tool returns a raw truthy value, it is wrapped into a success dict.
    """
    kwargs = dict(kwargs or {})
    action = action or getattr(function, "__name__", "tool")

    if destructive:
        value, exc = _call(function, kwargs)
        if exc is not None:
            outcome = classify(exc)
            return {
                "status": "error",
                "success": False,
                "action": action,
                "message": f"{action} failed: {outcome.message}",
                "recovery": "no_retry_destructive",
            }

        return _package(value, action, attempts=1)

    last_error = None
    for attempt in range(1, attempts + 1):
        value, exc = _call(function, kwargs)
        if exc is None:
            return _package(value, action, attempts=attempt)

        outcome = classify(exc)
        last_error = outcome.message
        if outcome.status != RETRYABLE or attempt == attempts:
            break
        time.sleep(min(0.1 * (2 ** (attempt - 1)), 1.0))

    return {
        "status": "error",
        "success": False,
        "action": action,
        "message": f"{action} failed after {attempts} attempt(s): {last_error}",
        "recovery": "exhausted",
    }


def _package(value, action, attempts=1):
    if isinstance(value, dict):
        merged = dict(value)
        merged.setdefault("status", "ok" if merged.get("success", True) else "error")
        merged.setdefault("success", True)
        merged.setdefault("action", action)
        merged.setdefault("message", "ok")
        merged["retries"] = attempts
        return merged

    return {
        "status": "ok",
        "success": bool(value) if value is not None else True,
        "action": action,
        "message": "ok",  # structured success carries message,
        "retries": attempts,
    }


__all__ = [
    "ExecutionGuard",
    "RecoveryAction",
    "classify",
    "run_tool_with_recovery",
    "OK",
    "RETRYABLE",
    "FAILED",
    "BLOCKED",
]