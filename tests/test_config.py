"""Config surface contract — the settings object every ARVEN component reads."""

import pytest

from config import get_settings
from config.defaults import Settings
from core import config as core_config


class TestSettingsSurface:

    def test_get_settings_returns_shared_instance(self):
        assert get_settings() is get_settings()

    def test_settings_is_settings_instance(self):
        assert isinstance(get_settings(), Settings)

    def test_required_attributes_present(self):
        s = get_settings()
        for attr in [
            "APP_TITLE",
            "APP_MIN_WIDTH",
            "APP_MIN_HEIGHT",
            "APP_WINDOW_WIDTH",
            "APP_WINDOW_HEIGHT",
            "APP_EXIT_PHRASES",
            "APP_MODE_SELECTORS",
            "APP_MODE_PROMPT",
            "APP_BYE_MESSAGE",
            "AUDIO_SETTLE_DELAY",
            "MODEL_NAME",
            "APP_NAME",
            "VERSION",
            "BOSS_NAME",
        ]:
            assert hasattr(s, attr), f"missing {attr}"

    def test_exit_phrases_contain_app_owned_phrases(self):
        phrases = get_settings().APP_EXIT_PHRASES
        assert "bye arven" in phrases
        assert "shut down arven" in phrases

    def test_exit_phrases_do_not_contain_destructive_system_phrases(self):
        s = get_settings()
        joined = " ".join(s.APP_EXIT_PHRASES)
        for destructive in ["shutdown my computer", "turn off the pc", "power off the laptop"]:
            assert destructive not in joined

    def test_mode_selectors_cover_chat_and_talk(self):
        selectors = get_settings().APP_MODE_SELECTORS
        assert "chat" in selectors
        assert "talk" in selectors
        assert "chat" in selectors["chat"]
        assert "voice" in selectors["talk"]

    def test_audio_settle_delay_default(self):
        assert get_settings().AUDIO_SETTLE_DELAY == 0.5


class TestCoreConfigBridge:

    def test_module_constants_match_settings(self):
        assert core_config.APP_NAME == "ARVEN"
        assert core_config.VERSION == "0.1.0"
        assert core_config.BOSS_NAME
        assert core_config.MODEL_NAME

    def test_settings_object_exposed(self):
        assert core_config.settings is get_settings()
        assert core_config.settings.APP_MODE_PROMPT
        assert core_config.settings.MODEL_NAME