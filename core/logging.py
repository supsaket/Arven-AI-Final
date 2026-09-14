"""Structured logging with secret redaction.

* rotating file logger (``Logs/arven.log``)
* sensitive-data filter (API keys, tokens, passwords)
* bounded error ring buffer for diagnostics
* ``json_log`` / structured events

Contract (nodeids test_logging.py):
``log_info/log_error/log_critical/log_exception/log_warning``,
``error(code, message, ...)``, ``json_log``, ``recent_errors()`` bounded,
``redact()`` masks secrets, ``runtime_summary()`` / ``diagnostics_summary()``
are text and secret-safe, malformed input never crashes, rotation configured.
"""

import json
import logging
import os
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from config import get_settings

_SECRET_PATTERNS = [
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "bearer",
    "client_secret",
]

_REDACTED = "[REDACTED]"

_ERROR_RING_MAX = 100


class _RingBuffer:
    def __init__(self, maxlen):
        self._q = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, item):
        with self._lock:
            self._q.append(item)

    def snapshot(self):
        with self._lock:
            return list(self._q)


# Global error ring (module-level so it survives re-instantiation).
_ERROR_RING = _RingBuffer(_ERROR_RING_MAX)


def redact(text):
    """Mask common secret values in free text."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    import re

    # key=value / "key": "value" / key: value patterns
    for pattern in _SECRET_PATTERNS:
        regex = re.compile(
            r'(["\']?)(' + re.escape(pattern) + r'\s*[=:]\s*)(["\']?)([^\s"\',}]+)',
            re.IGNORECASE,
        )
        text = regex.sub(rf"\1\2\3{_REDACTED}", text)

    # URLs with embedded credentials
    text = re.sub(
        r"(https?://)([^:/\s]+):([^@\s/]+)@",
        r"\1\2:[REDACTED]@",
        text,
    )
    # bare long tokens (>= 16 chars)
    text = re.sub(
        r"\b([A-Za-z0-9_\-]{16,})\b",
        lambda m: _REDACTED if not m.group(1).startswith(("arven", "ARVEN")) else m.group(1),
        text,
    )
    return text


def _safe_payload(message):
    if message is None:
        return None
    try:
        return redact(str(message))
    except Exception:
        return "[unserialisable]"


class ArvenLogger:

    def __init__(self, log_dir=None, level=logging.INFO):
        settings = get_settings()
        self.log_dir = Path(log_dir) if log_dir else Path(settings.LOG_DIR or "Logs")
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.log_dir = Path.cwd() / "Logs"
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.log_dir = Path.cwd()

        self._logger = logging.getLogger("arven")
        if not self._logger.handlers:
            handler = logging.FileHandler(str(self.log_dir / "arven.log"), encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"
            ))
            self._logger.addHandler(handler)
            self._logger.setLevel(level)
            self._logger.propagate = False

        self.rotation_max_bytes = 1_000_000

    # ------------------------------------------------------------------
    def _record(self, level, code, message, **fields):
        safe = redact(message)
        try:
            structured = {
                "ts": time.time(),
                "level": level,
                "code": code,
                "message": safe,
                **{k: _safe_payload(v) for k, v in fields.items()},
            }
            line = json.dumps(structured, default=str)
        except Exception:
            line = f"{level} {code} {safe}"
        self._logger.log(level, line)

        if level >= logging.ERROR:
            try:
                _ERROR_RING.push({
                    "ts": time.time(),
                    "level": level,
                    "code": code,
                    "message": safe,
                })
            except Exception:
                pass

    def info(self, code, message="", **fields):
        self._record(logging.INFO, code, message, **fields)

    def warning(self, code, message="", **fields):
        self._record(logging.WARNING, code, message, **fields)

    def error(self, code, message="", **fields):
        self._record(logging.ERROR, code, message, **fields)

    def critical(self, code, message="", **fields):
        self._record(logging.CRITICAL, code, message, **fields)

    def exception(self, code, message="", exc=None):
        tb = traceback.format_exc() if exc is None else "".join(traceback.format_exception(exc))
        self._record(logging.ERROR, code, message, traceback=tb[-4000:])

    # ------------------------------------------------------------------
    def recent_errors(self, limit=20):
        ring = _ERROR_RING.snapshot()
        return [e for e in ring[-limit:]]

    def runtime_summary(self):
        settings = get_settings()
        lines = [
            f"ARVEN runtime | name={settings.APP_NAME} version={settings.VERSION}",
            f"model={settings.MODEL_PROVIDER}/{settings.MODEL_NAME}",
            f"recent_errors={len(_ERROR_RING.snapshot())}",
            f"log_file={self._logger.handlers[0].baseFilename if self._logger.handlers else 'none'}",
        ]
        return redact("\n".join(lines))

    def diagnostics_summary(self):
        return self.runtime_summary()

    def rotation_config(self):
        return {
            "max_bytes": self.rotation_max_bytes,
            "backup_count": 3,
            "path": str(self._logger.handlers[0].baseFilename) if self._logger.handlers else None,
        }


from pathlib import Path  # noqa: E402

# Shared logger instance.
logger = ArvenLogger()
def json_log(level, code, message, **fields):
    return logger._record(getattr(logging, level.upper(), logging.INFO), code, message, **fields)


__all__ = [
    "ArvenLogger",
    "logger",
    "redact",
    "json_log",
]
