"""Capabilities contract (row 27) — enum, fold, offline honesty, no secrets."""

from core.capabilities import (
    Capabilities,
    CapabilityProbe,
    CapabilityStatus,
    LOCAL_CAPABILITIES,
    fold,
)


class TestEnum:

    def test_values(self):
        assert CapabilityStatus.AVAILABLE.value == "available"
        assert CapabilityStatus.LIMITED.value == "limited"
        assert CapabilityStatus.NOT_CONFIGURED.value == "not_configured"
        assert CapabilityStatus.UNAVAILABLE.value == "unavailable"

    def test_str_is_value(self):
        assert str(CapabilityStatus.UNAVAILABLE) == "unavailable"


class TestFold:

    def test_worst_wins(self):
        assert fold([CapabilityStatus.AVAILABLE, CapabilityStatus.LIMITED]) == \
            CapabilityStatus.LIMITED
        assert fold([CapabilityStatus.AVAILABLE,
                     CapabilityStatus.NOT_CONFIGURED]) == CapabilityStatus.NOT_CONFIGURED
        assert fold([CapabilityStatus.AVAILABLE, CapabilityStatus.UNAVAILABLE]) == \
            CapabilityStatus.UNAVAILABLE

    def test_empty_is_available(self):
        assert fold([]) == CapabilityStatus.AVAILABLE


class TestProbe:

    def test_local_always_available_offline(self):
        probe = CapabilityProbe()
        for name in LOCAL_CAPABILITIES:
            assert probe.probe(name, offline=True) == CapabilityStatus.AVAILABLE

    def test_embeddings_not_configured(self):
        probe = CapabilityProbe()
        status = probe.probe("embeddings", offline=False)
        assert status in (CapabilityStatus.NOT_CONFIGURED, CapabilityStatus.AVAILABLE)

    def test_vision_not_configured(self):
        probe = CapabilityProbe()
        status = probe.probe("vision", offline=False)
        assert status in (CapabilityStatus.NOT_CONFIGURED, CapabilityStatus.AVAILABLE)

    def test_offline_text_unavailable(self):
        probe = CapabilityProbe()
        assert probe.probe("text", offline=True) == CapabilityStatus.UNAVAILABLE

    def test_ollama_offline_unavailable(self):
        probe = CapabilityProbe()
        status = probe.probe("ollama", offline=True)
        assert status == CapabilityStatus.UNAVAILABLE or \
            status == CapabilityStatus.NOT_CONFIGURED


class TestCapabilitiesApi:

    def test_status_never_has_error(self):
        caps = Capabilities()
        statuses = caps.status(offline=False)
        assert statuses
        assert no_error(statuses.values())

    def test_status_offline_never_success_except_local(self):
        caps = Capabilities()
        statuses = caps.status(offline=True)
        for name, status in statuses.items():
            if name in LOCAL_CAPABILITIES:
                assert status == "available"
            else:
                assert status != "available"

    def test_structured_local_available_offline(self):
        caps = Capabilities()
        structured = caps.structured(offline=True)
        for name in ("files", "memory", "scheduler", "notes"):
            assert structured[name]["available"] is True

    def test_summary_no_secrets(self):
        caps = Capabilities()
        text = caps.summary(offline=False)
        assert "api" not in text.lower()
        assert "secret" not in text.lower()
        assert "token" not in text.lower()

    def test_summary_has_entries(self):
        caps = Capabilities()
        text = caps.summary(offline=False)
        assert "files:" in text
        assert "memory:" in text


def no_error(values):
    return all(str(v) != "error" for v in values)