"""BrowserProvider — Feature 39 (Automated Browsing).

Capabilities: browser_control, browser_search, browser_status, bookmarks.
Honest backend detection, real local bookmark/history store via KV.
"""

import importlib.util
import time

from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    ok,
    reject,
    probe_network,
)

CAPABILITIES = ("browser_control", "browser_search", "browser_status", "bookmarks")


class BrowserProvider(Provider):
    name = "browser"
    capabilities = CAPABILITIES
    category = "browsing"
    requires_network = False

    def __init__(self, settings=None, kv_path=None):
        super().__init__(settings)
        self._has_playwright = False
        self._backend_forced = None
        self._kv_path = kv_path
        self._kv = None
        self._init_kv()

    def _init_kv(self):
        path = self._kv_path or "data/browser_bookmarks.json"
        self._kv = KeyValueStore(path)

    # ------------------------------------------------------------------
    # Test hook
    # ------------------------------------------------------------------
    def set_backend(self, found):
        self._backend_forced = bool(found)

    def _has_backend(self):
        if self._backend_forced is not None:
            return self._backend_forced
        return importlib.util.find_spec("playwright") is not None

    # ------------------------------------------------------------------
    # check
    # ------------------------------------------------------------------
    def check(self):
        if self._has_backend():
            return self.set_status(
                STATUS_AVAILABLE,
                "playwright backend available",
                {"backend": "playwright"},
            )
        return self.set_status(
            STATUS_NOT_CONFIGURED,
            "playwright not installed; install with: pip install playwright && playwright install",
            {"backend": None, "required": "playwright"},
        )

    # ------------------------------------------------------------------
    # _cap_browser_status
    # ------------------------------------------------------------------
    def _cap_browser_status(self, **_kw):
        has = self._has_backend()
        reason = (
            "playwright backend available"
            if has
            else "playwright not installed; install with: pip install playwright && playwright install"
        )
        data = {
            "backend": "playwright" if has else None,
            "available": has,
            "reason": reason,
        }
        if has:
            return ok(reason, data=data)
        return reject(STATUS_NOT_CONFIGURED, reason, data=data)

    # ------------------------------------------------------------------
    # _cap_bookmarks — umbrella router for the `bookmarks` capability
    # ------------------------------------------------------------------
    def _cap_bookmarks(self, action=None, **kw):
        action = (action or "list").lower()
        if action == "add":
            return self._cap_bookmarks_add(**kw)
        if action == "search":
            return self._cap_bookmarks_search(**kw)
        if action in ("list", None):
            return self._cap_bookmarks_list(**kw)
        return reject(
            STATUS_NOT_CONFIGURED,
            f"unknown bookmark action: {action} (use add/list/search)",
        )

    # ------------------------------------------------------------------
    # _cap_browser_search
    # ------------------------------------------------------------------
    def _cap_browser_search(self, query=None, **_kw):
        if not self._has_backend():
            return reject(
                STATUS_NOT_CONFIGURED,
                "playwright not installed; cannot perform browser search. "
                "Install with: pip install playwright && playwright install",
            )
        if not probe_network():
            return reject(STATUS_OFFLINE, "no network; search requires connectivity")
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"https://www.google.com/search?q={query}")
                page.wait_for_load_state("domcontentloaded")
                text = page.inner_text("body")
                browser.close()
            return ok(
                f"search completed for '{query}'",
                data={"query": query, "result_text": text[:2000]},
            )
        except Exception as exc:
            return reject(STATUS_FAILED, f"browser search failed: {exc}")

    # ------------------------------------------------------------------
    # _cap_browser_control
    # ------------------------------------------------------------------
    def _cap_browser_control(self, action=None, url=None, **_kw):
        if not self._has_backend():
            return reject(
                STATUS_NOT_CONFIGURED,
                "playwright not installed; cannot control browser",
            )
        return reject(
            STATUS_NOT_CONFIGURED,
            "browser_control dispatch not yet wired to a live browser session",
        )

    # ------------------------------------------------------------------
    # Bookmarks — fully real local KV store
    # ------------------------------------------------------------------
    def _bookmarks_key(self):
        return "bookmarks"

    def _load_bookmarks(self):
        raw = self._kv.get(self._bookmarks_key(), [])
        return raw if isinstance(raw, list) else []

    def _save_bookmarks(self, bookmarks):
        self._kv.set(self._bookmarks_key(), bookmarks)

    def _cap_bookmarks_list(self, **_kw):
        bookmarks = self._load_bookmarks()
        return ok(
            f"{len(bookmarks)} bookmark(s)",
            data={"bookmarks": bookmarks},
        )

    def _cap_bookmarks_add(self, url=None, title="", tags=None, **_kw):
        if not url:
            return reject(STATUS_NOT_CONFIGURED, "url is required")
        bookmarks = self._load_bookmarks()
        entry = {
            "url": url,
            "title": title or url,
            "tags": list(tags) if tags else [],
            "created_at": time.time(),
        }
        bookmarks.append(entry)
        self._save_bookmarks(bookmarks)
        return ok("bookmark added", data={"bookmark": entry})

    def _cap_bookmarks_search(self, keyword=None, **_kw):
        if not keyword:
            return reject(STATUS_NOT_CONFIGURED, "keyword is required")
        kw = keyword.lower()
        bookmarks = self._load_bookmarks()
        matched = [
            b
            for b in bookmarks
            if kw in b.get("url", "").lower()
            or kw in b.get("title", "").lower()
            or kw in " ".join(b.get("tags", [])).lower()
        ]
        return ok(
            f"{len(matched)} bookmark(s) matching '{keyword}'",
            data={"bookmarks": matched},
        )

    def _cap_browser_bookmark_add(self, **kw):
        return self._cap_bookmarks_add(**kw)

    def _cap_browser_bookmarks_list(self, **kw):
        return self._cap_bookmarks_list(**kw)

    def _cap_browser_bookmarks_search(self, **kw):
        return self._cap_bookmarks_search(**kw)


# ---- Registration at import time ----
from core.providers.registry import providers_registry  # noqa: E402

if not providers_registry.has("browser"):
    providers_registry.register(BrowserProvider())

__all__ = ["BrowserProvider"]
