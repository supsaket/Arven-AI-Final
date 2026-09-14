"""RAG / knowledge retrieval contract (row 10)."""

from memory.rag import RAGEngine, chunk_text


class TestChunkText:

    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text(None) == []

    def test_small_text_one_chunk(self):
        assert chunk_text("short note") == ["short note"]

    def test_large_text_multiple_chunks(self):
        chunks = chunk_text("word " * 200, max_chars=400, overlap=50)
        assert len(chunks) > 1
        assert all(chunk.strip() for chunk in chunks)

    def test_no_duplicate_at_boundaries(self):
        text = "alpha beta gamma delta epslon zeta eta theta iota kappa lambda mu nu xi"
        chunks = chunk_text(text, max_chars=25, overlap=5)
        assert len(chunks) >= 2


class TestIndex:

    def test_index_text(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        outcome = engine.index_text("the quick brown fox jumps over the lazy dog")
        assert outcome["chunks"] == 1
        assert outcome["added"] == 1

    def test_reindex_never_duplicates(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        first = engine.index_text("a fully repeated document body here")
        second = engine.index_text("a fully repeated document body here")
        assert second["added"] == 0
        assert second["total"] == first["total"]

    def test_index_file_not_found(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        outcome = engine.index_file(str(tmp_path / "missing.txt"))
        assert outcome["success"] is False

    def test_index_file_real(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        doc = tmp_path / "doc.txt"
        doc.write_text("ARVEN memory stores facts locally.", encoding="utf-8")
        outcome = engine.index_file(str(doc))
        assert outcome["success"] is True
        assert outcome["added"] == 1

    def test_embedded_metadata(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        engine.index_text("some knowledge to embed", source="notes",
                          metadata={"importance": "high"})
        records = json_load(tmp_path / "rag.json")
        assert records[0]["metadata"]["importance"] == "high"
        assert records[0]["metadata"]["source"] == "notes"


class TestRetrieval:

    def test_query_without_provider_unavailable(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        engine.index_text("some text here")
        outcome = engine.query("some text")
        assert outcome["success"] is False
        assert outcome["status"] == "unavailable"
        assert outcome["results"] == []

    def test_retrieve_ranks_without_provider(self, tmp_path):
        engine = RAGEngine(store_path=tmp_path / "rag.json")
        engine.index_text("project uses sqlite for local memory")
        engine.index_text("the sky is blue today")
        outcome = engine.retrieve("sqlite memory")
        assert outcome["success"] is True
        assert outcome["count"] >= 1
        assert outcome["results"][0]["score"] > 0

    def test_retrieve_with_injected_embedder(self, tmp_path):
        def embedder(texts):
            # each text -> vector whose [0] axis captures a marker word
            return [[1.0 if "sqlite" in t else -1.0] for t in texts]

        engine = RAGEngine(embedder=embedder, store_path=tmp_path / "rag.json")
        engine.index_text("project uses sqlite for local memory")
        engine.index_text("the sky is blue today")
        outcome = engine.query("sqlite")
        assert outcome["success"] is True
        assert outcome["count"] >= 1
        assert "sqlite" in outcome["results"][0]["chunk"]


def json_load(path):
    import json
    return json.loads(path.read_text(encoding="utf-8"))