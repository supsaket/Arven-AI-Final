"""Semantic memory retrieval with a principled acceptance gate.

Decision rule (row 3 / test_memory_retrieval):
* accept if  semantic >= MIN_SEMANTIC_THRESHOLD (0.5)
* OR        strong keyword match (keyword_score >= KEYWORD_THRESHOLD)
* OR        exact value match against the memory value column
* otherwise reject (weak keyword AND low semantic -> rejected)

The embedder is injectable so tests may use a fake embedder; production uses
the real sentence-transformers model already used by the project.
"""

from memory.database import MemoryDatabase

MIN_SEMANTIC_THRESHOLD = 0.5
KEYWORD_THRESHOLD = 0.3


class MemoryRetrieval:

    UNSUPPORTED = False

    def __init__(self, database=None, embedder=None):
        self.database = database or MemoryDatabase()
        if embedder is self.UNSUPPORTED:
            self.embedder = None
        elif embedder is None:
            try:
                from memory.retriever import MemoryRetriever
                self._model = MemoryRetriever().model
                self.embedder = lambda texts: [
                    self._model.encode(t, normalize_embeddings=True) for t in texts]
            except Exception:
                self.embedder = None
        else:
            self.embedder = embedder

    def available(self):
        return self.embedder is not None

    # ------------------------------------------------------------------
    def _scores(self, query, rows):
        texts = [str(row[1]) for row in rows]
        if not texts:
            return []
        if self.embedder is None:
            return [0.0] * len(texts)
        try:
            vectors = self.embedder(texts)
            query_vec = self.embedder([query])[0]
            return [_dot(query_vec, v) for v in vectors]
        except Exception:
            return [0.0] * len(texts)

    def search(self, query, limit=5):
        rows = self.database.get_all()
        if not rows or not self.available():
            return []

        query_lower = str(query).lower()
        query_words = set(query_lower.split())
        semantic = self._scores(str(query), rows)

        accepted = []
        for row, sem in zip(rows, semantic):
            memory_id, content, category, memory_type, value, importance = (
                row[0], str(row[1]), row[2], row[3], row[4], row[5])
            content_lower = content.lower()
            content_words = set(content_lower.split())

            keyword_score = 0.0
            if query_words:
                keyword_score = len(query_words & content_words) / len(query_words)

            value_match = bool(value) and str(value).strip().lower() == query_lower.strip()

            if sem >= MIN_SEMANTIC_THRESHOLD:
                reason = "semantic"
            elif keyword_score >= KEYWORD_THRESHOLD:
                reason = "keyword"
            elif value_match:
                reason = "value_match"
            else:
                continue

            accepted.append({
                "id": memory_id,
                "content": content,
                "category": category,
                "memory_type": memory_type,
                "value": value,
                "importance": importance,
                "semantic_score": round(float(sem), 4),
                "keyword_score": round(float(keyword_score), 4),
                "score": round(float(sem) * 0.6 + float(keyword_score) * 0.4, 4),
                "accept_reason": reason,
            })

        accepted.sort(key=lambda m: m["score"], reverse=True)
        return accepted[: limit]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


memory_retrieval = MemoryRetrieval()

__all__ = ["MemoryRetrieval", "memory_retrieval",
           "MIN_SEMANTIC_THRESHOLD", "KEYWORD_THRESHOLD"]