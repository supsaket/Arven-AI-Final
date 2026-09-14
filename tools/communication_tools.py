"""Communication tools — email/calendar gateway.

Real mail/calendar backends are not configured (no live account attached), so
these tools report honest NOT_CONFIGURED statuses and provide read-only
testability via a local JSON outbox (no fake sending, no fabricated data).
"""

import json
import threading
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _outbox_path():
    return BASE / "data" / "comms_outbox.json"


def _rlock():
    return threading.Lock  # placeholder removed below


def comm_status(**kwargs):
    return {"success": True, "action": "comm_status", "available": False,
            "backend": "none configured",
            "email": "none configured", "calendar": "none configured",
            "message": "Email/calendar backend is not configured on this machine."}


def _outbox():
    try:
        path = _outbox_path()
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def email_search(query, **kwargs):
    outbox = [m for m in _outbox() if str(query).lower() in m.get("subject", "").lower()
              or str(query).lower() in m.get("body", "").lower()]
    return {"success": True, "action": "email_search", "available": False,
            "backend": "none configured", "query": str(query),
            "matches": outbox, "count": len(outbox),
            "message": "No live mailbox configured — searched local outbox."}


def email_send(to, subject="", body="", **kwargs):
    if not to or not "@" in str(to):
        return {"success": False, "action": "email_send", "message": "invalid recipient email"}
    record = {
        "to": str(to), "subject": str(subject), "body": str(body),
        "sent_at": datetime.now().isoformat(), "delivered": False,
    }
    try:
        path = _outbox_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        outbox = _outbox()
        outbox.append(record)
        path.write_text(json.dumps(outbox, indent=2), encoding="utf-8")
    except Exception as exc:
        return {"success": False, "action": "email_send", "message": f"email_send error: {exc}"}
    return {"success": True, "action": "email_send", "available": False,
            "queued": True, "to": str(to),
            "message": "No live mail transport configured — message queued locally (not delivered)."}


def email_draft(to, subject, body, **kwargs):
    return {"success": True, "action": "email_draft", "to": str(to),
            "subject": str(subject), "draft": str(body),
            "message": "Draft ready (no live mail backend configured)."}


def calendar_events(day=None, **kwargs):
    target = str(day) if day is not None else date.today().isoformat()
    return {"success": True, "action": "calendar_events", "available": False,
            "backend": "none configured", "day": target, "events": [],
            "message": "No calendar integration configured."}


def calendar_create(summary, when, **kwargs):
    return {"success": False, "action": "calendar_create", "available": False,
            "backend": "none configured", "summary": str(summary), "when": str(when),
            "message": "No calendar integration configured — event not created."}


def messaging_send(recipient, text, channel="", **kwargs):
    if not recipient:
        return {"success": False, "action": "messaging_send", "message": "no recipient"}
    return {"success": False, "action": "messaging_send", "available": False,
            "backend": "none configured", "channel": str(channel) or "unknown",
            "message": "No messaging transport configured — message not sent."}


TOOLS = [
    {"name": "comm_status", "function": comm_status, "category": "Communication",
     "backend": "comms", "risk": "safe"},
    {"name": "email_search", "function": email_search, "category": "Communication",
     "backend": "comms", "risk": "low",
     "parameters": [{"name": "query", "required": True, "hint": "str"}]},
    {"name": "email_send", "function": email_send, "category": "Communication",
     "backend": "comms", "risk": "high",
     "parameters": [{"name": "to", "required": True, "hint": "str"},
                    {"name": "subject", "required": False, "hint": "str"},
                    {"name": "body", "required": False, "hint": "str"}]},
    {"name": "email_draft", "function": email_draft, "category": "Communication",
     "backend": "comms", "risk": "low",
     "parameters": [{"name": "to", "required": True, "hint": "str"},
                    {"name": "subject", "required": True, "hint": "str"},
                    {"name": "body", "required": True, "hint": "str"}]},
    {"name": "calendar_events", "function": calendar_events, "category": "Communication",
     "backend": "comms", "risk": "safe",
     "parameters": [{"name": "day", "required": False, "hint": "str"}]},
    {"name": "calendar_create", "function": calendar_create, "category": "Communication",
     "backend": "comms", "risk": "high",
     "parameters": [{"name": "summary", "required": True, "hint": "str"},
                    {"name": "when", "required": True, "hint": "str"}]},
    {"name": "messaging_send", "function": messaging_send, "category": "Communication",
     "backend": "comms", "risk": "high",
     "parameters": [{"name": "recipient", "required": True, "hint": "str"},
                    {"name": "text", "required": True, "hint": "str"},
                    {"name": "channel", "required": False, "hint": "str"}]},
]