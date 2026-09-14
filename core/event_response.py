"""Real-Time Event Response (feature 92, Day 2).

A bounded reactive event bus: handlers are registered per event type with a
cooldown, ingested events are fingerprinted for dedup, matched handlers are
fired (optionally dispatching to a registered tool through an injected
invoker), and high-severity events with no handler escalate. Nothing here
executes arbitrary code — the invoker must be provided by the caller.
"""

import time
import uuid
from datetime import datetime

from core.kv import KeyValueStore


class EventResponder:

    SEVERITIES = ("info", "low", "medium", "high", "critical")

    def __init__(self, kv=None, invoker=None):
        self.kv = kv or KeyValueStore("data/event_response.json")
        self.invoker = invoker

    # ------------------------------------------------------------------
    def _now(self):
        return datetime.now().isoformat()

    def _handlers(self):
        return self.kv.get("handlers", [])

    def _save_handlers(self, handlers):
        self.kv.set("handlers", handlers)

    def _history(self):
        return self.kv.get("history", [])

    def _save_history(self, history):
        self.kv.set("history", history[-500:])

    @staticmethod
    def _fingerprint(source, event_type):
        return f"{source}|{event_type}"

    # ------------------------------------------------------------------
    def register(self, trigger, tool=None, args=None,
                 cooldown_seconds=0, severity="all", description=""):
        if not trigger or not str(trigger).strip():
            raise ValueError("trigger is required")
        if severity not in ("all",) + self.SEVERITIES:
            raise ValueError(f"unknown severity {severity}")
        handler = {
            "id": uuid.uuid4().hex[:12],
            "trigger": str(trigger).strip(),
            "tool": tool,
            "args": dict(args or {}),
            "cooldown_seconds": max(0, int(cooldown_seconds or 0)),
            "severity": severity,
            "description": str(description or ""),
            "fires": 0,
            "last_fired": None,
            "created_at": self._now(),
        }
        handlers = self._handlers()
        handlers.append(handler)
        self._save_handlers(handlers)
        return handler

    def unregister(self, handler_id):
        handlers = [h for h in self._handlers() if h["id"] != handler_id]
        removed = len(handlers) != len(self._handlers())
        self._save_handlers(handlers)
        return {"removed": removed, "handler_id": handler_id}

    def handlers(self):
        return self._handlers()

    # ------------------------------------------------------------------
    def ingest(self, source, event_type, severity="low", payload=None):
        if severity not in self.SEVERITIES:
            raise ValueError(f"unknown severity {severity}")
        source = str(source)
        event_type = str(event_type)

        fingerprint = self._fingerprint(source, event_type)
        history = self._history()
        now = time.time()
        for entry in reversed(history[-200:]):
            if entry.get("fingerprint") != fingerprint:
                continue
            if now - entry.get("at", 0) < 60:
                entry.update({"deduplicated": True, "repeated_at": now})
                self._save_history(history)
                return {"fingerprint": fingerprint, "deduplicated": True,
                        "matched": False, "action": "dedup"}

        record = {
            "fingerprint": fingerprint,
            "source": source,
            "event_type": event_type,
            "severity": severity,
            "payload": payload or {},
            "at": now,
            "iso": self._now(),
            "deduplicated": False,
        }

        handler = self._match(record)
        response = {"event_type": event_type, "source": source}
        if handler is None:
            if severity in ("high", "critical"):
                record["status"] = "escaped"
                response["status"] = "ESCALATED"
                response["message"] = "no handler; escalated for review"
            else:
                record["status"] = "unhandled"
                response["status"] = "unhandled"
                response["message"] = "no matching handler"
        else:
            fired = self._fire(handler, record, fingerprint)
            record["status"] = "handled"
            response["status"] = "handled"
            response["handler_id"] = handler["id"]
            response.update(fired)

        history.append(record)
        self._save_history(history)
        response["fingerprint"] = fingerprint
        return response

    def _match(self, record):
        for handler in reversed(self._handlers()):
            if handler["severity"] != "all" and \
                    handler["severity"] != record["severity"]:
                continue
            trigger = handler["trigger"]
            if trigger == record["event_type"] or \
                    trigger in record["event_type"]:
                if handler["cooldown_seconds"]:
                    last = handler.get("last_fired")
                    if last and time.time() - last < handler["cooldown_seconds"]:
                        continue
                return handler
        return None

    def _fire(self, handler, record, fingerprint):
        now = time.time()
        result = {"dispatched": False, "cooldown_active": False}
        tool = handler.get("tool")
        if not tool:
            result["note"] = "handler recorded; no tool dispatch"
            result["dispatched"] = True
            return result
        if self.invoker is None or not callable(self.invoker):
            result["status"] = "UNAVAILABLE"
            result["message"] = "event responder has no invoker configured"
            return result
        try:
            outcome = self.invoker(tool, dict(handler.get("args") or {}))
            if isinstance(outcome, dict):
                outcome.pop("confirmed", None)
            result.update({"dispatched": True, "tool": tool, "outcome": outcome})
        except Exception as exc:
            result.update({"dispatched": False,
                           "status": "FAILED", "message": repr(exc)})
        handler["fires"] += 1
        handler["last_fired"] = now
        self._save_handlers(self._handlers())
        return result

    # ------------------------------------------------------------------
    def history(self, limit=50):
        return list(reversed(self._history()[-int(limit):]))

    def stats(self):
        handlers = self._handlers()
        return {
            "handlers": len(handlers),
            "total_fires": sum(h.get("fires", 0) for h in handlers),
            "history_len": len(self._history()),
        }


__all__ = ["EventResponder"]