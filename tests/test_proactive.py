"""Proactive engine contract (row 20) — enabled gate, quiet hours, snooze,
duplicate prevention, provider isolation."""

from datetime import datetime

from core.proactive import ProactiveEngine
from config import get_settings


class FakeSettings:
    """Settings compatible with settings.get(name, default)."""
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, name, default=None):
        return self._mapping.get(name, default)


class TestEnabledGate:

    def test_disabled_when_preference_off(self):
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": False}),
            providers=[],
            now_fn=lambda: datetime(2026, 9, 6, 12, 0),
        )
        assert engine.enabled is False
        assert engine.suggest() == []

    def test_disabled_when_initiative_zero(self):
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True,
                                   "PROACTIVE_INITIATIVE": 0}),
            providers=[],
            now_fn=lambda: datetime(2026, 9, 6, 12, 0),
        )
        assert engine.enabled is False

    def test_enabled_by_default_preference(self):
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[],
            now_fn=lambda: datetime(2026, 9, 6, 12, 0),
        )
        assert engine.enabled is True


class TestQuietHours:

    def test_quiet_hours_suppress_suggestions(self):
        provider = lambda now: [{"text": "suggestion", "scope": "demo", "priority": 1}]
        engine = ProactiveEngine(
            settings=FakeSettings({
                "PROACTIVE_ENABLED": True,
                "PROACTIVE_QUIET_HOURS_START_MINUTES": 22 * 60,
                "PROACTIVE_QUIET_HOURS_END_MINUTES": 6 * 60,
            }),
            providers=[provider],
            now_fn=lambda: datetime(2026, 9, 6, 23, 0),
        )
        assert engine.quiet_hours_window() is True
        assert engine.suggest() == []

    def test_outside_quiet_hours_allows_suggestions(self):
        provider = lambda now: [{"text": "suggestion", "scope": "demo", "priority": 1}]
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[provider],
            now_fn=lambda: datetime(2026, 9, 6, 15, 0),
        )
        assert engine.quiet_hours_window() is None
        assert len(engine.suggest()) == 1


class TestSnooze:

    def test_snoozed_scope_stays_quiet(self):
        provider = lambda now: [{"text": "suggestion", "scope": "demo", "priority": 1}]
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[provider],
            now_fn=lambda: datetime(2026, 9, 6, 15, 0),
        )
        assert len(engine.suggest()) == 1
        engine.snooze("demo", seconds=3600)
        assert engine.suggest() == []

    def test_resume_allows_suggestion_again(self):
        provider = lambda now: [{"text": "suggestion", "scope": "demo", "priority": 1}]
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[provider],
            now_fn=lambda: datetime(2026, 9, 6, 15, 0),
        )
        engine.snooze("demo", seconds=3600)
        engine.resume("demo")
        assert len(engine.suggest()) == 1


class TestDuplicatePrevention:

    def test_same_scope_offered_once(self):
        provider = lambda now: [{"text": "suggestion", "scope": "demo", "priority": 1}]
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[provider],
            now_fn=lambda: datetime(2026, 9, 6, 15, 0),
        )
        assert len(engine.suggest()) == 1
        assert engine.suggest() == []


class TestProviderIsolation:

    def test_bad_provider_is_isolated(self):
        bad = lambda now: (_ for _ in ()).throw(RuntimeError("boom"))
        good = lambda now: [{"text": "good", "scope": "good", "priority": 2}]
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[bad, good],
            now_fn=lambda: datetime(2026, 9, 6, 15, 0),
        )
        suggestions = engine.suggest()
        assert len(suggestions) == 1
        assert suggestions[0]["scope"] == "good"
        assert engine.stats()["provider_failures"] == 1

    def test_stats_are_exposed(self):
        provider = lambda now: [{"text": "s", "scope": "s", "priority": 1}]
        engine = ProactiveEngine(
            settings=FakeSettings({"PROACTIVE_ENABLED": True}),
            providers=[provider],
            now_fn=lambda: datetime(2026, 9, 6, 15, 0),
        )
        engine.suggest()
        assert engine.stats()["suggestions_offered"] == 1
        assert engine.status()["enabled"] is True