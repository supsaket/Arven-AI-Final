"""Personal knowledge — notes + tasks (row 3 companion data).

Separate stores (notes are NOT tasks). JSON-backed, ordering new-first,
with delete/update/complete operations. Injectable directory for tests.
"""

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _now():
    return datetime.now().isoformat()


class PersonalStore:

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else BASE / "data" / "personal"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._notes_path = self.directory / "notes.json"
        self._tasks_path = self.directory / "tasks.json"
        self._ensure(self._notes_path)
        self._ensure(self._tasks_path)

    def _ensure(self, path):
        if not path.exists():
            path.write_text("[]", encoding="utf-8")

    def _load(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, path, data):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    def add_note(self, content):
        with self._lock:
            notes = self._load(self._notes_path)
            note = {"id": str(uuid.uuid4())[:12], "content": str(content),
                    "created_at": _now(), "updated_at": _now()}
            notes.append(note)
            self._save(self._notes_path, notes)
            return note["id"]

    def get_note(self, note_id):
        with self._lock:
            for note in self._load(self._notes_path):
                if note["id"] == note_id:
                    return note
            return None

    def list_notes(self):
        with self._lock:
            notes = self._load(self._notes_path)
            notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
            return notes

    def update_note(self, note_id, content):
        with self._lock:
            notes = self._load(self._notes_path)
            for note in notes:
                if note["id"] == note_id:
                    note["content"] = str(content)
                    note["updated_at"] = _now()
                    self._save(self._notes_path, notes)
                    return True
            return False

    def delete_note(self, note_id):
        with self._lock:
            notes = self._load(self._notes_path)
            remaining = [n for n in notes if n["id"] != note_id]
            if len(remaining) == len(notes):
                return False
            self._save(self._notes_path, remaining)
            return True

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def add_task(self, text, priority="normal"):
        with self._lock:
            tasks = self._load(self._tasks_path)
            task = {"id": str(uuid.uuid4())[:12], "text": str(text),
                    "priority": str(priority), "done": False,
                    "created_at": _now(), "completed_at": None}
            tasks.append(task)
            self._save(self._tasks_path, tasks)
            return task["id"]

    def list_tasks(self, include_done=True):
        with self._lock:
            tasks = self._load(self._tasks_path)
            tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
            if include_done:
                return tasks
            return [t for t in tasks if not t.get("done")]

    def pending_tasks(self):
        return self.list_tasks(include_done=False)

    def complete_task(self, task_id):
        with self._lock:
            tasks = self._load(self._tasks_path)
            for task in tasks:
                if task["id"] == task_id:
                    task["done"] = True
                    task["completed_at"] = _now()
                    self._save(self._tasks_path, tasks)
                    return True
            return False

    def delete_task(self, task_id):
        with self._lock:
            tasks = self._load(self._tasks_path)
            remaining = [t for t in tasks if t["id"] != task_id]
            if len(remaining) == len(tasks):
                return False
            self._save(self._tasks_path, remaining)
            return True


personal_store = PersonalStore()

__all__ = ["PersonalStore", "personal_store"]