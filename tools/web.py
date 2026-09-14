"""Web tools — web search + page fetch using only the Python standard library.

requests / duckduckgo_search / bs4 are absent from the reference environment,
so retrieval uses ``urllib`` with a real DuckDuckGo HTML search endpoint and a
plain-HTML text extractor. Results are real and honest: network errors return
an explicit offline/unavailable status (never fake results).
"""

import html
import re
import socket
import time
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT = 12


def _open(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data


def _fetch_text(url, timeout=TIMEOUT):
    data = _open(url, timeout=timeout)
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return html.unescape(data.decode("latin-1", errors="replace"))


_TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.IGNORECASE | re.DOTALL)
_SPACE_RE = re.compile(r"\s+")


def _strip_html(segment):
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", segment)).strip()


def _closest_duckduckgo(html_text, query):
    """Best-effort extraction of top-ish result lines from DuckDuckGo HTML."""
    text = _strip_html(html_text)
    results = []
    for line in text.split("."):
        line = line.strip()
        if not line or len(line) < 8 or len(line) > 400:
            continue
        low = line.lower()
        if ("duckduckgo" in low or "anon" in low or "privacy" in low
                or "settings" in low or "search" in low or "javascript" in low):
            continue
        results.append(line)
    if not results:
        return []
    return results[:5]


def web_search(query, max_results=5, **kwargs):
    """Real search over DuckDuckGo. Network failure => offline status."""
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(str(query))
        text = _fetch_text(url)
        lines = _closest_duckduckgo(text, str(query))
        if not lines:
            return {"success": True, "action": "web_search", "query": str(query),
                    "results": [], "count": 0,
                    "message": "No results found for the query."}
        results = lines[: max(1, int(max_results))]
        return {"success": True, "action": "web_search", "query": str(query),
                "results": results, "count": len(results),
                "message": f"Search completed with {len(results)} result(s)."}
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return {"success": False, "action": "web_search", "backend": "urllib",
                "available": False, "query": str(query),
                "message": "Web search unavailable — no network connection.",
                "offline": True}
    except Exception as exc:
        return {"success": False, "action": "web_search", "message": f"web_search error: {exc}"}


def fetch_page(url, max_chars=4000, **kwargs):
    """Fetch and strip a web page into plain text."""
    url = str(url).strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        text = _fetch_text(url)
        text = _strip_html(text)
        text = text[: max(1, int(max_chars))]
        return {"success": True, "action": "fetch_page", "url": url,
                "content": text, "content_length": len(text),
                "message": "Page fetched."}
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return {"success": False, "action": "fetch_page", "url": url,
                "backend": "urllib", "available": False,
                "message": "Fetch unavailable — no network connection.",
                "offline": True}
    except Exception as exc:
        return {"success": False, "action": "fetch_page", "message": f"fetch_page error: {exc}"}


TOOLS = [
    {"name": "web_search", "function": web_search, "category": "Web", "backend": "urllib",
     "risk": "safe",
     "parameters": [{"name": "query", "required": True, "hint": "str"},
                    {"name": "max_results", "required": False, "hint": "int"}]},
    {"name": "fetch_page", "function": fetch_page, "category": "Web", "backend": "urllib",
     "risk": "safe",
     "parameters": [{"name": "url", "required": True, "hint": "str"},
                    {"name": "max_chars", "required": False, "hint": "int"}]},
]