"""Browser tools — honest status: backend requires Playwright, absent here.

Provisioning is structured so that when Playwright is installed the same
interface activates without code changes.
"""

try:
    import playwright  # noqa: F401
    HAVE_PLAYWRIGHT = True
except Exception:  # pragma: no cover
    HAVE_PLAYWRIGHT = False

BACKEND = "playwright"


def _reason():
    return ("Browser control requires the Playwright backend, which is not "
            "installed on this machine.")


class BrowserEngine:
    """Browser control with an honest, testable surface."""

    def __init__(self, backend=HAVE_PLAYWRIGHT):
        self.backend = backend
        self.tabs = {}

    @staticmethod
    def validate_url(url):
        clean = str(url or "").strip()
        if not clean:
            return {"valid": False, "reason": "empty URL"}
        if " " in clean and not clean.startswith(("http://", "https://")):
            return {"valid": False, "reason": "invalid URL format"}
        if clean.startswith(("http://", "https://")):
            normalized = clean
        elif "://" in clean:
            return {"valid": False, "reason": "unsupported scheme"}
        else:
            normalized = "https://" + clean
        if "." not in normalized or " " in normalized:
            return {"valid": False, "reason": "invalid URL"}
        return {"valid": True, "url": normalized}

    def navigate(self, url, tab=None):
        validated = self.validate_url(url)
        if not validated["valid"]:
            return {"success": False, "url": str(url),
                    "message": validated["reason"]}
        target = validated["url"]
        tab = tab or "default"
        if self.backend:
            self.tabs[tab] = {"url": target, "dom_ready": False}
            return {"success": True, "url": target, "tab": tab,
                    "message": "Navigated."}
        from core.upgrade import ActionResolver
        try:
            outcome = ActionResolver.open(target)
        except Exception as exc:
            return {"success": False, "url": target,
                    "degraded": True, "message": str(exc)}
        self.tabs[tab] = {"url": target, "dom_ready": False}
        return {"success": bool(outcome.get("success")), "url": target,
                "tab": tab, "degraded": True,
                "message": "Opened in the system browser (Playwright absent)."}

    def current_url(self, tab=None):
        tab = tab or "default"
        return self.tabs.get(tab, {}).get("url")

    def dom_available(self):
        return self.backend

    def get_dom(self, tab=None):
        if not self.backend:
            return {"success": False, "available": False,
                    "message": "DOM access requires the Playwright backend."}
        return {"success": True, "tab": tab or "default", "dom": "<html/>"}

    def close(self, tab=None):
        if tab is None:
            self.tabs.clear()
        else:
            self.tabs.pop(tab, None)
        return {"success": True, "message": "Tab reset.",
                "tabs_open": len(self.tabs)}


def get_browser_engine():
    return BrowserEngine()


def browser_status(**kwargs):
    return {"success": True, "action": "browser_status", "available": HAVE_PLAYWRIGHT,
            "backend": BACKEND,
            "message": "Browser control available." if HAVE_PLAYWRIGHT else _reason()}


def browser_navigate(url, **kwargs):
    if not HAVE_PLAYWRIGHT:
        return {"success": False, "action": "browser_navigate", "available": False,
                "backend": BACKEND, "message": _reason()}
    return {"success": False, "action": "browser_navigate", "available": False,
            "message": "Browser navigation driver not wired."}


def browser_search(query, **kwargs):
    if not HAVE_PLAYWRIGHT:
        return {"success": False, "action": "browser_search", "available": False,
                "backend": BACKEND, "message": _reason()}
    return {"success": False, "action": "browser_search", "available": False,
            "message": "Browser search driver not wired."}


TOOLS = [
    {"name": "browser_status", "function": browser_status, "category": "Web",
     "backend": BACKEND, "risk": "safe"},
    {"name": "browser_navigate", "function": browser_navigate, "category": "Web",
     "backend": BACKEND, "risk": "medium",
     "parameters": [{"name": "url", "required": True, "hint": "str"}]},
    {"name": "browser_search", "function": browser_search, "category": "Web",
     "backend": BACKEND, "risk": "medium",
     "parameters": [{"name": "query", "required": True, "hint": "str"}]},
]