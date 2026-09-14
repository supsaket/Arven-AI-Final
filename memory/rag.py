"""RAG / knowledge retrieval (row 10).

Real chunking + a persistent chunk index with embeddings.

* ``chunk_text`` — deterministic splitting (empty -> [], small -> one chunk)
* index_file ingests a document; re-indexing never duplicates chunks
* embedded metadata accompanies every chunk
* ``query`` returns unavailable when no embedding provider is configured
* ``retrieve`` ranks the most relevant chunks first
"""

import hashlib
import json
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def chunk_text(text, max_chars=800, overlap=100):
    """Split text into overlapping chunks; empty text yields no chunks."""
    if not text:
        return []
    text = str(text)
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        # try to break on whitespace near the boundary
        if end < length:
            boundary = text.rfind(" ", start + int(max_chars * 0.6), end)
            if boundary != -1:
                end = boundary
        chunks.append(text[start:end].strip())
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


class RAGEngine:

    def __init__(self, embedder=None, store_path=None):
        """embedder: callable(texts: list[str]) -> list[list[float]] (or None)."""
        self.embedder = embedder
        self._lock = threading.Lock()
        self.store_path = Path(store_path) if store_path else BASE / "data" / "rag_index.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self.store_path.write_text("[]", encoding="utf-8")

    # ------------------------------------------------------------------
    def _load(self):
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, records):
        self.store_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def index_text(self, text, source="", metadata=None):
        """Index chunked text. Returns dict with count and added."""
        chunks = chunk_text(text)
        added = 0
        with self._lock:
            records = self._load()
            existing = {r["chunk_hash"] for r in records}
            for index, chunk in enumerate(chunks):
                tag = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
                if tag in existing:
                    continue
                record = {
                    "chunk_hash": tag,
                    "chunk": chunk,
                    "source": str(source),
                    "index": index,
                    "metadata": {
                        **(metadata or {}),
                        "hash": tag,
                        "source": str(source),
                        "added_at": datetime.now().isoformat(),
                    },
                }
                if self.embedder is not None:
                    try:
                        vectors = self.embedder([chunk])
                        record["embedding"] = list(vectors[0])
                    except Exception:
                        record["embedding"] = None
                else:
                    record["embedding"] = None
                records.append(record)
                existing.add(tag)
                added += 1
            self._save(records)
        return {"chunks": len(chunks), "added": added, "total": len(records)}

    def index_file(self, path, source=None, max_chars=4000):
        """Index a real document file. File-not-found -> failure dict."""
        target = Path(path)
        if not target.exists():
            return {"success": False, "message": f"File not found: {path}"}
        try:
            content = target.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except OSError as exc:
            return {"success": False, "message": f"Could not read file: {exc}"}
        result = self.index_text(content, source=source or str(target.name))
        result["success"] = True
        result["file"] = str(target)
        return result

    # ------------------------------------------------------------------
    def _provider_available(self):
        return self.embedder is not None

    def query(self, text, top_k=5):
        """Retrieve relevant chunks. No provider -> explicit unavailable."""
        if not self._provider_available():
            return {"status": "unavailable", "success": False,
                    "message": "No embedding provider configured for RAG retrieval.",
                    "results": []}
        return self.retrieve(text, top_k=top_k)

    def retrieve(self, text, top_k=5):
        """Rank chunks by similarity to the query."""
        records = self._load()
        if not records:
            return {"success": True, "results": [], "count": 0,
                    "message": "No documents indexed yet."}
        if not self._provider_available():
            needle = str(text).lower()
            scored = [{"record": r, "score": len([w for w in needle.split()
                                                  if w in r["chunk"].lower()])}
                      for r in records]
        else:
            try:
                vectors = self.embedder([str(text)])
                query_vec = list(vectors[0])
                scored = []
                for record in records:
                    emb = record.get("embedding")
                    score = 0.0
                    if emb:
                        score = _dot(query_vec, emb)
                    else:
                        needle = str(text).lower()
                        score = sum(1 for w in needle.split() if w in record["chunk"].lower())
                    scored.append({"record": record, "score": score})
            except Exception as exc:
                return {"success": False, "message": f"retrieval error: {exc}",
                        "results": []}
        scored.sort(key=lambda s: s["score"], reverse=True)
        results = [{
            "chunk": r["record"]["chunk"],
            "source": r["record"].get("source", ""),
            "score": round(float(r["score"]), 4),
            "metadata": r["record"].get("metadata", {}),
        } for r in scored[: top_k]]
        return {"success": True, "results": results, "count": len(results),
                "message": f"Retrieved {len(results)} relevant chunk(s)."}


def _dot(a, b):
    try:
        import math
        return sum(x * y for x, y in zip(a, b)) / (
            math.sqrt(sum(x * x for x in a) + 1e-9) *
            math.sqrt(sum(y * y for y in b) + 1e-9))
    except Exception:
        return 0.0


from datetime import datetime  # noqa: E402


rag = RAGEngine()

__all__ = ["RAGEngine", "chunk_text", "rag"]