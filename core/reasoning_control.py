"""Feature 114 — Dynamic Reasoning Control.

Configure the reasoning effort ARVEN applies to a task, per operator, per
mission, or mid-mission, without ever pretending the level changes the model's
internal steps:

* levels LOW -> MEDIUM -> HIGH -> XHIGH -> MAX with an explicit ordering;
* ``estimate(text)`` — deterministic complexity heuristic (length + branching
  + risk signals) that returns a recommended level and its reasoning;
* ``set_level`` persists the active level + source (auto/manual/mission/
  mid_mission) and per-mission overrides, surviving restart;
* ``status`` reports the CONFIGURED level against the PROVIDER-SUPPORTED max
  (detected from the configured model provider). When the provider cannot
  truthfully support the requested level, the effective cap is reported — the
  engine never claims a level the provider does not expose.

Provider detection is honest: the supported level is derived from the
configured provider name via a conservative, documented mapping, and anything
outside the map is capped at MEDIUM with an explicit "assumption" note.
"""

import re
import time

from core.kv import KeyValueStore

_DEFAULT_KV = "data/reasoning_control.json"

LEVELS = ("LOW", "MEDIUM", "HIGH", "XHIGH", "MAX")
_ORDER = {level: i for i, level in enumerate(LEVELS)}

# Documented, conservative provider capability mapping (assumption, not
# negotiated with the model). Unknown providers cap at MEDIUM.
_PROVIDER_MAX = {
    "openai": "MAX", "anthropic": "MAX", "google": "MAX", "gemini": "MAX",
    "ollama": "XHIGH", "deepseek": "XHIGH", "mistral": "HIGH",
    "groq": "HIGH", "together": "HIGH", "huggingface": "HIGH",
    "local": "MEDIUM",
}
_DEFAULT_PROVIDER_MAX = "MEDIUM"

_BRANCH_SIGNALS = (
    "but", "unless", "however", "alternatively", "instead", "compare",
    "options", "choice", "decision", "branch", "scenario", "trade-off",
    "versus", "if .* then",
)
_RISK_SIGNALS = ("delete", "destructive", "confirm", "security", "submit",
                 "permission", "high risk", "irreversible", "external")
_DEEP_SIGNALS = ("very complex", "extremely complex", "deep analysis",
                 "comprehensive", "exhaustive", "multi-stage", "critical")

_DESCRIPTIONS = {
    "LOW": "minimal effort: trivial lookups and status checks",
    "MEDIUM": "balanced effort: routine multi-step tasks",
    "HIGH": "elevated effort: complex analysis and planning",
    "XHIGH": "extended effort: deep multi-domain reasoning",
    "MAX": "maximum effort: extreme reasoning and verification",
}


def _normalise_level(value):
    level = str(value or "").upper().strip()
    return level if level in _ORDER else None


