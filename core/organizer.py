"""Time / Calendar / Daily Plan / Email Digest / Reminders (feature 59).

Organizer persists its state in a KeyValueStore and provides a daily plan
builder, calendar event create/list/validate/upcoming/conflict detection,
reminders with due/fire, an email digest composer, and a weekly-review
template. External calendar sync is honestly NOT_CONFIGURED.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from core.kv import KeyValueStore

_ISO_DT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$"
)


class Organizer:

    def __init__(self, kv_path=None):
        from core.kv import KeyValueStore
        self.kv = kv_path if isinstance(kv_path, KeyValueStore) else KeyValueStore(
            kv_path if kv_path else "data/organizer.json")

    # ==================================================================
    # Daily plan builder
    # ==================================================================
    def build_daily_plan(self, tasks, day=None, start_hour=9, workday_hours=8):
        """Allocate task blocks from the earliest available slot.

        tasks: list of {title, est_minutes, deadline_iso=None, priority}.
        Returns a deterministic day layout of time blocks.
        """
        day = day or datetime.now().strftime("%Y-%m-%d")
        slots = []
        cursor = datetime.strptime(f"{day} {start_hour:02d}:00", "%Y-%m-%d %H:%M")
        day_end = cursor + timedelta(hours=workday_hours)

        # Sort by (earliest deadline, highest priority) deterministically.
        def sort_key(task):
            priority = {"high": 0, "medium": 1, "low": 2}.get(
                str(task.get("priority", "medium")).lower(), 1)
            deadline = task.get("deadline_iso") or ""
            return (priority, deadline, task.get("title", ""))

        ordered = sorted(tasks, key=sort_key)
        for task in ordered:
            minutes = int(task.get("est_minutes", 30))
            minutes = max(5, minutes)
            start = cursor
            end = start + timedelta(minutes=minutes)
            if end > day_end:
                end = day_end
            slots.append({
                "task": task.get("title", "untitled"),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "weight": minutes,
            })
            cursor = end

        return {"day": day, "slots": slots, "count": len(slots)}

    # ==================================================================
    # Calendar events
    # ==================================================================
    def _event_key(self, event_id):
        return f"calendar.{event_id}"

    def create_event(self, event_id, title, start_dt, end_dt):
        """Validate datetime format + end>start, then persist."""
        start_ok = self.validate_datetime(start_dt)
        end_ok = self.validate_datetime(end_dt)
        if not start_ok["ok"] or not end_ok["ok"]:
            return {"ok": False, "error": "invalid datetime"}
        start = datetime.fromisoformat(str(start_dt).replace(" ", "T"))
        end = datetime.fromisoformat(str(end_dt).replace(" ", "T"))
        if end <= start:
            return {"ok": False, "error": "end must be after start"}

        event = {
            "id": str(event_id),
            "title": str(title),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        self.kv.set(self._event_key(event_id), event)
        return {"ok": True, "event": event}

    def validate_datetime(self, value):
        if not _ISO_DT_RE.match(str(value)):
            return {"ok": False, "error": "datetime must be YYYY-MM-DD HH:MM(:SS)"}
        try:
            datetime.fromisoformat(str(value).replace(" ", "T"))
        except ValueError as exc:
            return {"ok": False, "error": f"invalid datetime: {exc}"}
        return {"ok": True}

    def list_events(self):
        events = []
        for key in self.kv.keys(prefix="calendar."):
            events.append(self.kv.get(key))
        events.sort(key=lambda e: e["start"])
        return events

    def upcoming(self, days=7, now=None):
        now = now or datetime.now()
        horizon = now + timedelta(days=int(days))
        return [e for e in self.list_events()
                if datetime.fromisoformat(e["end"]) >= now
                and datetime.fromisoformat(e["start"]) <= horizon]

    def conflicts(self, events=None):
        events = events if events is not None else self.list_events()
        found = []
        for i, a in enumerate(events):
            a_start = datetime.fromisoformat(a["start"])
            a_end = datetime.fromisoformat(a["end"])
            for b in events[i + 1:]:
                b_start = datetime.fromisoformat(b["start"])
                b_end = datetime.fromisoformat(b["end"])
                if a_start < b_end and b_start < a_end:
                    found.append({"a": a["id"], "b": b["id"]})
        return found

    def external_calendar_sync(self):
        """Honest: no external calendar backend configured."""
        return {"status": "NOT_CONFIGURED",
                "message": "no external calendar backend configured"}

    # ==================================================================
    # Reminders
    # ==================================================================
    def _reminder_key(self, reminder_id):
        return f"reminder.{reminder_id}"

    def create_reminder(self, reminder_id, text, due_iso):
        check = self.validate_datetime(due_iso)
        if not check["ok"]:
            return {"ok": False, "error": check["error"]}
        reminder = {
            "id": str(reminder_id),
            "text": str(text),
            "due": datetime.fromisoformat(str(due_iso).replace(" ", "T")).isoformat(),
            "fired": False,
        }
        self.kv.set(self._reminder_key(reminder_id), reminder)
        return {"ok": True, "reminder": reminder}

    def due(self, now=None):
        now = now or datetime.now()
        return [r for r in self.list_reminders()
                if not r["fired"] and datetime.fromisoformat(r["due"]) <= now]

    def list_reminders(self):
        reminders = []
        for key in self.kv.keys(prefix="reminder."):
            reminders.append(self.kv.get(key))
        reminders.sort(key=lambda r: r["due"])
        return reminders

    def fired(self, reminder_id):
        key = self._reminder_key(reminder_id)
        reminder = self.kv.get(key)
        if reminder is None:
            return {"ok": False, "error": "reminder not found"}
        reminder = dict(reminder)
        reminder["fired"] = True
        self.kv.set(key, reminder)
        return {"ok": True, "reminder": reminder}

    # ==================================================================
    # Email digest (composition only — no send)
    # ==================================================================
    def email_digest(self, reminders=None, events=None):
        reminders = reminders if reminders is not None else self.list_reminders()
        events = events if events is not None else self.list_events()

        reminder_lines = []
        for r in reminders:
            mark = "[done]" if r.get("fired") else "[due]"
            reminder_lines.append(f"- {mark} {r.get('text')} (due {r.get('due')})")

        event_lines = []
        for e in events:
            event_lines.append(f"- {e.get('start')} {e.get('title')}")

        body_lines = ["# Daily Digest", ""]
        body_lines.append(f"## Reminders ({len(reminder_lines)})")
        body_lines.extend(reminder_lines or ["- none"])
        body_lines.append("")
        body_lines.append(f"## Calendar ({len(event_lines)})")
        body_lines.extend(event_lines or ["- none"])
        body_lines.append("")
        body_lines.append("Generated by ARVEN Organizer (composition only — not sent)")

        return {
            "subject": "ARVEN Daily Digest",
            "body": "\n".join(body_lines),
            "reminder_count": len(reminder_lines),
            "event_count": len(event_lines),
        }

    # ==================================================================
    # Weekly review template
    # ==================================================================
    def weekly_review_template(self):
        return {
            "template": [
                "What went well this week?",
                "What did not go as planned?",
                "Top 3 accomplishments",
                "Blockers encountered",
                "Priorities for next week",
                "Lessons learned",
            ],
            "sections": 6,
        }


__all__ = ["Organizer"]
