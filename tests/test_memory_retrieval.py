"""Memory retrieval contract (row 3/10) — acceptance thresholds."""

from memory.retrieval import (
    KEYWORD_THRESHOLD,
    MIN_SEMANTIC_THRESHOLD,
    MemoryRetrieval,
)


class FakeDatabase:
    def __init__(self, rows):
        self._rows = rows

    def get_all(self):
        return list(self._rows)


def make_row(content, memory_type="fact", value=""):
    return (1, content, "general", memory_type, value, 0.5,
            "2026-09-06", "2026-09-06")


def marker_embedder(marker):
    """Fake embedder: high similarity only when the marker is in BOTH sides."""
    def embed(texts):
        return [[1.0 if marker in str(t) else 0.0] for t in texts]
    return embed


class TestThresholds:

    def test_semantic_threshold_value(self):
        assert MIN_SEMANTIC_THRESHOLD == 0.5

    def test_keyword_threshold_value(self):
        assert KEYWORD_THRESHOLD == 0.3


class TestAcceptance:

    def test_semantic_accepts(self):
        db = FakeDatabase([make_row("the boss likes circuits and motors")])
        retrieval = MemoryRetrieval(database=db, embedder=marker_embedder("circuits"))
        results = retrieval.search("circuits")
        assert results, "semantic match must be accepted"
        assert results[0]["accept_reason"] == "semantic"

    def test_strong_keyword_accepts(self):
        db = FakeDatabase([make_row("we visited the miami beach")])
        retrieval = MemoryRetrieval(database=db, embedder=marker_embedder("zzz"))
        results = retrieval.search("miami")
        assert results, "strong keyword match must be accepted"

    def test_weak_keyword_low_semantic_rejected(self):
        db = FakeDatabase([make_row("we visited the miami beach")])
        retrieval = MemoryRetrieval(database=db, embedder=marker_embedder("zzz"))
        results = retrieval.search("giraffe planets")
        assert results == []

    def test_value_match_accepted(self):
        db = FakeDatabase([make_row("the boss's name", memory_type="identity",
                                    value="saket")])
        retrieval = MemoryRetrieval(database=db, embedder=marker_embedder("zzz"))
        results = retrieval.search("saket")
        assert results
        assert results[0]["accept_reason"] == "value_match"

    def test_unavailable_embedder_returns_empty(self):
        db = FakeDatabase([make_row("some fact here")])
        retrieval = MemoryRetrieval(database=db, embedder=False)
        assert retrieval.available() is False
        assert retrieval.search("any") == []