"""Browser engine contract (row 11/13) — URL validation, degradation, DOM."""

from tools.browser import BrowserEngine, get_browser_engine


class TestValidateUrl:

    def test_accepts_http(self):
        outcome = BrowserEngine.validate_url("http://example.com")
        assert outcome["valid"] is True
        assert outcome["url"] == "http://example.com"

    def test_normalizes_scheme(self):
        outcome = BrowserEngine.validate_url("example.com")
        assert outcome["valid"] is True
        assert outcome["url"] == "https://example.com"

    def test_rejects_empty(self):
        assert BrowserEngine.validate_url("")["valid"] is False
        assert BrowserEngine.validate_url(None)["valid"] is False

    def test_rejects_whitespace_garbage(self):
        assert BrowserEngine.validate_url("a b c")["valid"] is False
        assert BrowserEngine.validate_url("   ")["valid"] is False

    def test_rejects_bad_scheme(self):
        assert BrowserEngine.validate_url("ftp://x.com")["valid"] is False

    def test_rejects_no_dot(self):
        assert BrowserEngine.validate_url("localhost")["valid"] is False


class TestNavigate:

    def test_navigate_with_backend(self):
        engine = BrowserEngine(backend=True)
        outcome = engine.navigate("http://example.com")
        assert outcome["success"] is True
        assert "degraded" not in outcome
        assert engine.current_url() == "http://example.com"

    def test_navigate_bad_url_rejected_before_action(self):
        engine = BrowserEngine()
        outcome = engine.navigate("not a url at all")
        assert outcome["success"] is False

    def test_navigate_degrades_to_system_browser(self):
        engine = BrowserEngine(backend=False)
        outcome = engine.navigate("example.com")
        assert outcome["degraded"] is True
        assert engine.current_url() == "https://example.com"


class TestDom:

    def test_dom_truthfully_unavailable(self):
        engine = BrowserEngine(backend=False)
        assert engine.dom_available() is False
        outcome = engine.get_dom()
        assert outcome["available"] is False

    def test_dom_available_with_backend(self):
        engine = BrowserEngine(backend=True)
        assert engine.dom_available() is True


class TestTabs:

    def test_tab_state_abstract(self):
        engine = BrowserEngine(backend=True)
        engine.navigate("http://a.com", tab="t1")
        engine.navigate("http://b.com", tab="t2")
        assert engine.current_url("t1") == "http://a.com"
        assert engine.current_url("t2") == "http://b.com"

    def test_close_resets(self):
        engine = BrowserEngine(backend=True)
        engine.navigate("http://a.com", tab="t1")
        engine.close()
        assert engine.current_url("t1") is None
        assert engine.tabs == {}


class TestAccessor:

    def test_get_browser_engine(self):
        assert isinstance(get_browser_engine(), BrowserEngine)