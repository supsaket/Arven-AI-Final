"""Alerts and notifications (Day 2, feature 58).

Channel honesty contract:

* ``local``  — always AVAILABLE; delivery appends to the internal alert
  journal kept inside the KeyValueStore (no external side effects).
* ``email``/``push``/``sms`` — default ``NOT_CONFIGURED``. They only move
  toward AVAILABLE when configured AND enabled with explicit confirmation
  AND a real runtime backend adapter is registered. ``notify`` never
  claims external delivery without such a backend.

Status values are limited to the honest set:
AVAILABLE / UNAVAILABLE / NOT_CONFIGURED / OFFLINE / REQUIRES_AUTH /
REQUIRES_PERMISSION / FAILED.

Closing an alert archives it (status ``closed``); nothing is ever deleted.
"""

import time

from core.kv import KeyValueStore

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]
SEVERITY_INDEX = {name: i for i, name in enumerate(SEVERITY_ORDER)}

STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_OFFLINE = "OFFLINE"
STATUS_REQUIRES_AUTH = "REQUIRES_AUTH"
STATUS_REQUIRES_PERMISSION = "REQUIRES_PERMISSION"
STATUS_FAILED = "FAILED"

STATUS_SET = {
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
    STATUS_REQUIRES_PERMISSION,
    STATUS_FAILED,
}

_RECORDS_KEY = "alerts.records"
_COUNTER_KEY = "alerts.next_id"
_LOG_KEY = "alerts.log"


