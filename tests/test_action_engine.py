"""ActionEngine offline contract tests.

Uses temp dirs and mocked subprocess/webbrowser so no real app, browser or
filesystem outside the test sandbox is touched. Hardware-backed paths
(pycaw/pyautogui) are covered only for graceful-degradation behaviour.
"""

import subprocess
from pathlib import Path

import pytest

from core.action_engine import ActionEngine


@pytest.fixture
def engine(tmp_path):
    e = ActionEngine()
    e.base_dir = tmp_path
    return e


class TestResultShape:

    def test_result_returns_dict_with_action_key(self, engine):
        r = engine.execute("create folder notes")
        assert isinstance(r, dict)
        assert set(["success", "message", "action", "target"]).issubset(r.keys())

    def test_unknown_command_reports_failure(self, engine):
        r = engine.execute("turn the lights purple")
        assert r["success"] is False
        assert r["action"] is None


class TestCleanRequest:

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Please open notepad", "open notepad"),
            ("Can you open notepad", "open notepad"),
            ("Hey Arven, open notepad", "open notepad"),
            ("arven open notepad", "open notepad"),
            ("do me a favour, open notepad", "open notepad"),
            ("open notepad", "open notepad"),
        ],
    )
    def test_prefix_stripping(self, engine, raw, expected):
        assert engine.clean_request(raw) == expected


class TestFileOperations:

    def test_create_folder(self, engine, tmp_path):
        r = engine.execute("create folder myfolder")
        assert r["success"] is True
        assert (tmp_path / "myfolder").is_dir()
        assert r["action"] == "create_folder"

    def test_create_file_creates_parents(self, engine, tmp_path):
        r = engine.execute("create file docs/readme.txt")
        assert r["success"] is True
        assert (tmp_path / "docs" / "readme.txt").is_file()

    def test_create_file_existing_is_ok(self, engine, tmp_path):
        engine.execute("create file a.txt")
        r = engine.execute("create file a.txt")
        assert r["success"] is True

    def test_rename(self, engine, tmp_path):
        engine.execute("create file old.txt")
        r = engine.execute("rename old.txt to new.txt")
        assert r["success"] is True
        assert (tmp_path / "new.txt").is_file()
        assert not (tmp_path / "old.txt").exists()

    def test_rename_missing_source_fails_honestly(self, engine):
        r = engine.execute("rename ghost.txt to gone.txt")
        assert r["success"] is False

    def test_copy_item(self, engine, tmp_path):
        engine.execute("create file src.txt")
        r = engine.execute("copy src.txt to dest")
        assert r["success"] is True
        assert (tmp_path / "dest" / "src.txt").is_file()
        assert (tmp_path / "src.txt").is_file()

    def test_move_item(self, engine, tmp_path):
        engine.execute("create file src.txt")
        r = engine.execute("move src.txt to dest")
        assert r["success"] is True
        assert (tmp_path / "dest" / "src.txt").is_file()
        assert not (tmp_path / "src.txt").exists()


class TestPathSafety:

    def test_traversal_escapes_base_dir_rejected(self, engine):
        r = engine.execute("create folder ../../evil")
        assert r["success"] is False

    def test_traversal_open_rejected(self, engine):
        r = engine.execute("open ../../../../Windows/System32/notepad.exe")
        assert r["success"] is False


class TestOpenDispatch:

    def test_open_website_uses_webbrowser(self, engine, monkeypatch):
        opened = []

        def fake_open(url, new=0):
            opened.append(url)
            return True

        monkeypatch.setattr("core.action_engine.webbrowser.open", fake_open)
        r = engine.execute("open youtube")
        assert r["success"] is True
        assert opened and "youtube" in opened[0]

    def test_open_default_browser(self, engine, monkeypatch):
        opened = []

        def fake_open(url, new=0):
            opened.append(url)
            return True

        monkeypatch.setattr("core.action_engine.webbrowser.open", fake_open)
        r = engine.execute("open browser")
        assert r["success"] is True

    def test_open_two_targets(self, engine, monkeypatch):
        opened = []

        def fake_open(url, new=0):
            opened.append(url)
            return True

        monkeypatch.setattr("core.action_engine.webbrowser.open", fake_open)
        engine.websites["example.com"] = "https://example.com"
        engine.websites["example.org"] = "https://example.org"
        r = engine.execute("open example.com and example.org")
        assert r["success"] is True
        assert len(opened) == 2


class TestCloseDispatch:

    def test_close_running_app_named_target(self, engine, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr("core.action_engine.subprocess.run", fake_run)
        engine.processes["notepad"] = ["notepad.exe"]
        r = engine.execute("close notepad")
        assert r["success"] is True

    def test_close_not_running_reports_honest_failure(self, engine, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

        monkeypatch.setattr("core.action_engine.subprocess.run", fake_run)
        engine.processes["notepad"] = ["notepad.exe"]
        r = engine.execute("close notepad")
        assert r["success"] is False


class TestSearchDispatch:

    def test_search_opens_google(self, engine, monkeypatch):
        opened = []

        def fake_open(url, new=0):
            opened.append(url)
            return True

        monkeypatch.setattr("core.action_engine.webbrowser.open", fake_open)
        r = engine.execute("search python tutorials")
        assert r["success"] is True
        assert opened and "google.com/search" in opened[0]

    def test_empty_search_fails_gracefully(self, engine, monkeypatch):
        monkeypatch.setattr(
            "core.action_engine.webbrowser.open", lambda *a, **k: True
        )
        r = engine.execute("search")
        assert r["success"] is False


class TestGracefulHardwarePaths:

    def test_volume_command_returns_result_not_crash(self, engine):
        r = engine.execute("volume up")
        assert r["action"] in ("volume", None) or "message" in r

    def test_screenshot_graceful_when_unavailable(self, engine):
        r = engine.execute("screenshot")
        assert isinstance(r, dict)
        assert "message" in r