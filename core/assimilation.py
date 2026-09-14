"""Knowledge assimilation (Day 2, feature 66).

A small regex parser extracts candidate triples from natural-language chunks
using heuristic patterns with a fixed precedence:

* ``X is a kind/type of Y``     -> ``(X, kind_of, Y)``
* ``X is not Y``                -> ``(X, is_not, Y)``
* ``X is Y``                    -> ``(X, is, Y)``
* ``X has Y``                   -> ``(X, has, Y)``
* ``X does Y``                  -> ``(X, does, Y)``
* ``X depends on Y``            -> ``(X, depends_on, Y)``

Extraction is honest about its source: every triple carries the ``source_id``
and a timestamp, stored as provenance attributes on the graph nodes.
``conflicts`` reports opposite-direction pairs such as ``A is B`` vs
``A is not B`` and ``A depends_on B`` vs ``B depends_on A``.
"""

import re
import time

from core.knowledge_graph import KnowledgeGraph
from core.kv import KeyValueStore

_PATTERNS = [
    ("kind_of",
     re.compile(r"^\s*(.+?)\s+is\s+(?:a|an|the)?\s*(?:kind|type)\s+of\s+(.+?)\s*[.!?]?$", re.I)),
    ("is_not",
     re.compile(r"^\s*(.+?)\s+is\s+not\s+(.+?)\s*[.!?]?$", re.I)),
    ("is",
     re.compile(r"^\s*(.+?)\s+is\s+(.+?)\s*[.!?]?$", re.I)),
    ("has",
     re.compile(r"^\s*(.+?)\s+has\s+(.+?)\s*[.!?]?$", re.I)),
    ("does",
     re.compile(r"^\s*(.+?)\s+does\s+(.+?)\s*[.!?]?$", re.I)),
    ("depends_on",
     re.compile(r"^\s*(.+?)\s+depends\s+on\s+(.+?)\s*[.!?]?$", re.I)),
]

_TRIPLES_KEY = "assimilation.triples"


def _clean_phrase(phrase):
    cleaned = re.sub(r"\s+", " ", str(phrase).strip().strip(".,;:!?")).strip()
    cleaned = re.sub(r"^(a|an|the)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(some|any)\s+", "", cleaned, flags=re.I)
    return cleaned.strip().lower()


def _split_sentences(text):
    parts = re.split(r"[.!?]+\s*|\n+", str(text))
    return [p.strip() for p in parts if p.strip()]


class AssimilationEngine:

    def __init__(self, store):
        self.kv = store if isinstance(store, KeyValueStore) else KeyValueStore(store)
        self.graph = KnowledgeGraph(self.kv)
        self._last = None

    # ------------------------------------------------------------------
    def parse_chunk(self, chunk):
        text = str(chunk).strip()
        for predicate, pattern in _PATTERNS:
            match = pattern.match(text)
            if match:
                subject = _clean_phrase(match.group(1))
                object_ = _clean_phrase(match.group(2))
                if subject and object_:
                    return {
                        "subject": subject,
                        "predicate": predicate,
                        "object": object_,
                        "pattern": predicate,
                        "text": text,
                    }
        return None

    def _candidate_facts(self, raw_triples):
        unique = []
        seen = set()
        for triple in raw_triples:
            key = (triple["subject"], triple["predicate"], triple["object"])
            if key not in seen:
                seen.add(key)
                unique.append(triple)
        return unique

    def assimilate(self, text, source_id, chunks=True):
        ts = time.time()
        chunks_list = _split_sentences(text) if chunks else [str(text).strip()]
        raw = []
        pattern_counts = {}
        for chunk in chunks_list:
            parsed = self.parse_chunk(chunk)
            if parsed:
                raw.append(parsed)
                pattern_counts[parsed["pattern"]] = pattern_counts.get(parsed["pattern"], 0) + 1

        candidates = self._candidate_facts(raw)
        result = {
            "source_id": source_id,
            "ts": ts,
            "chunks": chunks_list,
            "candidates": candidates,
            "triples": [(c["subject"], c["predicate"], c["object"]) for c in candidates],
            "extraction": {
                "method": "regex heuristics",
                "pattern_counts": pattern_counts,
                "source_id": source_id,
                "note": "extraction is heuristic; provenance attached per triple",
            },
        }
        self._last = result
        return result

    # ------------------------------------------------------------------
    def record_triple(self, subject, predicate, object_, source_id=None, ts=None):
        ts = time.time() if ts is None else ts
        provenance = {"source_id": source_id, "assimilated_at": ts}
        self.graph.add_node(subject, "entity", attrs=dict(provenance))
        self.graph.add_node(object_, "entity", attrs=dict(provenance))
        outcome = self.graph.add_edge(subject, object_, str(predicate), weight=1.0)

        def append(old):
            return list(old or []) + [{
                "subject": subject,
                "predicate": str(predicate),
                "object": object_,
                "source_id": source_id,
                "ts": ts,
                "accepted": bool(outcome.get("added", True)),
            }]

        self.kv.update(_TRIPLES_KEY, append, default=[])
        return dict(outcome)

    def store(self, result=None, source_id=None, text=None):
        if isinstance(result, str) or text is not None:
            payload = str(result if result is not None else text)
            result = self.assimilate(payload, source_id)
        if result is None:
            return {"stored": 0, "source_id": None, "candidates": [], "graph": None}

        stored = []
        for subject, predicate, object_ in result.get("triples", []):
            outcome = self.record_triple(
                subject, predicate, object_,
                source_id=result.get("source_id"),
                ts=result.get("ts"),
            )
            stored.append({
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "accepted": outcome.get("added", True),
            })
        summary = self.graph.summarize()
        return {
            "stored": len(stored),
            "source_id": result.get("source_id"),
            "candidates": result.get("triples", []),
            "triples": stored,
            "graph": {"nodes": summary["nodes"], "edges": summary["edges"]},
        }

    # ------------------------------------------------------------------
    def _triples(self):
        return list(self.kv.get(_TRIPLES_KEY, []) or [])

    def conflicts(self):
        is_pairs = set()
        is_not_pairs = set()
        depends_pairs = set()
        for record in self._triples():
            subject, predicate, object_ = record["subject"], record["predicate"], record["object"]
            if predicate == "is":
                is_pairs.add((subject, object_))
            elif predicate == "is_not":
                is_not_pairs.add((subject, object_))
            elif predicate == "depends_on":
                depends_pairs.add((subject, object_))

        conflicts = []
        seen = set()

        def add_pair(left, right, reason):
            key = tuple(sorted([str(left), str(right)]))
            if key in seen:
                return
            seen.add(key)
            conflicts.append({
                "kind": "opposite",
                "left": left,
                "right": right,
                "reason": reason,
            })

        for pair in sorted(is_pairs):
            if pair in is_not_pairs:
                add_pair(("is",) + pair, ("is_not",) + pair, "A is B vs A is not B")
        for pair in sorted(depends_pairs):
            reverse = (pair[1], pair[0])
            if reverse in depends_pairs:
                add_pair(
                    ("depends_on",) + pair,
                    ("depends_on",) + reverse,
                    "A depends_on B vs B depends_on A",
                )
        return conflicts


__all__ = ["AssimilationEngine"]