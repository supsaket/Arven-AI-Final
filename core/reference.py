"""Context references (row 30).

Resolve ambiguous pronouns and references against a session context:
* tracks opened and closed file/app targets
* resolves "it / that / the file / the one I opened" to real targets
* detects ambiguity between opened and closed targets that differ
* destructive + ambiguous references are flagged (caller confirms)
* ``do it again`` reuses the last opened target
* explicit commands pass through unchanged
"""

import re

_REF_SCAN = re.compile(
    r"\b(?:it|that|this|the\s+(?:file|app|one|folder|document|report|pdf|"
    r"notes?|project|image|screenshot|window)|"
    r"the\s+one\s+(?:I|we)\s+(?:opened|closed)|"
    r"the\s+(?:last|previous)\s+(?:one|file|app)|"
    r"do\s+it\s+again|again)\b",
    re.IGNORECASE,
)


class ContextReferenceManager:

    def __init__(self):
        self._opened = {}   # semantic name -> target
        self._closed = {}   # semantic name -> target
        self._last_opened = None
        self._order = []    # most-recent-first list of (kind, name, target)

    # ------------------------------------------------------------------
    def track_opened(self, target, name=None):
        semantic = str(name or target)
        self._opened[semantic] = target
        self._last_opened = target
        self._order.insert(0, ("opened", semantic, target))
        return semantic

    def track_closed(self, target, name=None):
        semantic = str(name or target)
        self._closed[semantic] = target
        self._order.insert(0, ("closed", semantic, target))
        return semantic

    def forget(self, semantic):
        self._opened.pop(semantic, None)
        self._closed.pop(semantic, None)

    # ------------------------------------------------------------------
    def _candidate_targets(self, text):
        lowered = text.lower()
        candidates = []

        if "_again_resolved" in lowered or "again" in lowered and "do it" in lowered:
            if self._last_opened is not None:
                candidates.append(self._last_opened)

        # match by name seeds: "the report file", "that code", etc.
        for token in re.findall(r"\b[a-zA-Z0-9_.\-]{2,}\b", lowered):
            if token in ("it", "that", "this", "the", "file", "app", "one",
                         "open", "close", "opened", "closed", "again", "do"):
                continue
            for semantic, target in list(self._opened.items()) + list(self._closed.items()):
                if token in str(semantic).lower():
                    candidates.append(target)

        if self._opened and ("it" in lowered or "that" in lowered or "this" in lowered):
            candidates.append(next(reversed(self._opened.values())))

        if not candidates:
            for semantic, target in list(self._closed.items()):
                candidates.append(target)

        return candidates

    def resolve(self, text):
        """Return {'status': ..., 'target': ..., 'ambiguous': bool, 'reason': str}."""
        lowered = str(text).lower()

        if " do it again" in lowered or re.search(r"do\s+it\s+again", lowered):
            if self._last_opened is not None:
                return {"status": "resolved", "target": self._last_opened,
                        "ambiguous": False,
                        "reason": "reused last opened target"}
            return {"status": "error", "target": None, "ambiguous": False,
                    "reason": "no previously opened target"}

        if not _REF_SCAN.search(lowered):
            return {"status": "explicit", "target": None, "ambiguous": False,
                    "reason": "no reference detected"}

        candidates = self._candidate_targets(lowered)
        unique = list(dict.fromkeys(str(c) for c in candidates))

        if len(unique) == 1:
            return {"status": "resolved", "target": unique[0], "ambiguous": False,
                    "reason": "single matching target"}

        if len(unique) > 1:
            return {"status": "ambiguous", "target": None, "ambiguous": True,
                    "candidates": unique,
                    "reason": "multiple targets match this reference"}

        return {"status": "error", "target": None, "ambiguous": False,
                "reason": "no target found for this reference"}


context_refs = ContextReferenceManager()

__all__ = ["ContextReferenceManager", "context_refs"]