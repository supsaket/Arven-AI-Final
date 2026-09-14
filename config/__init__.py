"""ARVEN configuration entry point.

``get_settings()`` returns a shared :class:`config.defaults.Settings` instance
so the desktop shell, controller, input policy and Brain stay in sync.
"""

from config.defaults import Settings

_settings = None


def get_settings():
    """Return the shared ARVEN settings object."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_confirmation_settings():
    """Return settings for the confirmation/trust flow (kept for parity)."""
    return get_settings()


__all__ = ["Settings", "get_settings", "get_confirmation_settings"]