class ReasoningControl:
    """Persisted reasoning-effort control with honest provider caps."""

    def __init__(self, kv_path=None):
        self.path = str(kv_path) if kv_path else _DEFAULT_KV
        self.store = KeyValueStore(self.path)

    # ------------------------------------------------------------------
    # active level
    # ------------------------------------------------------------------
    def _current(self):
        current = self.store.get("reasoning.current")
        if not current:
            default = {"level": "MEDIUM", "source": "auto",
                       "at": time.time(), "note": "factory default"}
            self.store.set("reasoning.current", default)
            return default
        return current

    def set_level(self, level, source="manual", mission_id=None, note=""):
        level = _normalise_level(level)
        if level is None:
            return {"success": False, "status": "invalid_argument",
                    "message": f"level must be one of {', '.join(LEVELS)}",
                    "level": level}
        if source not in ("auto", "manual", "mission", "mid_mission"):
            return {"success": False, "status": "invalid_argument",
                    "message": "source must be auto|manual|mission|mid_mission"}
        entry = {
            "level": level, "source": source,
            "mission_id": mission_id, "at": time.time(),
            "note": str(note or ""),
        }
        if mission_id:
            overrides = self.store.get("reasoning.mission_overrides") or {}
            overrides[str(mission_id)] = entry
            self.store.set("reasoning.mission_overrides", overrides)
        else:
            self.store.set("reasoning.current", entry)
        supported = self.supported_max()
        eff = self._effective(supported.get("level"), entry)
        self.store.set("reasoning.effective_cap", {
            "level": level,
            "effective": eff,
            "supported_max": supported,
            "at": time.time(),
        })
        return {
            "success": True, "status": "ok",
            "message": f"reasoning level set to {level} "
                       f"(source={source})",
            "level": level, "source": source,
            "mission_id": mission_id,
            "effective": eff,
            "supported_max": supported,
            "note": "level is a control directive; provider support is "
                    "reported separately and never assumed",
            "recorded": entry,
        }

    def _effective(self, supported_max, entry):
        """Practical cap = configured level clamped to provider support."""
        want = _ORDER.get(entry.get("level"), 0)
        cap = _ORDER.get(supported_max, 0)
        eff = LEVELS[min(want, cap)]
        return eff if eff != entry.get("level") else entry.get("level")

    # ------------------------------------------------------------------
    # provider detection
    # ------------------------------------------------------------------
    def configured_provider(self):
        try:
            from config import get_settings
            settings = get_settings()
        except Exception:
            settings = {}
        provider = settings.get("MODEL_PROVIDER") or \
            settings.get("TEXT_PROVIDER")
        if not provider:
            try:
                from core.providers.registry import providers_registry
                names = providers_registry.names()
                if "ollama" in names:
                    provider = "ollama"
                elif names:
                    provider = str(names[0])
            except Exception:
                provider = None
        return str(provider).strip().lower() or None

    def supported_max(self):
        provider = self.configured_provider()
        if not provider:
            return {
                "level": _DEFAULT_PROVIDER_MAX, "provider": None,
                "assumption": True,
                "note": "no provider configured — conservative MEDIUM cap",
            }
        known = {k for k in _PROVIDER_MAX}
        exact = provider if provider in known else None
        partial = None
        if exact is None:
            for key in known:
                if key in provider or provider in key:
                    partial = key
                    break
        if exact or partial:
            level = _PROVIDER_MAX[exact or partial]
            return {
                "level": level, "provider": provider,
                "matched": exact or partial, "assumption": True,
                "note": "supported level derived from provider-name mapping; "
                        "not negotiated with the model",
            }
        return {
            "level": _DEFAULT_PROVIDER_MAX, "provider": provider,
            "matched": None, "assumption": True,
            "note": f"provider '{provider}' outside the known map — "
                    "conservative MEDIUM cap",
        }

    # ------------------------------------------------------------------
    # estimation
    # ------------------------------------------------------------------
    def estimate(self, text):
        text = str(text or "").strip()
        if not text:
            return {"success": False, "status": "invalid_argument",
                    "message": "text is empty"}
        words = re.split(r"\s+", text)
        word_count = len([w for w in words if w])
        chars = len(text)
        tokens_estimate = max(1, round(chars / 4.0))
        lowered = text.lower()
        branches = sum(1 for s in _BRANCH_SIGNALS if s in lowered)
        risks = sum(1 for s in _RISK_SIGNALS if s in lowered)
        deep = sum(1 for s in _DEEP_SIGNALS if s in lowered)

        score = 0
        if word_count >= 1500:
            score += 4
        elif word_count >= 600:
            score += 3
        elif word_count >= 200:
            score += 2
        elif word_count >= 40:
            score += 1
        score += min(2, branches)
        score += min(2, risks)
        score += min(3, deep)

        level = LEVELS[min(score, len(LEVELS) - 1)]
        reasons = [
            f"{word_count} words (~{tokens_estimate} estimated tokens)"
            if word_count else "empty",
        ]
        if branches:
            reasons.append(f"{branches} branching signal(s)")
        if risks:
            reasons.append(f"{risks} risk signal(s)")
        if deep:
            reasons.append(f"{deep} deep-complexity signal(s)")
        return {
            "success": True, "status": "ok",
            "estimated_level": level,
            "tokens_estimate": tokens_estimate,
            "word_count": word_count,
            "signals": {"branches": branches, "risks": risks, "deep": deep},
            "reason": "; ".join(reasons),
            "note": "heuristic recommendation only — the operator or "
                    "mission may override it",
        }

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------
    def status(self, mission_id=None):
        current = self._current()
        overrides = self.store.get("reasoning.mission_overrides") or {}
        supported = self.supported_max()
        entry = current
        if mission_id and str(mission_id) in overrides:
            entry = overrides[str(mission_id)]
        configured = entry.get("level")
        effective = self._effective(supported.get("level"), entry)
        return {
            "success": True, "status": "ok",
            "configured_level": configured,
            "configured_source": entry.get("source"),
            "effective_level": effective,
            "provider_supported_max": supported.get("level"),
            "provider": supported.get("provider"),
            "provider_assumption": supported.get("assumption"),
            "provider_note": supported.get("note"),
            "mission_id": mission_id,
            "note": ("provider may cap the configured level; effective_level "
                     "is the honest cap and is never claimed otherwise"),
            "mission_overrides": {
                k: {"level": v.get("level"), "source": v.get("source")}
                for k, v in overrides.items()},
            "levels": {level: _DESCRIPTIONS[level] for level in LEVELS},
        }


reasoning_control = ReasoningControl()

__all__ = [
    "ReasoningControl", "reasoning_control",
    "LEVELS", "_ORDER", "_DESCRIPTIONS",
]