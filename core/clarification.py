"""Clarification engine (row 31).

Instead of guessing on ambiguous/underspecified requests, the Brain opens a
clarification: an id + question. The answer resumes the pending operation.

* every clarification has ``id`` and ``question``
* session-bounded: a finite number of open clarifications per session
  (no infinite ping-pong)
* detects underspecified destructive actions and missing parameters
* re-raises a ``ClarificationRequired`` so the Brain ASKS rather than guesses
"""

import threading
import time
import uuid


class ClarificationRequired(Exception):
    """Raised by the action layer when a question is needed."""

    def __init__(self, request_id, question, context=None):
        super().__init__(question)
        self.request_id = request_id
        self.question = question
        self.context = context or {}


class Clarification:
    def __init__(self, request_id, question, context=None, session=None):
        self.request_id = request_id
        self.question = question
        self.context = context or {}
        self.session = session
        self.answer = None
        self.resolved_at = None
        self.expires_at = time.monotonic() + 120

    @property
    def expired(self):
        return time.monotonic() > self.expires_at


class ClarificationEngine:

    def __init__(self, max_open=10, ttl=120):
        self._lock = threading.Lock()
        self._open = {}
        self._answered = []
        self.max_open = max_open
        self.ttl = ttl

    # ------------------------------------------------------------------
    def require(self, question, context=None):
        with self._lock:
            if len(self._open) >= self.max_open:
                # session bound — refuse to loop forever
                raise ClarificationRequired(
                    "clarification-limit", "Too many open questions — please restate your request.",
                    {"limit": self.max_open},
                )
            request_id = str(uuid.uuid4())[:12]
            item = Clarification(request_id, question, context, None)
            item.expires_at = time.monotonic() + self.ttl
            self._open[request_id] = item
            return request_id, question

    def is_pending(self, request_id):
        with self._lock:
            item = self._open.get(request_id)
            return item is not None and not item.expired

    def get(self, request_id):
        with self._lock:
            item = self._open.get(request_id)
            if item is not None and item.expired:
                del self._open[request_id]
                return None
            return item

    def answer(self, request_id, answer):
        with self._lock:
            item = self._open.get(request_id)
            if item is None:
                return False, "no such clarification"
            item.answer = answer
            item.resolved_at = time.time()
            del self._open[request_id]
            self._answered.append(item)
            return True, item.context

    def open_empty(self, request_id):
        with self._lock:
            return request_id not in self._open

    def open_questions(self):
        with self._lock:
            return [{"id": rid, "question": item.question}
                    for rid, item in self._open.items()]


def clarify(question, context=None):
    """Helper used by the Brain: ask instead of guessing."""
    return clarify_engine.require(question, context)


clarify_engine = ClarificationEngine()

__all__ = ["ClarificationEngine", "Clarification", "ClarificationRequired",
           "clarify_engine", "clarify"]