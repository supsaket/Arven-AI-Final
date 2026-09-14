"""Research agent (row 12) — honest multi-source search + synthesis.

* extracts the real query (strips ``research``/``search for``/``look up``
  prefixes and trailing instructions)
* preserves per-source citations for every result
* synthesizes even without an LLM provider (rule-based answer)
* never invents results or answers when offline — messages are honest
* flags genuine numeric conflicts between disagreeing sources
"""

import re

from core.upgrade import strip_arven_prefix

_QUERY_PREFIXES = ("research ", "researched ", "look up ", "lookup ",
                   "search for ", "search", "find me information about ")
_TRAILING_INSTRUCTIONS = [
    re.compile(r"[,.:;]\s*(summarize|summarise|and summarize|and tell me|"
               r"and give me|and share|tell me about).*$", re.IGNORECASE),
    re.compile(r"\s+and\s+(summari[sz]e|tell me|give me|share)\b.*$",
               re.IGNORECASE),
]

_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?%?|\$?\d[\d,]*\.?\d*")


class ResearchAgent:

    def __init__(self, searcher=None, model_fn=None):
        self.searcher = searcher or self._default_searcher
        self.model_fn = model_fn  # injectable synthesis provider (or None)

    # ------------------------------------------------------------------
    @staticmethod
    def extract_query(request):
        text = strip_arven_prefix(request).strip()
        for prefix in _QUERY_PREFIXES:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break
        for pattern in _TRAILING_INSTRUCTIONS:
            text = pattern.sub("", text).strip()
        text = text.strip(" .").strip()
        return text

    # ------------------------------------------------------------------
    def _default_searcher(self, query):
        from tools.web import web_search
        return web_search(query=query)

    def search(self, query=None, request=None):
        if query is None:
            query = self.extract_query(request)
        if not query:
            return {"success": False, "message": "no query to search",
                    "query": query, "results": []}
        try:
            outcome = self.searcher(query)
        except Exception as exc:
            return {"success": False, "message": f"search failed: {exc}",
                    "query": query, "results": [], "offline": True}
        raw = outcome.get("results", outcome.get("items", []))
        results = []
        for index, item in enumerate(raw, start=1):
            if isinstance(item, str):
                results.append({"title": item, "url": "", "snippet": "",
                                "source": f"Source {index}"})
                continue
            results.append({
                "title": item.get("title", f"Result {index}"),
                "url": item.get("url", item.get("link", "")),
                "snippet": item.get("snippet", item.get("snippet_text", "")),
                "source": f"Source {index}",
            })
        if not results and any(k in str(outcome).lower() for k in
                               ("offline", "unreachable", "timeout", "no network")):
            return {"success": False, "message": "search unavailable offline",
                    "offline": True, "query": query, "results": []}
        return {"success": bool(results), "query": query, "results": results}

    # ------------------------------------------------------------------
    @staticmethod
    def _rule_based_synthesis(query, results):
        pieces = [f"Searching for '{query}' returned {len(results)} sources."]
        for result in results:
            snippet = result.get("snippet", "") or result.get("title", "")
            if snippet:
                pieces.append(f"[{result['source']}] {snippet.strip()}")
        return "\n".join(pieces)

    def synthesize(self, query, results, model_fn=None):
        if not results:
            return {"answer": "No results were found for that query.",
                    "sources": [], "rule_based": True, "success": True}
        provider = model_fn or self.model_fn
        conflicts = self.conflicts(query, results)
        try:
            if provider is not None:
                summary = provider(query, results)
                answer = summary or self._rule_based_synthesis(query, results)
            else:
                answer = self._rule_based_synthesis(query, results)
        except Exception:
            answer = self._rule_based_synthesis(query, results)
        return {"answer": answer,
                "sources": [r["source"] for r in results],
                "conflicts": conflicts, "rule_based": provider is None,
                "success": True}

    # ------------------------------------------------------------------
    def conflicts(self, query, results):
        """Real numeric disagreements across sources (empty when none)."""
        claims = {}
        for result in results:
            snippet = (result.get("snippet", "") or result.get("title", "")).lower()
            source = result.get("source", "") or result.get("title", "unknown")
            for number in _NUMBER_RE.findall(snippet):
                claims.setdefault(number, set()).add(source)
        conflicts = []
        numbers = list(claims)
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                if claims[numbers[i]] & claims[numbers[j]]:
                    continue
                if ResearchAgent._numeric_close(numbers[i], numbers[j]):
                    continue
                left, right = claims[numbers[i]], claims[numbers[j]]
                if left & right:
                    continue
                if len(left | right) < 2:
                    continue
                conflicts.append({
                    "value_a": numbers[i], "value_b": numbers[j],
                    "sources_a": sorted(left), "sources_b": sorted(right)})
        return conflicts

    @staticmethod
    def _numeric_close(a, b):
        try:
            fa = float(a.replace(",", "").replace("%", "").replace("$", ""))
            fb = float(b.replace(",", "").replace("%", "").replace("$", ""))
            return abs(fa - fb) < 1e-6
        except ValueError:
            return False

    # ------------------------------------------------------------------
    def report(self, request=None, query=None):
        found = self.search(query=query, request=request)
        if not found.get("success") and found.get("offline"):
            message = found.get("message", "no results while offline")
            return {"success": False, "query": found.get("query"),
                    "answer": f"Research is unavailable right now: {message}",
                    "offline": True, "sources": []}
        synthesis = self.synthesize(found["query"], found["results"])
        return {"success": bool(found["results"]), "query": found["query"],
                "answer": synthesis["answer"], "sources": synthesis["sources"],
                "results": found["results"], "conflicts": synthesis["conflicts"]}


research_agent = ResearchAgent()

__all__ = ["ResearchAgent", "research_agent"]