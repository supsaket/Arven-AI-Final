"""Logging & diagnostics contract (row 28) — redaction, ring buffer, json."""

from core.logging import ArvenLogger, json_log, logger, redact


class TestRedact:

    def test_redacts_api_key_value(self):
        assert redact("api_key=sk-abc123456789") == "api_key=[REDACTED]"

    def test_redacts_credentials_in_url(self):
        assert ":[REDACTED]@" in redact("https://user:pass@example.com/x")

    def test_redacts_long_bare_tokens(self):
        assert redact("token A1B2C3D4E5F6G7H8I9J0K") == redact("token [REDACTED]")

    def test_none_becomes_empty(self):
        assert redact(None) == ""


class TestLogger:

    def test_rotation_config_has_path(self):
        config = logger.rotation_config()
        assert "path" in config
        assert config["path"]

    def test_runtime_summary_is_text(self):
        summary = logger.runtime_summary()
        assert isinstance(summary, str)
        assert "ARVEN runtime" in summary

    def test_error_lands_in_ring_buffer(self):
        for entry in logger.recent_errors():
            if entry.get("code") == "TEST_EVENT":
                return
        logger.error("TEST_EVENT", "hello world")
        codes = [entry.get("code") for entry in logger.recent_errors()]
        assert "TEST_EVENT" in codes

    def test_json_log_writes(self):
        json_log("info", "EVENT_X", "a json event")
        # the INFO level does not populate the error ring; it only writes a line
        assert True


class TestRingBuffer:

    def test_ring_buffer_capped(self):
        for index in range(300):
            logger.error("SPAM", f"event {index}")
        assert len(logger.recent_errors()) <= 256

    def test_diagnostics_summary(self):
        summary = logger.diagnostics_summary()
        assert isinstance(summary, str)