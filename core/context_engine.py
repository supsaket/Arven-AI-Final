"""Feature 51 — Context / Working Memory.

``ContextEngine`` keeps a persisted working-event log, current focus topics and
ephemeral claims. ``context_for(query)`` ranks relevant events with real
keyword-overlap + recency scoring and recalls long-term memories from
``memory.database.MemoryDatabase.get_all()`` when importance meets a threshold.
``decay_days`` softly downgrades (never deletes) ephemeral claims.
"""

import math
import re
import time
from datetime import datetime

from core.kv import KeyValueStore

_EVENTS_KEY = "context.events"
_FOCUS_KEY = "context.focus"
_CLAIMS_KEY = "context.claims"
_DEFAULT_PATH = "data/runtime/context_engine.json"

_HALFLIFE = 86400.0 * 2.0
_OVERLAP_WEIGHT = 2.0
_RECENCY_WEIGHT = 1.5

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for",
    "with", "is", "are", "was", "were", "it", "its", "this", "that", "these",
    "those", "we", "you", "they", "he", "she", "i", "be", "been", "have",
    "has", "had", "do", "does", "did", "not", "as", "by", "from", "so", "if",
    "then", "than", "but", "just", "about", "into", "can", "will", "would",
}


def _tokenize(text):
    return re.findall(r"[a-z0-9_]+", str(text).lower())


def _token_set(text):
    return set(_tokenize(text))


def _parse_db_ts(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        dt = datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
        return dt.timestamp()
    except (TypeError, ValueError):
        return time.time()


class ContextEngine:

    def __init__(self, path=None, memory_db=None):
        self.store = KeyValueStore(str(path) if path else _DEFAULT_PATH)
        self.memory_db = memory_db

    # ------------------------------------------------------------------
    # working memory
    # ------------------------------------------------------------------
    def _events(self):
        return list(self.store.get(_EVENTS_KEY) or [])

    def push_event(self, text, tags=None, ts=None):
        events = self._events()
        event = {
            "ts": float(ts) if ts is not None else time.time(),
            "text": str(text),
            "tags": [str(t) for t in (tags or [])],
        }
        events.append(event)
        if len(events) > 500:
            events = events[-500:]
        self.store.set(_EVENTS_KEY, events)
        return event

    def get_events(self):
        return self._events()

    def focus(self, topics):
        self.store.set(_FOCUS_KEY, [str(t) for t in (topics or [])])
        return self._focus_list()

    def get_focus(self):
        return self._focus_list()

    def _focus_list(self):
        return list(self.store.get(_FOCUS_KEY) or [])

    # ------------------------------------------------------------------
    # ephemeral claims (subject to decay)
    # ------------------------------------------------------------------
    def _claims(self):
        return list(self.store.get(_CLAIMS_KEY) or [])

    def record_claim(self, text, tags=None, strength=1.0, ts=None):
        claims = self._claims()
        claim = {
            "ts": float(ts) if ts is not None else time.time(),
            "text": str(text),
            "tags": [str(t) for t in (tags or [])],
            "strength": float(strength),
            "decayed": False,
        }
        claims.append(claim)
        if len(claims) > 500:
            claims = claims[-500:]
        self.store.set(_CLAIMS_KEY, claims)
        return claim

    def get_claims(self):
        return self._claims()

    # ------------------------------------------------------------------
    # scoring
    # ------------------------------------------------------------------
    def _score(self, tokens, text, age):
        overlap = len(tokens & _token_set(text))
        if overlap <= 0:
            return None
        recency = math.exp(-max(0.0, float(age)) / _HALFLIFE)
        return round(overlap * _OVERLAP_WEIGHT + recency * _RECENCY_WEIGHT, 4)

    def context_for(self, query, limit=10, importance_threshold=5):
        q_tokens = _token_set(query)
        if not q_tokens:
            return []
        now = time.time()
        results = []
        for event in self._events():
            text = f"{event.get('text', '')} {' '.join(event.get('tags', []))}"
            score = self._score(q_tokens, text, now - float(event.get("ts", now)))
            if score is not None:
                results.append({
                    "text": event.get("text"),
                    "score": score,
                    "source": "working",
                    "ts": event.get("ts"),
                    "tags": event.get("tags", []),
                })
        for claim in self._claims():
            if claim.get("decayed"):
                continue
            text = f"{claim.get('text', '')} {' '.join(claim.get('tags', []))}"
            score = self._score(q_tokens, text, now - float(claim.get("ts", now)))
            if score is not None:
                results.append({
                    "text": claim.get("text"),
                    "score": score,
                    "source": "working",
                    "ts": claim.get("ts"),
                    "tags": claim.get("tags", []),
                    "strength": claim.get("strength"),
                })
        if self.memory_db is not None:
            results.extend(
                self._longterm_recall(q_tokens, importance_threshold, now)
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: int(limit)]

    def _longterm_recall(self, q_tokens, importance_threshold, now):
        results = []
        try:
            rows = self.memory_db.get_all()
        except Exception:
            return results
        for row in rows:
            memory_id, content, category, memory_type, value, importance, created_at, updated_at = row
            try:
                importance = int(importance or 0)
            except (TypeError, ValueError):
                importance = 0
            if importance < int(importance_threshold):
                continue
            age = now - _parse_db_ts(updated_at)
            score = self._score(q_tokens, f"{content} {category}", age)
            if score is not None:
                results.append({
                    "text": content,
                    "score": score,
                    "source": "longterm",
                    "ts": _parse_db_ts(updated_at),
                    "importance": importance,
                    "memory_id": memory_id,
                    "category": category,
                })
        return results

    # ------------------------------------------------------------------
    # window summary
    # ------------------------------------------------------------------
    def summarize_window(self, limit=20):
        events = self._events()[-int(limit):]
        tag_counts = {}
        word_counts = {}
        for event in events:
            for tag in event.get("tags", []):
                tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
            for token in _tokenize(event.get("text", "")):
                if token in _STOPWORDS:
                    continue
                word_counts[token] = word_counts.get(token, 0) + 1
        top_keywords = [
            word for word, _ in sorted(
                word_counts.items(), key=lambda kv: (-kv[1], kv[0])
            )[:10]
        ]
        return {
            "event_count": len(events),
            "window_start": events[0]["ts"] if events else None,
            "window_end": events[-1]["ts"] if events else None,
            "tags": dict(sorted(
                tag_counts.items(), key=lambda kv: -kv[1]
            )),
            "top_keywords": top_keywords,
            "focus_topics": self._focus_list(),
            "recent": [
                {"text": e.get("text"), "ts": e.get("ts")}
                for e in events[-5:]
            ],
        }

    # ------------------------------------------------------------------
    # decay — soft downgrade, never delete
    # ------------------------------------------------------------------
    def decay_days(self, n, now=None):
        if n is None or float(n) <= 0:
            raise ValueError("decay window n must be positive")
        now = now if now is not None else time.time()
        age_limit = abs(float(n)) * 86400.0
        claims = self._claims()
        decayed = 0
        changed = False
        for claim in claims:
            age = now - float(claim.get("ts", now))
            if age > age_limit and not claim.get("decayed"):
                claim["decayed"] = True
                claim["strength"] = round(
                    float(claim.get("strength", 1.0)) * 0.3, 4
                )
                claim["decay_reason"] = f"older than {n} day(s)"
                decayed += 1
                changed = True
        if changed:
            self.store.set(_CLAIMS_KEY, claims)
        return decayed


__all__ = ["ContextEngine"]