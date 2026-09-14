"""Wake word engine — text-level wake detection (fully offline).

``WakeWordEngine().available()`` reports whether the engine can operate, and
``contains_wake(text)`` checks for the wake phrase (\"hey arven\"). On Windows
with a microphone present the same engine can later be fed real audio; the
text path is deterministic and testable offline.
"""

from config import get_settings


class WakeWordEngine:

    def __init__(self, phrases=None):
        settings = get_settings()
        default = settings.get("WAKE_PHRASES", "hey arven,arven,ok arven")
        if isinstance(default, str):
            defaults = [p.strip() for p in default.split(",") if p.strip()]
        else:
            defaults = ["hey arven"] if default else ["hey arven"]
        self.phrases = [p.lower() for p in (phrases or defaults)]

    def available(self):
        return bool(self.phrases)

    def contains_wake(self, text):
        lowered = (text or "").lower()
        return any(phrase in lowered for phrase in self.phrases)

    def strip_wake(self, text):
        lowered = (text or "").lower()
        remaining = str(text or "")
        for phrase in sorted(self.phrases, key=len, reverse=True):
            if lowered.startswith(phrase):
                remaining = remaining[len(phrase):].strip()
                break
        return remaining


wakeword = WakeWordEngine()

__all__ = ["WakeWordEngine", "wakeword"]