"""Scheduler / reminders (row 18) — parse, store, list, cancel, fire.

Natural-language parsing:
* one-time:  "remind me to X at 15:30" / "tomorrow at 9"
* relative:  "in 5 minutes" / "in 2 hours"   -> one-time in the future
* daily:     "every day at 8"  (daily stores recurrence, not the raw text)
* weekly:    "every monday"    (weekly stores the weekday)
* gibberish  -> "help" response, never an exception

Safety: the engine will NEVER auto-execute a destructive scheduled action —
such items are flagged and left for explicit confirmation.
"""

import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from core.safety import RISK_DESTRUCTIVE, SAFETY

BASE = Path(__file__).resolve().parent.parent

_CANCEL_PREFIX_PATTERNS = [
    r"cancel\s+my\s+", r"cancel\s+the\s+", r"remove\s+my\s+",
    r"remove\s+the\s+", r"delete\s+my\s+", r"delete\s+the\s+", r"cancel\s+",
]
_CANCEL_SUFFIX = r"\b(?:reminder|task|event|alarm|it|that|one)s?\b"


def extract_action(text):
    """Extract a scheduled action and reject destructive prefixes."""
    lowered = (text or "").lower()
    risk = SAFETY.classify_action(lowered)
    if risk == RISK_DESTRUCTIVE:
        return None, "destructive"
    return str(text or "").strip(), "ok"


class TaskStore:
    """JSON-file backed store of scheduled items."""

    def __init__(self, path=None):
        self.path = Path(path) if path else BASE / "data" / "tasks.json"
        self._lock = threading.Lock()
        self._ensure()

    def _ensure(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, tasks):
        self.path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    def add(self, task):
        with self._lock:
            tasks = self._load()
            task = dict(task)
            task.setdefault("id", str(uuid.uuid4())[:12])
            task.setdefault("status", "pending")
            task.setdefault("created_at", datetime.now().isoformat())
            tasks.append(task)
            self._save(tasks)
            return task["id"]

    def duplicate(self, other):
        with self._lock:
            for existing in self._load():
                if all(existing.get(k) == other.get(k) for k in (
                        "kind", "text", "run_at", "recurring", "weekday", "at_time")):
                    return True
            return False

    def get_all(self):
        with self._lock:
            return self._load()

    def get(self, task_id):
        with self._lock:
            for task in self._load():
                if task["id"] == task_id:
                    return task
            return None

    def mark_run(self, task_id):
        with self._lock:
            tasks = self._load()
            for task in tasks:
                if task["id"] == task_id:
                    task["status"] = "run"
                    task["run_at_epoch"] = time.time()
                    task["last_run"] = datetime.now().isoformat()
                    # daily recurrence reschedules
                    if task.get("recurring") == "daily":
                        task["status"] = "pending"
                        task["next_at"] = (datetime.now() + timedelta(days=1)).isoformat()
                    if task.get("recurring") == "weekly":
                        task["status"] = "pending"
                        task["next_at"] = (datetime.now() + timedelta(weeks=1)).isoformat()
                    self._save(tasks)
                    return True
            return False

    def cancel(self, task_id=None, description=None):
        with self._lock:
            tasks = self._load()
            original = len(tasks)
            def match(task):
                if task_id is not None:
                    return task["id"] == task_id
                if description is not None:
                    words = [w for w in description.lower().split() if len(w) > 2]
                    text = str(task.get("text", "")).lower()
                    return bool(words) and all(w in text for w in words)
                return False
            remaining = [t for t in tasks if not match(t)]
            if len(remaining) == original:
                return False
            self._save(remaining)
            return True

    def upcoming(self, limit=5, after=None):
        """Next due items (for the proactive engine)."""
        now = after or datetime.now()
        items = []
        for task in self.get_all():
            if task.get("status") not in ("pending", None):
                continue
            at = self._due_moment(task, now)
            if at is None:
                continue
            items.append({
                "id": task["id"],
                "text": task.get("text", ""),
                "summary": task.get("text", ""),
                "time": at.strftime("%Y-%m-%d %H:%M"),
                "when": at.strftime("%H:%M"),
                "kind": task.get("kind", "one_time"),
            })
        items.sort(key=lambda i: i["time"])
        return items[: limit]

    def _due_moment(self, task, now):
        if task.get("kind") == "one_time":
            try:
                return datetime.strptime(task["run_at"], "%Y-%m-%d %H:%M")
            except Exception:
                return None
        if task.get("kind") == "daily":
            try:
                hour, minute = (int(v) for v in str(task.get("at_time", "09:00")).split(":"))
                base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if base < now:
                    base = base + timedelta(days=1)
                return base
            except Exception:
                return None
        if task.get("kind") == "weekly":
            try:
                target = int(task.get("weekday", 0))
                hour, minute = (int(v) for v in str(task.get("at_time", "09:00")).split(":"))
                delta = (target - now.weekday() + 7) % 7
                base = (now + timedelta(days=delta)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0)
                if base < now:
                    base = base + timedelta(days=7)
                return base
            except Exception:
                return None
        return None


