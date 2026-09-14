"""Events & Important Dates (Day 2, feature 92).

Real datetime arithmetic for upcoming filtering, recurring events with
day/month/year rollover, overlap detection between events, reminders due, and
a minimal RFC5545-style export written to Output/Events.
"""

import uuid
from datetime import datetime, timedelta

from core.kv import KeyValueStore
from core.output import output_manager

RECURRING = ("daily", "weekly", "monthly", "yearly", "none")


class EventsCalendar:

    def __init__(self, kv=None, now_fn=None):
        self.kv = kv or KeyValueStore("data/events.json")
        self._now = now_fn or (lambda: datetime.now())

    # ------------------------------------------------------------------
    def _events(self):
        return self.kv.get("events", {})

    def add(self, title, date_iso, time=None, reminder_offset_min=0,
            recurring="none"):
        if recurring not in RECURRING:
            raise ValueError(f"invalid recurring '{recurring}'; "
                             f"allowed: {RECURRING}")
        when = _parse_date(date_iso)
        if time:
            hour, minute = _parse_time(time)
            when = when.replace(hour=hour, minute=minute)
        event = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "date": when.strftime("%Y-%m-%d"),
            "time": when.strftime("%H:%M"),
            "timestamp": when.isoformat(),
            "reminder_offset_min": int(reminder_offset_min),
            "recurring": recurring,
        }
        events = self._events()
        events[event["id"]] = event
        self.kv.set("events", events)
        return event

    def list(self):
        events = list(self._events().values())
        events.sort(key=lambda e: e["timestamp"])
        return events

    def get(self, event_id):
        return self._events().get(event_id)

    # ------------------------------------------------------------------
    def upcoming(self, days=7, now=None):
        now = now or self._now()
        horizon = now + timedelta(days=int(days))
        found = []
        for event in self.list():
            instances = self._occurrences(event, now, horizon)
            for when in instances:
                if now <= when <= horizon:
                    found.append(dict(event, timestamp=when.isoformat()))
        found.sort(key=lambda e: e["timestamp"])
        return found

    def _occurrences(self, event, start, horizon):
        base = datetime.fromisoformat(event["timestamp"])
        rule = event["recurring"]
        if rule == "none":
            return [base] if start <= base <= horizon else []
        found = []
        candidate = (base + timedelta(days=1)).replace(hour=0, minute=0)
        guard = 0
        offset = base - base.replace(hour=0, minute=0)
        while candidate <= horizon and guard < 366 * 4:
            if _matches_rule(base, candidate, rule):
                occurrence = candidate + offset
                if start <= occurrence <= horizon:
                    found.append(occurrence)
            candidate += timedelta(days=1)
            guard += 1
        return found

    # ------------------------------------------------------------------
    def reminders_due(self, now=None):
        now = now or self._now()
        due = []
        for event in self.upcoming(days=1, now=now):
            rem = datetime.fromisoformat(event["timestamp"]) - \
                timedelta(minutes=event["reminder_offset_min"])
            if rem <= now:
                due.append(event)
        return due

    # ------------------------------------------------------------------
    def conflicts(self, date, time=None, day_window=0):
        """Return events overlapping the given date (or time slot)."""
        target_date = _parse_date(date)
        conflicts = []
        for event in self.list():
            event_date = datetime.fromisoformat(event["timestamp"])
            if event_date.date() == target_date.date():
                conflicts.append(event)
            else:
                if day_window:
                    start = target_date - timedelta(days=day_window)
                    end = target_date + timedelta(days=day_window)
                    for occ in self._occurrences(event, start, end):
                        if occ.date() == target_date.date():
                            conflicts.append(event)
                            break
        return conflicts

    # ------------------------------------------------------------------
    def export(self, directory=None):
        target = directory or "Output/Events"
        lines = ["BEGIN:VCALENDAR",
                 "VERSION:2.0",
                 "PRODID:-//ARVEN//Events//EN"]
        for event in self.list():
            local = datetime.fromisoformat(event["timestamp"])
            dtstamp = self._now().strftime("%Y%m%dT%H%M%S")
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{event['id']}@arven",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{local.strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{event['title']}",
                f"RRULE:{_rrule(event['recurring'], local)}",
                "END:VEVENT",
                "END:VCALENDAR",
            ])
        content = "\n".join(lines) + "\n"
        result = output_manager.write(target, "events.ics", content)
        return {"path": result["path"], "text": content}


def _parse_date(date_iso):
    return datetime.strptime(str(date_iso), "%Y-%m-%d")


def _parse_time(value):
    parts = str(value).split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return hour, minute


def _matches_rule(base, candidate, rule):
    if rule == "daily":
        return True
    if rule == "weekly":
        return candidate.weekday() == base.weekday()
    if rule == "monthly":
        return candidate.day == base.day
    if rule == "yearly":
        return candidate.month == base.month and candidate.day == base.day
    return False


def _rrule(rule, dt):
    if rule == "daily":
        return "FREQ=DAILY"
    if rule == "weekly":
        return "FREQ=WEEKLY"
    if rule == "monthly":
        return "FREQ=MONTHLY"
    if rule == "yearly":
        return "FREQ=YEARLY"
    return "FREQ=NONE"


__all__ = ["EventsCalendar", "RECURRING"]