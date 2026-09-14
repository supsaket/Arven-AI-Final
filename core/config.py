"""ARVEN core configuration.

Backwards-compatible bridge: the first-generation Brain modules import module
constants here (``APP_NAME``, ``VERSION``, ``BOSS_NAME``, ``MODEL_PROVIDER``,
``MODEL_NAME``, ``DEBUG``), while the desktop shell imports the shared
``settings`` object. Both come from the canonical ``config.defaults``.
"""

from config.defaults import Settings
from config import get_settings

APP_NAME = Settings.APP_NAME
VERSION = Settings.VERSION
BOSS_NAME = Settings.BOSS_NAME
MODEL_PROVIDER = Settings.MODEL_PROVIDER
MODEL_NAME = Settings.MODEL_NAME
DEBUG = Settings.DEBUG

settings = get_settings()

__all__ = [
    "APP_NAME",
    "VERSION",
    "BOSS_NAME",
    "MODEL_PROVIDER",
    "MODEL_NAME",
    "DEBUG",
    "settings",
    "get_settings",
]