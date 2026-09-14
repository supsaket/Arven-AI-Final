"""Skill / plugin contract (row 22) — discovery, execution, isolation."""

from skills.manager import Skill, SkillManager


HTML = ("<html><body>Great facts about python programming. "
        "The language is popular. Sessions end quickly.</body></html>")
HTML_NO_RESULTS = "<html><body>hi</body></html>"


class TestWebSearch:

    def test_search_success(self, monkeypatch):
        import tools.web as web
        monkeypatch.setattr(web, "_fetch_text", lambda url: HTML)
        outcome = web.web_search("python")
        assert outcome["success"] is True
        assert outcome["count"] >= 1
        assert all(len(r) > 0 for r in outcome["results"])

    def test_search_no_results(self, monkeypatch):
        import tools.web as web
        monkeypatch.setattr(web, "_fetch_text", lambda url: HTML_NO_RESULTS)
        outcome = web.web_search("python")
        assert outcome["success"] is True
        assert outcome["count"] == 0
        assert outcome["results"] == []

    def test_search_offline(self, monkeypatch):
        import tools.web as web
        def boom(url):
            raise OSError("no network")
        monkeypatch.setattr(web, "_fetch_text", boom)
        outcome = web.web_search("python")
        assert outcome["success"] is False
        assert outcome.get("offline") is True
        assert "results" not in outcome

    def test_max_results_clamped(self, monkeypatch):
        import tools.web as web
        monkeypatch.setattr(web, "_fetch_text", lambda url: HTML)
        outcome = web.web_search("python", max_results=2)
        assert outcome["count"] <= 2


class TestFetchPage:

    def test_fetch_strips_html(self, monkeypatch):
        import tools.web as web
        monkeypatch.setattr(web, "_fetch_text", lambda url: HTML)
        outcome = web.fetch_page("example.org")
        assert outcome["success"] is True
        assert outcome["url"] == "https://example.org"
        assert "<html>" not in outcome["content"]
        assert outcome["content_length"] == len(outcome["content"])

    def test_fetch_offline(self, monkeypatch):
        import tools.web as web

        def boom(url):
            raise OSError("no network")

        monkeypatch.setattr(web, "_fetch_text", boom)
        outcome = web.fetch_page("https://example.org")
        assert outcome["success"] is False
        assert outcome.get("offline") is True