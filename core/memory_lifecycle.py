"""Memory lifecycle management (Day 2, feature 70).

Soft lifecycle only: importance scores decay over real time, protected and
highly-important facts are exempt, and forgetting is always a *suggestion*
with ``delete_required: False``. Nothing is ever deleted — the only writes
go through :meth:`MemoryDatabase.update` to lower importance. Lifecycle
settings persist in a KeyValueStore passed via ``kv_path``.
"""

from datetime import datetime

from core.kv import KeyValueStore
from memory.database import MemoryDatabase

PROTECT_IMPORTANCE = 8
DEFAULT_FORGET_THRESHOLD = 3
DEFAULT_MERGE_THRESHOLD = 0.5
MONTH_SECONDS = 30.44 * 86400.0

_PROTECTED_KEY = "lifecycle.protected"
_LAST_AGE_KEY = "lifecycle.last_age"


def _tokenize(text):
    import re
    import string
    words = re.findall(r"[a-z0-9']+", str(text).lower())
    return [w for w in words if w not in string.punctuation]


def _overlap(left, right):
    if not left or not right:
        return 0.0
    left_set, right_set = set(left), set(right)
    union = len(left_set | right_set) or 1
    return len(left_set & right_set) / union


def _parse_created(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.now()


class MemoryLifecycle:

    def __init__(self, db=None, kv=None, db_path="data/arven_memory.db", kv_path=None):
        self.db = db if db is not None else MemoryDatabase(db_path)
        self.kv = kv if kv is not None else KeyValueStore(kv_path or "data/memory_lifecycle.json")

    # ------------------------------------------------------------------
    def _protected_ids(self):
        return set(int(i) for i in (self.kv.get(_PROTECTED_KEY, []) or []))

    def protect(self, memory_id):
        memory_id = int(memory_id)

        def update(old):
            ids = list(old or [])
            if memory_id not in ids:
                ids.append(memory_id)
            return ids

        self.kv.update(_PROTECTED_KEY, update, default=[])
        return memory_id

    def is_protected(self, memory_id):
        return int(memory_id) in self._protected_ids()

    # ------------------------------------------------------------------
    def age(self, decay_rate):
        rate = float(decay_rate)
        rows = self.db.get_all()
        protected = self._protected_ids()
        decayed = 0
        protected_count = 0
        skipped_important = 0
        now = datetime.now()

        for row in rows:
            memory_id, content, _cat, _type, _value, importance, created_at, _updated = row
            if memory_id in protected:
                protected_count += 1
                continue
            if importance >= PROTECT_IMPORTANCE:
                skipped_important += 1
                continue
            months = max(0.0, (now - _parse_created(created_at)).total_seconds() / MONTH_SECONDS)
            new_importance = max(1, int(round(importance - rate * months)))
            if new_importance < importance:
                self.db.update(memory_id, content, importance=new_importance)
                decayed += 1

        self.kv.set(_LAST_AGE_KEY, {
            "run_at": now.isoformat(),
            "decay_rate": rate,
            "decayed": decayed,
            "protected": protected_count,
            "skipped_important": skipped_important,
        })
        return {
            "decayed": decayed,
            "protected": protected_count,
            "skipped_important": skipped_important,
        }

    # ------------------------------------------------------------------
    def candidates_for_forgetting(self, threshold=DEFAULT_FORGET_THRESHOLD):
        protected = self._protected_ids()
        candidates = []
        for row in self.db.get_all():
            memory_id, content, _cat, _type, _value, importance, created_at, _updated = row
            if memory_id in protected:
                continue
            if importance <= threshold:
                candidates.append({
                    "id": memory_id,
                    "content": content,
                    "importance": importance,
                    "created_at": created_at,
                    "delete_required": False,
                    "suggested": True,
                    "reason": "importance below forgetting threshold",
                })
        candidates.sort(key=lambda c: c["importance"])
        return candidates

    def merge_duplicates(self, threshold=DEFAULT_MERGE_THRESHOLD):
        rows = self.db.get_all()
        suggestions = []
        seen = set()
        for i in range(len(rows)):
            left = rows[i]
            left_tokens = _tokenize(left[1])
            for j in range(i + 1, len(rows)):
                right = rows[j]
                overlap = _overlap(left_tokens, _tokenize(right[1]))
                if overlap < threshold:
                    continue
                key = tuple(sorted([left[0], right[0]]))
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append({
                    "pair": [left[0], right[0]],
                    "overlap": round(overlap, 3),
                    "sources": [left[1], right[1]],
                    "draft_merged": f"{left[1]} {right[1]}",
                    "merge_required": False,
                    "action": "suggest",
                })
        suggestions.sort(key=lambda s: s["overlap"], reverse=True)
        return suggestions

    # ------------------------------------------------------------------
    def summarize(self):
        rows = self.db.get_all()
        protected = self._protected_ids()
        importances = [row[5] for row in rows]
        candidates = self.candidates_for_forgetting()
        return {
            "total": len(rows),
            "protected_count": len(protected),
            "avg_importance": round(sum(importances) / len(importances), 3) if importances else None,
            "min_importance": min(importances) if importances else None,
            "max_importance": max(importances) if importances else None,
            "last_age": self.kv.get(_LAST_AGE_KEY),
            "forgetting_candidates": {
                "count": len(candidates),
                "threshold": DEFAULT_FORGET_THRESHOLD,
                "delete_required": False,
            },
        }


__all__ = ["MemoryLifecycle"]