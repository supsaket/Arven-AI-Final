"""Canonical ARVEN application settings (single source of truth).

Layered configuration:
1. Hardcoded defaults below.
2. Optional overrides from an ``.env`` file and environment variables
   (``ARVEN_<SETTING>`` / plain ``<SETTING>``).
3. A shared ``Settings`` instance exposed through ``get_settings()``.

No secrets are stored here; provider credentials are read from environment
variables at use time.
"""

import json
import os


def _env_value(name, default):
    """Return the environment override for ``name`` if present.

    Plain ``NAME`` as well as ``ARVEN_NAME`` are honoured so tools can run
    inside an .env loader too.
    """
    for key in (name, f"ARVEN_{name}"):
        if key in os.environ:
            return os.environ[key]
    return default


class Settings:
    """Runtime configuration for ARVEN.

    Plain attribute holder with defaults. ``get_settings()`` returns a shared
    instance. Supports ``.get(name, default)`` and ``as_dict()`` for structured
    consumers and JSON serialisation.
    """

    # ------------------------------------------------------------------
    # App shell
    # ------------------------------------------------------------------
    APP_TITLE = "ARVEN AI"
    APP_WINDOW_WIDTH = 980
    APP_WINDOW_HEIGHT = 680
    APP_MIN_WIDTH = 720
    APP_MIN_HEIGHT = 520

    APP_EXIT_PHRASES = [
        "bye arven",
        "goodbye arven",
        "good night arven",
        "shutdown arven",
        "shut down arven",
        "close yourself",
        "exit arven",
        "quit arven",
    ]

    APP_MODE_SELECTORS = {
        "chat": ["chat", "text mode", "type mode", "typing"],
        "talk": ["talk", "voice", "voice mode", "speak"],
    }
    APP_MODE_PROMPT = "Boss, what do you prefer — Chat or Talk?"
    APP_BYE_MESSAGE = "Bye Boss."
    AUDIO_SETTLE_DELAY = 0.5

    # ------------------------------------------------------------------
    # Brain / model
    # ------------------------------------------------------------------
    APP_NAME = "ARVEN"
    VERSION = "0.1.0"
    BOSS_NAME = "Saket"
    MODEL_PROVIDER = "ollama"
    MODEL_NAME = "qwen3.5:4b"
    TEXT_PROVIDER = "ollama"
    CODING_PROVIDER = "ollama"
    EMBEDDING_PROVIDER = "local"
    VISION_PROVIDER = ""  # empty => vision is NOT_CONFIGURED (honest)
    IMAGE_GENERATION_PROVIDER = ""
    VIDEO_GENERATION_PROVIDER = ""
    STT_PROVIDER = "faster_whisper"
    TTS_PROVIDER = "sapi"
    DEBUG = True

    # ------------------------------------------------------------------
    # Security / trust
    # ------------------------------------------------------------------
    CONFIDENCE_THRESHOLD = 0.8
    CONFIRMATION_TTL_SECONDS = 60
    MAX_CONFIRMATION_ATTEMPTS = 3
    TRUST_TTL_SECONDS = 300

    # ------------------------------------------------------------------
    # Scheduler / proactive
    # ------------------------------------------------------------------
    PROACTIVE_ENABLED = True
    PROACTIVE_QUIET_HOURS_START = 22
    PROACTIVE_QUIET_HOURS_END = 8
    SCHEDULER_POLL_SECONDS = 2

    # ------------------------------------------------------------------
    # Paths / output
    # ------------------------------------------------------------------
    OUTPUT_ROOT = "Output"
    SCREENSHOTS_DIR = "Screenshots"
    LOG_DIR = "Logs"

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------
    STT_MODEL_SIZE = "base"
    STT_DEVICE = "cpu"
    STT_COMPUTE_TYPE = "int8"

    def __init__(self):
        # Apply environment overrides so ``ARVEN_*`` / plain env vars win.
        for name in dir(self):
            if name.isupper():
                default = getattr(self, name)
                value = _env_value(name, default)
                if isinstance(default, bool):
                    setattr(self, name, str(value).lower() in ("1", "true", "yes", "on"))
                elif isinstance(default, int):
                    try:
                        setattr(self, name, int(value))
                    except (TypeError, ValueError):
                        pass
                elif isinstance(default, float):
                    try:
                        setattr(self, name, float(value))
                    except (TypeError, ValueError):
                        pass
                else:
                    setattr(self, name, value)

    # ------------------------------------------------------------------
    # Structured access
    # ------------------------------------------------------------------
    def get(self, name, default=None):
        return getattr(self, name, default)

    def as_dict(self):
        return {
            name: getattr(self, name)
            for name in dir(self)
            if name.isupper() and not name.startswith("_")
        }

    def to_json(self):
        return json.dumps(self.as_dict(), default=str, indent=2)


__all__ = ["Settings"]