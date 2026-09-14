"""Fact verification (Day 2, feature 71).

Local heuristics only:

* evidence presence (how many sources were supplied),
* keyword overlap between the claim and each source,
* contradiction markers (``not``, ``no``, ``never`` …) counted per source.

Verdicts are ``supported`` / ``contradicted`` / ``uncertain`` with a real
confidence in 0..1 and an evidence trace. External web verification is
honestly reported as NOT_CONFIGURED — no scraping is performed.
"""

import re
import time

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "for", "on", "in",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "this",
    "that", "with", "from", "by", "as", "at", "not", "no",
}

CONTRADICTION_MARKERS = ("not", "no", "never", "false", "deny", "denies", "incorrect", "contrary")

SUPPORT_THRESHOLD = 0.5


def _tokenize(text):
    words = re.findall(r"[a-z0-9']+", str(text).lower())
    return [w for w in words if w not in STOPWORDS]


def _keyword_overlap(claim_keywords, source_keywords):
    if not claim_keywords:
        return 0.0
    claim_set = set(claim_keywords)
    source_set = set(source_keywords)
    match = len(claim_set & source_set)
    return match / len(claim_set)


def _jaccard(left, right):
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    left_set, right_set = set(left), set(right)
    union = len(left_set | right_set) or 1
    return len(left_set & right_set) / union


class FactChecker:

    def __init__(self):
        self._audit_trail = []

    def check(self, claim, sources=None):
        sources = list(sources or [])
        claim_keywords = _tokenize(claim)
        evidence = []

        for index, source in enumerate(sources):
            source_text = str(source)
            source_keywords = _tokenize(source_text)
            stripped = re.sub(r"[^a-z ]", " ", source_text.lower())
            markers = [m for m in CONTRADICTION_MARKERS
                       if re.search(rf"\b{re.escape(m)}\b", stripped)]
            overlap = _keyword_overlap(claim_keywords, source_keywords)
            supports = overlap >= SUPPORT_THRESHOLD and not markers
            contradicts = overlap >= SUPPORT_THRESHOLD and bool(markers)
            evidence.append({
                "index": index,
                "overlap": round(overlap, 3),
                "markers": markers,
                "supports": bool(supports),
                "contradicts": bool(contradicts),
                "snippet": source_text[:200],
            })

        contradicting = [e for e in evidence if e["contradicts"]]
        supporting = [e for e in evidence if e["supports"]]

        if contradicting:
            verdict = "contradicted"
            best = max(e["overlap"] for e in contradicting)
            confidence = min(1.0, 0.6 + 0.4 * best)
        elif supporting:
            verdict = "supported"
            best = max(e["overlap"] for e in supporting)
            confidence = min(1.0, 0.5 + 0.5 * best)
        else:
            verdict = "uncertain"
            best = max([e["overlap"] for e in evidence], default=0.0)
            confidence = min(1.0, 0.1 + 0.2 * best)

        result = {
            "claim": claim,
            "verdict": verdict,
            "confidence": round(confidence, 3),
            "evidence": evidence,
            "evidence_score": round(best, 3),
            "source_count": len(sources),
        }
        self._audit_trail.append({
            "ts": time.time(),
            "claim": claim,
            "verdict": verdict,
            "confidence": result["confidence"],
            "evidence_count": len(evidence),
            "source_count": len(sources),
        })
        return result

    # ------------------------------------------------------------------
    def cross_check(self, sources):
        sources = list(sources or [])
        if not sources:
            return {"agreement": 0.0, "pairs": 0, "consistent": False, "sources": 0}
        token_sets = [_tokenize(s) for s in sources]
        pairs = 0
        total = 0.0
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                total += _jaccard(token_sets[i], token_sets[j])
                pairs += 1
        agreement = 1.0 if pairs == 0 else total / pairs
        return {
            "agreement": round(agreement, 3),
            "pairs": pairs,
            "consistent": agreement >= SUPPORT_THRESHOLD,
            "sources": len(sources),
        }

    def verify_web(self, claim):
        return {
            "status": "NOT_CONFIGURED",
            "verdict": "uncertain",
            "confidence": 0.0,
            "detail": "external web verification not configured; no scraping performed",
            "claim": claim,
        }

    def audit(self):
        external = self.verify_web("")
        return {
            "checks": list(self._audit_trail[-20:]),
            "total_checks": len(self._audit_trail),
            "external_verification": {
                "status": external["status"],
                "note": external["detail"],
            },
            "heuristics": [
                "evidence presence",
                "keyword overlap",
                "contradiction markers",
            ],
        }


__all__ = ["FactChecker"]