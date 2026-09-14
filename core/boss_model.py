"""Boss Model (Day 2, feature 77).

Only uses consented facts plus the base profile name from settings. Never
invents preferences: unknown preferences are reported honestly as not known
and never inferred. Discussions are grounded only in stored facts.
"""

from datetime import datetime

from config import get_settings
from core.kv import KeyValueStore

# Mode selectors come from canonical settings (a known, consented default).
_SETTING_MODES = ("APP_MODE_SELECTORS", "APP_MODE_PROMPT", "APP_MODE_DEFAULT")


class BossModel:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/boss_model.json")
        self.settings = get_settings()

    # ------------------------------------------------------------------
    def _consent_log(self, entry):
        log = self.kv.get("consent_log", [])
        log.append({"at": datetime.now().isoformat(), **entry})
        self.kv.set("consent_log", log)

    def consent_history(self):
        return self.kv.get("consent_log", [])

    # ------------------------------------------------------------------
    def facts(self):
        """Consented preferences + base profile facts, no inventions."""
        profile = {
            "boss_name": self._boss_name(),
            "source": "config",
            "consented": True,
        }
        preferences = self.kv.get("preferences", {})
        consented = {
            name: value for name, value in preferences.items()
            if value.get("consented") is True
        }
        return {
            "profile": profile,
            "consented_preferences": consented,
            "mode_selectors": self._mode_selectors(),
        }

    def _boss_name(self):
        try:
            return self.settings.get("BOSS_NAME") or "unknown"
        except Exception:
            return "unknown"

    def _mode_selectors(self):
        selectors = {}
        for setting in _SETTING_MODES:
            value = None
            try:
                value = self.settings.get(setting)
            except Exception:
                value = None
            if value:
                selectors[setting] = value
        return selectors

    # ------------------------------------------------------------------
    def set_preference(self, name, value, consented=False):
        if not consented:
            return {"stored": False, "reason": "consent required",
                    "name": name, "value": "not stored"}
        preferences = self.kv.get("preferences", {})
        preferences[str(name)] = {
            "value": value,
            "consented": True,
            "at": datetime.now().isoformat(),
        }
        self.kv.set("preferences", preferences)
        self._consent_log({"action": "set_preference", "name": str(name)})
        return {"stored": True, "name": str(name), "value": value}

    # ------------------------------------------------------------------
    def suggest_preferences(self):
        """Only known defaults + explicitly consented items. Unknown -> 'not known'."""
        known = {}
        mode_selectors = self._mode_selectors()
        if mode_selectors.get("APP_MODE_SELECTORS"):
            keys = sorted(mode_selectors["APP_MODE_SELECTORS"])
            known["preferred_mode"] = {
                "known": True,
                "value": (keys[0] if keys else "chat"),
                "note": "from settings mode selectors",
            }
        consented = self.facts()["consented_preferences"]
        for name, entry in consented.items():
            known[name] = {"known": True, "value": entry["value"],
                           "consented": True}
        return {
            "known_preferences": known,
            "unknown": {
                "preferred_tone": "not known",
                "communication_style": "not known",
                "decision_speed": "not known",
            },
        }

    # ------------------------------------------------------------------
    def consult(self, question):
        """Grounded answer using stored facts only; no fabrication."""
        lower = (question or "").lower()
        facts = self.facts()
        text = f"{lower} {question or ''}"

        answered = []
        if "name" in text or "boss" in text:
            answered.append({"subject": "boss_name",
                             "fact": facts["profile"]["boss_name"],
                             "source": "config"})
        for name, entry in facts["consented_preferences"].items():
            if name.lower().replace("_", " ") in lower or name.lower() in lower:
                answered.append({"subject": name,
                                 "fact": entry["value"],
                                 "source": "consented preference"})

        if answered:
            return {"grounded": True, "facts": answered,
                    "answer": _compose(answered)}
        return {"grounded": True, "facts": [],
                "answer": ("I only reason from consented facts or the boss "
                           "profile in settings. I don't have a stored fact "
                           "to answer that, and I won't invent one.")}


def _compose(facts):
    return "; ".join(f"{f['subject']} = {f['fact']} ({f['source']})" for f in facts)


__all__ = ["BossModel"]
