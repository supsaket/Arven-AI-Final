"""Emotional Intelligence / Adaptive Response (69).

Provides ``AffectEngine`` which observes speech, computes a sentiment
valence and energy estimate, maintains a running mood, and suggests an
adaptive tone with an empathetic reply template.  Every advisory output
includes an informational disclaimer.
"""

import math
import re
from datetime import datetime, timezone

# ------------------------------------------------------------------
# Valence lexicon  (positive / negative words)
# ------------------------------------------------------------------
_POSITIVE = {
    "good", "great", "excellent", "happy", "love", "awesome", "fantastic",
    "wonderful", "best", "amazing", "thank", "thanks", "glad", "pleased",
    "excited", "brilliant", "nice", "fine", "joy", "fun", "beautiful",
    "success", "win", "hope", "kind", "smile", "calm", "peace",
}

_NEGATIVE = {
    "bad", "terrible", "horrible", "hate", "sad", "angry", "awful",
    "worst", "annoying", "frustrated", "disappointed", "fail", "failure",
    "ugly", "pain", "sorry", "wrong", "problem", "difficult", "hard",
    "stress", "anxious", "fear", "worry", "lost", "broken", "miss",
    "lost", "unfortunately", "nasty", "cruel",
}

_EMOTES = {":)", ":-)", ":D", ":-D", "<3", ":(", ":-(", ">:(", "XD", ";)"}
_EMOTES_POS = {":)", ":-)", ":D", ":-D", "<3", "XD", ";)"}
_EMOTES_NEG = {":(", ":-(", ">:("}

_TONE_SUGGESTIONS = {
    "calm":      {"reason": "User appears low energy or mildly negative."},
    "supportive": {"reason": "User is expressing negative emotions."},
    "assertive":  {"reason": "User is in a positive, action-oriented mood."},
    "neutral":    {"reason": "No strong emotional signal detected."},
}

_DISCLAIMER = (
    "This output is informational guidance only and does not constitute "
    "professional advice."
)


def _tokenize(text):
    return re.findall(r"[\w':!]+|[^\w\s]", (text or "").lower())


def _word_valence(tokens):
    pos = sum(1 for t in tokens if t in _POSITIVE)
    neg = sum(1 for t in tokens if t in _NEGATIVE)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def _energy_estimate(text):
    """Rough energy: punctuation density + caps ratio + emotes."""
    raw = text or ""
    if not raw:
        return 0.0
    exclaims = raw.count("!")
    questions = raw.count("?")
    caps_letters = sum(1 for c in raw if c.isupper())
    total_letters = max(1, sum(1 for c in raw if c.isalpha()))
    emote_hits = sum(1 for e in _EMOTES if e in raw)
    score = (
        0.35 * min(exclaims / max(1, len(raw) / 50), 1.0)
        + 0.25 * min(questions / max(1, len(raw) / 80), 1.0)
        + 0.20 * (caps_letters / total_letters)
        + 0.20 * min(emote_hits / 3, 1.0)
    )
    return round(min(score, 1.0), 3)


class AffectEngine:
    """Observe utterances, compute mood and suggest adaptive tone."""

    def __init__(self):
        self._observations = []
        self._mood_valence = 0.0
        self._mood_energy = 0.0
        self._count = 0

    # ------------------------------------------------------------------
    def observe(self, speaker, text):
        tokens = _tokenize(text)
        val = _word_valence(tokens)
        energy = _energy_estimate(text)
        self._count += 1
        alpha = 1.0 / self._count
        self._mood_valence = self._mood_valence * (1 - alpha) + val * alpha
        self._mood_energy = self._mood_energy * (1 - alpha) + energy * alpha
        entry = {
            "speaker": speaker,
            "text": text,
            "valence": round(val, 4),
            "energy": round(energy, 4),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._observations.append(entry)
        return entry

    # ------------------------------------------------------------------
    def mood(self):
        return {
            "valence": round(self._mood_valence, 4),
            "energy": round(self._mood_energy, 4),
            "observations": self._count,
        }

    # ------------------------------------------------------------------
    def affect_map(self):
        v = self._mood_valence
        e = self._mood_energy
        if v > 0.2 and e > 0.4:
            label = "elated"
        elif v > 0.2:
            label = "content"
        elif v < -0.2 and e > 0.4:
            label = "agitated"
        elif v < -0.2:
            label = "down"
        else:
            label = "neutral"
        return {"valence": round(v, 4), "energy": round(e, 4), "label": label}

    # ------------------------------------------------------------------
    def adapt_tone(self, intent="converse"):
        amap = self.affect_map()
        v, e = amap["valence"], amap["energy"]
        if v < -0.2:
            tone = "supportive"
        elif e < 0.2 and v >= -0.2:
            tone = "calm"
        elif v > 0.2 and e > 0.3:
            tone = "assertive"
        else:
            tone = "neutral"
        return {
            "suggested_tone": tone,
            "affect_label": amap["label"],
            "reasoning": _TONE_SUGGESTIONS[tone]["reason"],
            "intent": intent,
        }

    # ------------------------------------------------------------------
    def empathy_reply(self, context=""):
        amap = self.affect_map()
        v = amap["valence"]
        if v < -0.2:
            template = (
                f"I hear that things are tough right now regarding "
                f"'{context or 'your situation'}'. Your feelings are "
                f"valid, and I'm here to support you."
            )
        elif v > 0.2:
            template = (
                f"It's wonderful that '{context or 'things are going well'}'! "
                f"I'm glad you're feeling positive."
            )
        else:
            template = (
                f"Thanks for sharing about '{context or 'your situation'}'. "
                f"Let me know how I can help."
            )
        return {
            "template": template,
            "affect_label": amap["label"],
            "disclaimer": _DISCLAIMER,
        }


__all__ = ["AffectEngine", "_DISCLAIMER"]
