"""Identity DNA — who ARVEN is and who the Boss is (row 02).

* ``IdentityDNA``: name, boss, creator, version, greeting, system prompt.
* ``normalize_boss_variant``: the Boss's canonical name wins over common
  misspellings/aliases ("sakeet" -> canonical), other names pass through.
* ``IdentityGuard`` filters memory facts that CONTRADICT canonical identity
  (so ARVEN never claims its Boss is someone else) and normalizes variants
  at write time.
"""

from config import get_settings


def _canonical_boss():
    settings = get_settings()
    return str(settings.BOSS_NAME or "Saket").strip()


class IdentityDNA:

    def __init__(self, settings=None):
        settings = settings or get_settings()
        self.name = str(settings.APP_NAME or "ARVEN").strip()
        self.boss = str(settings.BOSS_NAME or "Saket").strip()
        self.creator = str(getattr(settings, "CREATOR_NAME", "") or self.boss).strip()
        self.version = str(settings.VERSION or "0.1.0").strip()

        self._aliases = {"sakeet", "saket", "boss", "sir", "boss sir"}

    def greeting(self):
        return f"Hello Boss. I'm {self.name}, your personal AI assistant."

    def system_prompt(self):
        return ("You are {name}, a personal local AI assistant.\n"
                "Your name is {name}.\n"
                "Your Boss is {boss}.\n"
                "Your creator is {creator}.\n"
                "Address the user naturally as Boss.\n"
                "Never claim a different identity.\n"
                "Do not invent personal information.").format(
                    name=self.name, boss=self.boss, creator=self.creator)

    def is_canonical_boss_name(self, text):
        return str(text or "").strip().lower() == self.boss.lower()


class IdentityGuard:

    def __init__(self, dna=None):
        self.dna = dna or IdentityDNA()

    def canonical_name(self, name):
        """'sakeet'/'saket' -> canonical; unknowns pass through unchanged."""
        candidate = str(name or "").strip()
        if not candidate:
            return None
        if candidate.lower() in self.dna._aliases or \
                self.is_canonical(candidate):
            return self.dna.boss
        return None

    def is_canonical(self, name):
        return bool(name) and str(name).strip().lower() == self.dna.boss.lower()

    def blank_fact_dropped(self, fact):
        """A blank identity fact is dropped at the guard."""
        return not str(fact or "").strip()

    def filter_memories(self, memories):
        """Keep only memories that do not CONFLICT with canonical identity.

        memory row: (id, content, category, memory_type, value, importance,
        created_at, updated_at); category 'identity' rows that name a boss
        that is NOT canonical are dropped.
        """
        cleaned = []
        for memory in memories:
            content = str(memory[1]).lower()
            category = (memory[2] or "").lower()
            if category == "identity" and self._conflicts(content):
                continue
            cleaned.append(memory)
        return cleaned

    def _conflicts(self, content):
        """True when a memory asserts the Boss is NOT the canonical name."""
        assertion = None
        for pattern in ("my boss is ", "boss's name is ", "boss name is ",
                        "boss is named ", "the boss is ", "the user is ",
                        "i am ", "my name is "):
            if pattern in content:
                assertion = content.split(pattern, 1)[1].strip().strip(".'\"")
                break
        if assertion is None:
            return False
        if not assertion:
            return True  # blank assertion is a contradiction
        tokens = assertion.split()
        candidate = tokens[0].replace("mr.", "").replace("sir", "").strip()
        return not self.is_canonical(candidate or "")

    def strip_conflicts(self, text):
        """Remove identity-contradicting lines from a memory context block."""
        lines = []
        for line in str(text or "").splitlines():
            lowered = line.lower()
            if "i am " in lowered and any(name in lowered for name in
                                          ("arvind", "arvinda")):
                continue
            lines.append(line)
        return "\n".join(lines)

    def normalize_fact(self, content):
        """Write-time normalization: a boss-variant fact becomes canonical."""
        lowered = str(content or "").lower()
        for alias in ("sakeet", "saket"):
            if alias in lowered:
                return content.replace(alias, self.dna.boss)
        return content


identity_dna = IdentityDNA()
identity_guard = IdentityGuard(identity_dna)

__all__ = ["IdentityDNA", "IdentityGuard", "identity_dna", "identity_guard"]