def parse(text, now=None):
    """Parse natural-language reminder text. Returns a structured task or None."""
    text = (str(text or "")).strip()
    lowered = text.lower()
    now = now or datetime.now()

    # relative minutes / hours
    relative_min = re.search(r"in\s+(\d+)\s*min", lowered)
    relative_hr = re.search(r"in\s+(\d+)\s*h(?:ou)r", lowered)
    if relative_min:
        return {"kind": "one_time",
                "run_at": (now + timedelta(minutes=int(relative_min.group(1))))
                .strftime("%Y-%m-%d %H:%M"),
                "text": _action_only(text, relative_min.group(0))}
    if relative_hr:
        return {"kind": "one_time",
                "run_at": (now + timedelta(hours=int(relative_hr.group(1))))
                .strftime("%Y-%m-%d %H:%M"),
                "text": _action_only(text, relative_hr.group(0))}

    # "tomorrow at 9am"
    tomorrow = re.search(r"tomorrow", lowered)
    explicit_today = re.search(r"today", lowered)

    time_match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", lowered)
    day_of_week = next((i for i, day in enumerate(["monday", "tuesday", "wednesday",
                                                  "thursday", "friday", "saturday", "sunday"])
                        if re.search(rf"\b{day}\b", lowered)), None)

    if day_of_week is not None:
        hour, minute, _ = _parse_clock(time_match)
        return {"kind": "weekly", "weekday": day_of_week,
                "at_time": f"{hour:02d}:{minute:02d}",
                "text": _action_only(text, None)}

    if re.search(r"\bevery\s+day\b|\bdaily\b", lowered):
        hour, minute, _ = _parse_clock(time_match)
        return {"kind": "daily", "at_time": f"{hour:02d}:{minute:02d}",
                "text": _action_only(text, None)}

    if time_match and (tomorrow or explicit_today or _has_clock_particle(lowered)):
        hour, minute, ampmflag = _parse_clock(time_match)
        target = now
        if tomorrow:
            target = now + timedelta(days=1)
        run_at = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_at <= now and not tomorrow:
            run_at = run_at + timedelta(days=1)
        return {"kind": "one_time", "run_at": run_at.strftime("%Y-%m-%d %H:%M"),
                "text": _action_only(text, time_match.group(0))}

    if tomorrow and not time_match:
        run_at = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0)
        return {"kind": "one_time", "run_at": run_at.strftime("%Y-%m-%d %H:%M"),
                "text": _action_only(text, None)}

    return None


def _has_clock_particle(lowered):
    return bool(re.search(r"\bat\b|\bam\b|\bpm\b|\ba\.m\.\b|\bp\.m\.\b", lowered))


def _parse_clock(time_match):
    if not time_match:
        return 9, 0, False
    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    suffix = (time_match.group(3) or "").lower()
    if "p" in suffix and hour < 12:
        hour += 12
    if "a" in suffix and hour == 12:
        hour = 0
    return hour, minute, bool(suffix)