class AlertManager:

    def __init__(self, store, dedup_window=300.0):
        self.kv = store if isinstance(store, KeyValueStore) else KeyValueStore(store)
        self.dedup_window = float(dedup_window)
        self._backends = {}

    # ------------------------------------------------------------------
    def _records(self):
        return dict(self.kv.get(_RECORDS_KEY, {}) or {})

    def _save_records(self, records):
        self.kv.set(_RECORDS_KEY, records)
        return records

    def _next_id(self):
        def bump(old):
            return 1 if old is None else int(old) + 1
        return self.kv.update(_COUNTER_KEY, bump, default=0)

    # ------------------------------------------------------------------
    def create(self, severity, title, message, source, dedup_key=None):
        severity = str(severity).lower()
        if severity not in SEVERITY_INDEX:
            raise ValueError(f"unknown severity: {severity!r}")
        now = time.time()

        if dedup_key is not None:
            existing = self._find_dedup(str(dedup_key))
            if existing is not None:
                existing["dedup_count"] = int(existing.get("dedup_count", 1)) + 1
                self._save_records(self._records())
                return {
                    "id": existing["id"],
                    "severity": existing["severity"],
                    "title": existing["title"],
                    "deduped": True,
                    "count": existing["dedup_count"],
                    "created": False,
                }

        records = self._records()
        alert_id = self._next_id()
        record = {
            "id": alert_id,
            "severity": severity,
            "title": title,
            "message": message,
            "source": source,
            "dedup_key": dedup_key,
            "dedup_count": 1,
            "status": "open",
            "acknowledged": False,
            "created_at": now,
            "closed_at": None,
            "notified": [],
        }
        records[alert_id] = record
        self._save_records(records)
        return {
            "id": alert_id,
            "severity": severity,
            "title": title,
            "deduped": False,
            "count": 1,
            "created": True,
        }

    def _find_dedup(self, dedup_key):
        now = time.time()
        best = None
        for record in self._records().values():
            if record.get("status") != "open":
                continue
            if record.get("dedup_key") != dedup_key:
                continue
            if now - record.get("created_at", 0) <= self.dedup_window:
                best = record
        return best

    # ------------------------------------------------------------------
    def list(self, severity=None, status=None):
        records = [record for record in self._records().values()]
        if severity is not None:
            records = [r for r in records if r["severity"] == str(severity).lower()]
        if status is not None:
            records = [r for r in records if r.get("status") == status]
        records.sort(key=lambda r: r["id"])
        return records

    def active(self):
        return [r for r in self.list() if r["status"] == "open"]

    def get(self, alert_id):
        return self._records().get(int(alert_id))

    def ack(self, alert_id):
        records = self._records()
        record = records.get(int(alert_id))
        if record is None or record["status"] != "open":
            return False
        record["acknowledged"] = True
        record["acknowledged_at"] = time.time()
        self._save_records(records)
        return True

    def close(self, alert_id):
        records = self._records()
        record = records.get(int(alert_id))
        if record is None:
            return False
        record["status"] = "closed"
        record["closed_at"] = time.time()
        self._save_records(records)
        return True

    def severity_count(self):
        counts = {name: 0 for name in SEVERITY_ORDER}
        for record in self.active():
            counts[record["severity"]] += 1
        counts["total"] = sum(counts.values())
        return counts

    # ------------------------------------------------------------------
    def channels(self):
        return ["local", "email", "push", "sms"]

    def _channel_config(self, name):
        return self.kv.get(f"alerts.channels.{name}", {}) or {}

    def configure_channel(self, name, config=None):
        self.kv.set(f"alerts.channels.{name}", dict(config or {}))
        return self.channel_status(name)

    def enable_channel(self, name, confirmed=False):
        cfg = dict(self._channel_config(name))
        if not cfg:
            return STATUS_NOT_CONFIGURED
        cfg["confirmed"] = bool(confirmed)
        self.kv.set(f"alerts.channels.{name}", cfg)
        return self.channel_status(name)

    def register_backend(self, name, backend):
        self._backends[name] = backend
        return True

    def channel_status(self, name):
        if name == "local":
            return STATUS_AVAILABLE
        cfg = self._channel_config(name)
        if not cfg:
            return STATUS_NOT_CONFIGURED
        if not cfg.get("confirmed"):
            return STATUS_REQUIRES_PERMISSION
        backend = self._backends.get(name)
        if backend is None:
            return STATUS_OFFLINE
        is_ready = getattr(backend, "is_ready", None)
        if callable(is_ready):
            try:
                if not is_ready():
                    return STATUS_REQUIRES_AUTH
            except Exception:
                return STATUS_FAILED
        return STATUS_AVAILABLE

    def _status_note(self, name, status):
        notes = {
            STATUS_NOT_CONFIGURED: "channel not configured",
            STATUS_REQUIRES_PERMISSION: "external channel requires explicit enable confirmation",
            STATUS_REQUIRES_AUTH: "backend not authenticated",
            STATUS_OFFLINE: "no verified backend reachable",
            STATUS_UNAVAILABLE: "channel unavailable",
            STATUS_FAILED: "backend failure",
        }
        return notes.get(status, "not delivered")

    # ------------------------------------------------------------------
    def _log_local(self, record):
        def append(old):
            entries = list(old or [])
            entries.append({
                "ts": time.time(),
                "channel": "local",
                "alert_id": record["id"],
                "severity": record["severity"],
                "title": record["title"],
                "message": record["message"],
                "source": record["source"],
            })
            return entries[-500:]
        self.kv.update(_LOG_KEY, append, default=[])

    def alert_log(self):
        return list(self.kv.get(_LOG_KEY, []) or [])

    def notify(self, alert_id, channels=None):
        record = self._records().get(int(alert_id))
        if record is None:
            return {
                "alert_id": int(alert_id),
                "results": {},
                "delivered_any": False,
                "error": "alert_not_found",
            }
        if record["status"] != "open":
            return {
                "alert_id": int(alert_id),
                "results": {},
                "delivered_any": False,
                "error": "alert_not_open",
            }

        targets = channels if channels is not None else self.channels()
        results = {}
        for channel in targets:
            status = self.channel_status(channel)
            if status != STATUS_AVAILABLE:
                results[channel] = {
                    "status": status,
                    "delivered": False,
                    "note": self._status_note(channel, status),
                }
                continue
            if channel == "local":
                self._log_local(record)
                results[channel] = {
                    "status": STATUS_AVAILABLE,
                    "delivered": True,
                    "note": "written to internal alert log",
                }
                continue
            backend = self._backends.get(channel)
            if backend is None:
                results[channel] = {
                    "status": STATUS_OFFLINE,
                    "delivered": False,
                    "note": "no verified backend; external delivery not claimed",
                }
                continue
            try:
                outcome = backend.send(dict(record)) or {}
                delivered = bool(outcome.get("delivered", False))
                results[channel] = {
                    "status": STATUS_AVAILABLE if delivered else STATUS_UNAVAILABLE,
                    "delivered": delivered,
                    "note": outcome.get("note", "backend result"),
                }
            except Exception as exc:
                results[channel] = {
                    "status": STATUS_FAILED,
                    "delivered": False,
                    "note": str(exc),
                }

        record["notified"].append({
            "ts": time.time(),
            "results": results,
        })
        self._save_records(self._records())
        return {
            "alert_id": int(alert_id),
            "results": results,
            "delivered_any": any(r.get("delivered") for r in results.values()),
        }


__all__ = [
    "AlertManager",
    "SEVERITY_ORDER",
    "SEVERITY_INDEX",
    "STATUS_SET",
    "STATUS_AVAILABLE",
    "STATUS_NOT_CONFIGURED",
    "STATUS_OFFLINE",
    "STATUS_REQUIRES_AUTH",
    "STATUS_REQUIRES_PERMISSION",
]