"""Intent detection contract (row 01/04) — command routing."""

from brain.intent import (
    detect,
    detect_close_app,
    detect_identity,
    detect_memory,
    detect_open_app,
)


class TestOpen:

    def test_open_app(self):
        assert detect_open_app("open notepad") is True
        assert detect_open_app("launch calculator") is True
        assert detect_open_app("run chrome") is True

    def test_not_open(self):
        assert detect_open_app("what is the weather") is False
        assert detect_open_app("explain how motors work") is False


class TestClose:

    def test_close_app(self):
        assert detect_close_app("close notepad") is True
        assert detect_close_app("quit the browser") is True

    def test_not_close(self):
        assert detect_close_app("close enough") is False


class TestIdentity:

    def test_who_are_you(self):
        assert detect_identity("who are you") is True
        assert detect_identity("what is your name") is True

    def test_am_i_boss(self):
        assert detect_identity("am I Saket") is True


class TestMemory:

    def test_remember(self):
        assert detect_memory("remember that I like coffee") is True

    def test_what_do_you_remember(self):
        assert detect_memory("what do you remember about me") is True


class TestDetect:

    def test_routes_open(self):
        assert detect("open notepad") == "open_app"

    def test_routes_close(self):
        assert detect("close notepad") == "close_app"

    def test_routes_identity(self):
        assert detect("who are you") == "identity"

    def test_routes_memory(self):
        assert detect("remember that I like coffee") == "memory"

    def test_routes_calculate(self):
        assert detect("what is 12 times 4") == "calculate"

    def test_arven_prefix_stripped(self):
        assert detect("Hey Arven, open notepad") == "open_app"

    def test_default_chat(self):
        assert detect("tell me a joke") == "chat"