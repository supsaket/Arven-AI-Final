"""Upgrade layer contract — calculator, TTS, STT cap, document detection."""

from core.upgrade import (
    ActionResolver,
    Calculator,
    DocumentDetector,
    STT_MemoryCapper,
    TTS_Sanitizer,
    guard_memory_fact,
    normalize_boss_variant,
    strip_arven_prefix,
)


class TestCalculator:

    def test_arithmetic(self):
        assert Calculator.eval_expression("2 + 3 * 4")["value"] == 14
        assert Calculator.eval_expression("10 / 2")["value"] == 5.0
        assert Calculator.eval_expression("(1 + 2) * 3")["value"] == 9

    def test_relative_double(self):
        assert Calculator.relative("double it", 50) == 100

    def test_relative_percent(self):
        assert Calculator.relative("add 10%", 200) == 210.0

    def test_empty_expression(self):
        assert Calculator.eval_expression("  ")["success"] is False

    def test_unsupported_expression_rejected(self):
        outcome = Calculator.eval_expression("import os")
        assert outcome["success"] is False


class TestTTSSanitizer:

    def test_strips_markdown(self):
        cleaned = TTS_Sanitizer.sanitize("Hello **Boss**, how *are* you?")
        assert "*" not in cleaned
        assert "**" not in cleaned

    def test_collapses_whitespace(self):
        assert TTS_Sanitizer.sanitize(" a   b ") == "a b"

    def test_abbreviation_expansion(self):
        assert "for example" in TTS_Sanitizer.sanitize("e.g. a demo")


class TestSTTCap:

    def test_short_text_unchanged(self):
        assert STT_MemoryCapper.cap("hello") == "hello"

    def test_long_text_capped(self):
        long_text = "x" * 1000
        capped = STT_MemoryCapper.cap(long_text)
        assert len(capped) <= STT_MemoryCapper.MAX_CHARS + 3
        assert capped.endswith("...")


class TestDocumentDetector:

    def test_summarize_is_document(self):
        assert DocumentDetector.is_document("summarize this file")
        assert DocumentDetector.is_document("summarise this report.docx")

    def test_actions_not_documents(self):
        assert not DocumentDetector.is_document("open the file please")
        assert not DocumentDetector.is_document("close notepad")
        assert not DocumentDetector.is_document("move the file")

    def test_extract_text_is_document(self):
        assert DocumentDetector.is_document("extract the text from resume.pdf")


class TestPrefix:

    def test_strips_arven_prefix(self):
        assert strip_arven_prefix("Hey Arven, open notepad") == "open notepad"
        assert strip_arven_prefix("Arven, what time is it") == "what time is it"
        assert strip_arven_prefix("open notepad") == "open notepad"


class TestIdentityWiring:

    def test_normalize_boss_variant(self):
        assert normalize_boss_variant("sakeet") == "Saket"

    def test_unknown_identity_still_rejected_by_guard_at_write(self):
        assert guard_memory_fact("my boss is Arvind") is None
        assert guard_memory_fact("  ") is None
        assert guard_memory_fact("the boss is saket") == "the boss is Saket"

    def test_normal_fact_passes(self):
        assert guard_memory_fact("you are a personal assistant") is not None


class TestActionResolver:

    def test_default_browser_is_a_string(self):
        browser = ActionResolver.default_browser()
        assert isinstance(browser, str)
        assert browser

    def test_resolve_unknown_app(self):
        status, name = ActionResolver.resolve("definitely-not-an-app-xyz")
        assert status == "unknown"