def _action_only(text, token):
    """Keep the actionable part (e.g. 'water the plants'), drop scheduling words."""
    cleaned = re.sub(r"\bremind me to\b|\bremind me\b|\bremember to\b|\breminder:\s*", "",
                     text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\b(?:every\s+(?:day|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"\bdaily)\b|\btomorrow\b|\btoday\b",
        "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?\s*$"
        r"|\s+\d{1,2}:\d{2}\s*(?:am|pm)?\s*$"
        r"|\s+\d{1,2}\s*(?:am|pm)\s*$",
        "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()
    cleaned = re.sub(
        r"^(?:in\s+\d+\s*(?:min|hours?)|every\s+\d+\s+(?:minutes?|hours?))\s*",
        "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?$", "",
                     cleaned, flags=re.IGNORECASE).strip()
    if cleaned.lower().startswith("to "):
        cleaned = cleaned[3:].strip()
    return cleaned or text


class Scheduler:

    def __init__(self, store=None):
        self.store = store or TaskStore()

    # ------------------------------------------------------------------
    def schedule(self, text, now=None):
        """Parse + persist. Returns a structured response (never raises)."""
        action, verdict = extract_action(text)
        if verdict == "destructive":
            return {"success": False, "help": False,
                    "message": "Destructive scheduled actions are not allowed."}
        parsed = parse(text, now=now)
        if parsed is None:
            return {"success": False, "help": True,
                    "message": ("I couldn't parse that reminder. Try e.g. "
                                "'remind me to water the plants at 18:00', "
                                "'every day at 8am', 'every monday at 9am' or "
                                "'in 30 minutes'.")}
        parsed["text"] = _action_only(text, None) or action  # store the action text, not the timetable words
        if self.store.duplicate(parsed):
            return {"success": False, "message": "That reminder is already scheduled."}
        task_id = self.store.add(parsed)
        return {"success": True, "task_id": task_id, "task": parsed,
                "message": f"Scheduled ({parsed['kind']}): {parsed.get('text')}."}

    def list(self):
        tasks = self.store.get_all()
        return {"success": True, "count": len(tasks), "tasks": tasks}

    def cancel(self, text=None, task_id=None):
        """Cancel by id or natural description ('cancel my water plants reminder')."""
        description = None
        if text:
            lowered = (text or "").lower()
            for prefix in _CANCEL_PREFIX_PATTERNS:
                if re.match(prefix, lowered):
                    lowered = re.sub(prefix, "", lowered)
                    break
            description = re.sub(_CANCEL_SUFFIX, "", lowered).strip()
            if not description:
                description = lowered.strip()
        done = self.store.cancel(task_id=task_id, description=description)
        if not done:
            return {"success": False, "message": "No matching reminder found to cancel."}
        return {"success": True, "message": "Reminder cancelled."}


class SchedulerEngine:

    def __init__(self, store=None, notify=None, now_fn=None):
        self.store = store or TaskStore()
        self.notify = notify or (lambda task: None)
        self.now_fn = now_fn or (lambda: datetime.now())
        self.fired = []

    def due_tasks(self, now=None):
        now = now or self.now_fn()
        due = []
        for task in self.store.get_all():
            if task.get("status") not in ("pending", None):
                continue
            moment = None
            if task.get("kind") == "one_time":
                try:
                    moment = datetime.strptime(task["run_at"], "%Y-%m-%d %H:%M")
                except Exception:
                    continue
                # Only fire one-time items when their instant has been REACHED.
                if now >= moment:
                    due.append(task)
                continue
            else:
                # daily/weekly recurrence (kind is the authority; 'recurring'
                # is an optional alias kept for older stored tasks)
                recurrence = task.get("recurring") or task.get("kind")
                if recurrence not in ("daily", "weekly"):
                    continue
                if task.get("next_at"):
                    try:
                        if datetime.fromisoformat(task["next_at"]) > now:
                            continue
                    except Exception:
                        pass
                if recurrence == "daily":
                    try:
                        hour, minute = (int(v) for v in str(task.get("at_time", "09:00")).split(":"))
                        base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if base <= now and (now - base).total_seconds() < 24 * 3600:
                            due.append(task)
                    except Exception:
                        continue
                elif recurrence == "weekly":
                    try:
                        target = int(task.get("weekday", 0))
                        hour, minute = (int(v) for v in str(task.get("at_time", "09:00")).split(":"))
                        delta = (target - now.weekday() + 7) % 7
                        base = (now + timedelta(days=delta)).replace(
                            hour=hour, minute=minute, second=0, microsecond=0)
                        if base <= now and (now - base).total_seconds() < 24 * 3600:
                            due.append(task)
                    except Exception:
                        continue
        return due

    def fire(self, now=None):
        """Execute due, non-destructive tasks. Returns the fired tasks."""
        now = now or self.now_fn()
        fired = []
        for task in self.due_tasks(now):
            # Safety: never auto-execute destructive scheduled items.
            action = task.get("text", "")
            _, verdict = extract_action(action)
            if verdict == "destructive":
                self.store.mark_run(task["id"])
                fired.append({**task, "blocked_destructive": True})
                continue
            self.store.mark_run(task["id"])
            try:
                self.notify(task)
            except Exception:
                pass
            fired.append(task)
        self.fired.extend(fired)
        return fired


scheduler_store = TaskStore()
scheduler = Scheduler(scheduler_store)
scheduler_engine = SchedulerEngine(scheduler_store)

__all__ = ["TaskStore", "Scheduler", "SchedulerEngine", "parse",
           "extract_action", "scheduler_store", "scheduler", "scheduler_engine"]