"""Speaker Recognition (48) & Language Detection (49).

Speaker recognition computes a real FFT-magnitude voiceprint and matches
by cosine similarity.  Results **always** include ``authorized: False`` —
identity is informational, never an auth gate.

Language detection uses per-language letter-frequency profiles built from
reference alphabets (en, de, fr, es, it, hi, ja, zh, ru) and finds the
closest profile by cosine similarity.
"""

import math
import os
import re
import uuid
from datetime import datetime, timezone

import numpy as np

from core.kv import KeyValueStore

# ------------------------------------------------------------------
# Speaker Recognition (48)
# ------------------------------------------------------------------


def _voiceprint(audio, sr=16000, dim=32):
    """Extract a normalised magnitude-spectrum voiceprint (dim-dim vector).

    Uses FFT on the raw audio, takes the magnitude of the first
    ``dim * 4`` bins, bins them into ``dim`` buckets, L2-normalises.
    """
    audio = np.asarray(audio, dtype=np.float64).ravel()
    if audio.size == 0:
        return np.zeros(dim, dtype=np.float64)
    fft = np.fft.rfft(audio)
    mag = np.abs(fft)
    n = min(mag.size, dim * 4)
    mag = mag[:n]
    # bin into *dim* buckets
    bucket_size = max(1, n // dim)
    binned = []
    for i in range(0, dim * bucket_size, bucket_size):
        chunk = mag[i : i + bucket_size]
        binned.append(float(chunk.mean()) if chunk.size else 0.0)
    vec = np.array(binned[:dim], dtype=np.float64)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def _cosine(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SpeakerRecognition:
    """Enrol and recognise speakers via FFT voiceprints (kv-persisted)."""

    def __init__(self, kv_path="data/speakers.json"):
        self._kv = KeyValueStore(kv_path)
        if self._kv.get("_profiles") is None:
            self._kv.set("_profiles", {})

    def _profiles(self):
        return self._kv.get("_profiles", {})

    def _save_profiles(self, profiles):
        self._kv.set("_profiles", profiles)

    def enroll(self, speaker_id, audio, sr=16000, consent=True):
        if not consent:
            return {
                "status": "REQUIRES_PERMISSION",
                "reason": "Consent is required to enrol a voiceprint.",
            }
        vp = _voiceprint(audio, sr)
        profiles = self._profiles()
        profiles[speaker_id] = {
            "voiceprint": vp.tolist(),
            "enrolled_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_profiles(profiles)
        return {
            "status": "AVAILABLE",
            "speaker_id": speaker_id,
            "dimensions": len(vp),
        }

    def recognize(self, audio, sr=16000):
        """Return best match and scores.  **Always** ``authorized: False``."""
        profiles = self._profiles()
        if not profiles:
            return {
                "status": "UNAVAILABLE",
                "reason": "No enrolled speakers.",
                "authorized": False,
            }
        vp = _voiceprint(audio, sr)
        scores = {}
        for sid, pdata in profiles.items():
            enrolled_vp = np.array(pdata["voiceprint"], dtype=np.float64)
            scores[sid] = round(_cosine(vp, enrolled_vp), 6)
        best_id = max(scores, key=scores.get)
        return {
            "status": "AVAILABLE",
            "best_match": best_id,
            "scores": scores,
            "authorized": False,  # NEVER grants authorization
        }

    def list_speakers(self):
        profiles = self._profiles()
        return [
            {"speaker_id": sid, "enrolled_at": p["enrolled_at"]}
            for sid, p in profiles.items()
        ]

    def delete_speaker(self, speaker_id):
        profiles = self._profiles()
        removed = profiles.pop(speaker_id, None)
        self._save_profiles(profiles)
        return {"removed": removed is not None, "speaker_id": speaker_id}


# ------------------------------------------------------------------
# Language Detection (49)
# ------------------------------------------------------------------

# Reference strings used to build letter-frequency profiles per language.
_REF_SAMPLES = {
    "en": "The quick brown fox jumps over the lazy dog and the",
    "de": "Falsches X von kleinen Kwaken quaest im See und",
    "fr": "Portez ce vieux whisky au juge blond qui fume sur",
    "es": "El veloz murciélago hindú comía feliz cardillo y kiwi",
    "it": "Quel vituperabile xenofobo zelante compra wap e dj",
    "hi": "\u0905\u0917\u0938\u0947 \u092e\u0947\u0902 \u0916\u093e\u0928\u093e \u0939\u0948 \u092f\u0939 \u092e\u0948\u0902 \u0915\u094d\u092e\u0925\u093e",
    "ja": "\u3042\u308b\u3055\u3051\u307f\u305f\u308b\u3068\u305b\u308a\u306a\u308b\u3092",
    "zh": "\u4f60\u597d\u6211\u7684\u670b\u53cb\u4eca\u5929\u5929\u6c14\u771f\u597d",
    "ru": "\u0414\u0430\u0432\u044b\u0439 \u0424\u0435\u0434\u044f \u0431\u0440\u044d\u0441\u0442 \u0448\u0443\u043b \u0446\u044b\u043f\u043b\u0435\u043d\u0438\u043b \u0432 \u0447\u0430\u044e",
    "es_extra": "",  # placeholder
}

_SCRIPT_PATTERNS = {
    "hi": re.compile(r"[\u0900-\u097F]"),
    "ja": re.compile(r"[\u3040-\u309F\u30A0-\u30FF]"),
    "zh": re.compile(r"[\u4E00-\u9FFF]"),
    "ru": re.compile(r"[\u0400-\u04FF]"),
}


def _letter_freq(text, alphabet_size=26):
    """Normalised letter-frequency vector for Latin-script languages."""
    counts = [0.0] * alphabet_size
    for ch in text.lower():
        idx = ord(ch) - ord("a")
        if 0 <= idx < alphabet_size:
            counts[idx] += 1
    total = sum(counts) or 1.0
    return [c / total for c in counts]


def _script_freq(text, unicode_range_start, unicode_range_end, dim=64):
    """Character frequency across a Unicode block (for non-Latin scripts)."""
    counts = [0.0] * dim
    span = unicode_range_end - unicode_range_start
    for ch in text:
        cp = ord(ch)
        if unicode_range_start <= cp <= unicode_range_end:
            idx = min(int((cp - unicode_range_start) / max(1, span / dim)), dim - 1)
            counts[idx] += 1
    total = sum(counts) or 1.0
    return [c / total for c in counts]


def _dot(a, b):
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def _norm(v):
    return math.sqrt(sum(x * x for x in v)) or 1.0


class LanguageDetector:
    """Profile-based language detection for Latin and non-Latin scripts."""

    def __init__(self):
        self._profiles = {}
        self._forced = None
        self._build_profiles()

    def _build_profiles(self):
        for lang, sample in _REF_SAMPLES.items():
            if lang.startswith("_"):
                continue
            # detect script
            if lang == "hi":
                fp = _script_freq(sample, 0x0900, 0x097F, 64)
            elif lang == "ja":
                fp = _script_freq(sample, 0x3040, 0x30FF, 64)
            elif lang == "zh":
                fp = _script_freq(sample, 0x4E00, 0x9FFF, 64)
            elif lang == "ru":
                fp = _script_freq(sample, 0x0400, 0x04FF, 64)
            else:
                fp = _letter_freq(sample, 26)
            self._profiles[lang] = fp

    def detect(self, text):
        """Return detected language with confidence, or UNKNOWN."""
        if self._forced:
            return {
                "language": self._forced,
                "confidence": 1.0,
                "status": "AVAILABLE",
                "forced": True,
            }
        text = text or ""
        stripped = re.sub(r"[^A-Za-z\u0900-\u097F\u3040-\u30FF\u4E00-\u9FFF\u0400-\u04FF]", "", text)
        if len(stripped) < 3:
            return {
                "language": "UNKNOWN",
                "confidence": 0.0,
                "status": "NOT_CONFIGURED",
                "reason": "Insufficient text for detection.",
            }

        # choose frequency function based on script content
        sample_vec = _letter_freq(stripped, 26)
        non_latin = False
        for lang_key in ("hi", "ja", "zh", "ru"):
            pat = _SCRIPT_PATTERNS[lang_key]
            if pat.search(stripped):
                non_latin = True
                break

        best_lang = None
        best_score = -1.0
        for lang, prof in self._profiles.items():
            if non_latin and lang in ("en", "de", "fr", "es", "it"):
                continue
            if not non_latin and lang not in ("en", "de", "fr", "es", "it"):
                continue
            score = _dot(sample_vec, prof) / (_norm(sample_vec) * _norm(prof)) if _norm(sample_vec) * _norm(prof) else 0.0
            if score > best_score:
                best_score = score
                best_lang = lang

        if best_lang is None:
            return {
                "language": "UNKNOWN",
                "confidence": 0.0,
                "status": "UNKNOWN",
            }

        return {
            "language": best_lang,
            "confidence": round(best_score, 4),
            "status": "AVAILABLE",
        }

    def set_language(self, name, force=True):
        if force:
            self._forced = name
        return {"language": name, "forced": force, "status": "AVAILABLE"}


__all__ = ["SpeakerRecognition", "LanguageDetector", "_voiceprint", "_cosine"]
