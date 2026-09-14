"""Clarification engine contract (row 31) — ask, answer, session bounds."""

from core.clarification import ClarificationEngine, ClarificationRequired, clarify


class TestClarificationEngine:

    def test_require_returns_id_and_question(self):
        engine = ClarificationEngine()
        request_id, question = engine.require("Which file?")
        assert request_id
        assert question == "Which file?"
        assert engine.is_pending(request_id) is True

    def test_answer_resolves(self):
        engine = ClarificationEngine()
        request_id, _ = engine.require("Which file?")
        ok, context = engine.answer(request_id, "report.txt")
        assert ok is True
        assert engine.is_pending(request_id) is False

    def test_unknown_answer_fails(self):
        engine = ClarificationEngine()
        ok, _ = engine.answer("missing", "x")
        assert ok is False

    def test_open_questions_listed(self):
        engine = ClarificationEngine()
        engine.require("Which file?")
        assert engine.open_questions()
        assert engine.open_questions()[0]["question"] == "Which file?"

    def test_expired_is_not_pending(self):
        engine = ClarificationEngine(ttl=1e-9)
        request_id, _ = engine.require("Which file?")
        from core.clarification import Clarification
        item = engine.get(request_id)
        assert item is None or item.expired


class TestSessionBound:

    def test_max_open_bounded(self):
        engine = ClarificationEngine(max_open=2)
        engine.require("Q1")
        engine.require("Q2")
        try:
            engine.require("Q3")
        except ClarificationRequired as exc:
            assert "limit" in exc.request_id
        else:
            raise AssertionError("expected ClarificationRequired")


class TestHelper:

    def test_clarify_returns_pair(self):
        request_id, question = clarify("Which one?")
        assert request_id
        assert question