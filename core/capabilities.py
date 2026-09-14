"""Capabilities tracking (row 27 / offline-aware).

* ``CapabilityStatus`` enum with a strict ordering
* ``fold`` picks the worst status among a set (never lies OK)
* local capabilities are ALWAYS available, even offline
* missing/unreachable providers resolve to not_configured / unavailable
* structured output never reports success while offline
* summaries never leak secrets
"""

from enum import Enum


class CapabilityStatus(Enum):
    AVAILABLE = "available"
    LIMITED = "limited"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"

    def __str__(self):
        return self.value


_WORSE = {
    CapabilityStatus.AVAILABLE: 0,
    CapabilityStatus.LIMITED: 1,
    CapabilityStatus.NOT_CONFIGURED: 2,
    CapabilityStatus.UNAVAILABLE: 3,
}


def fold(statuses):
    """The aggregate status is the WORST one — never more optimistic."""
    if not statuses:
        return CapabilityStatus.AVAILABLE
    worst = max(statuses, key=lambda s: _WORSE[s])
    return worst


LOCAL_CAPABILITIES = {
    "local_ops",
    "files",
    "memory",
    "notes",
    "tasks",
    "scheduler",
    "timers",
    "system_readonly",
    "tts",
}


class CapabilityProbe:
    """Stateless resolution of provider availability for each capability."""

    def __init__(self, settings=None):
        self.settings = settings

    def _ready(self, name, default=None):
        try:
            from config import get_settings
            return get_settings().get(name, default)
        except Exception:
            return default

    def probe(self, name, offline=False):
        name = str(name).lower()
        if name in LOCAL_CAPABILITIES:
            return CapabilityStatus.AVAILABLE if not offline else CapabilityStatus.AVAILABLE
        if name in ("text", "text_model", "llm", "generation"):
            model = self._ready("MODEL_PROVIDER") or self._ready("TEXT_PROVIDER")
            if not model:
                return CapabilityStatus.UNAVAILABLE if offline else CapabilityStatus.NOT_CONFIGURED
            if offline:
                return CapabilityStatus.UNAVAILABLE
            return CapabilityStatus.AVAILABLE
        if name in ("embeddings", "embedding", "semantic"):
            provider = self._ready("EMBEDDING_PROVIDER")
            if not provider:
                return CapabilityStatus.UNAVAILABLE if offline else CapabilityStatus.NOT_CONFIGURED
            if offline:
                return CapabilityStatus.UNAVAILABLE
            return CapabilityStatus.AVAILABLE
        if name in ("vision", "image_analysis"):
            provider = self._ready("VISION_PROVIDER")
            if provider and not offline:
                return CapabilityStatus.AVAILABLE
            return CapabilityStatus.UNAVAILABLE if offline else CapabilityStatus.NOT_CONFIGURED
        if name == "ollama":
            if offline:
                return CapabilityStatus.UNAVAILABLE
            try:
                import ollama  # noqa: F401
                return CapabilityStatus.AVAILABLE
            except Exception:
                return CapabilityStatus.NOT_CONFIGURED
        return None


BAD_STATUS = "error"


class Capabilities:

    def __init__(self, probe=None):
        self._probe = probe or CapabilityProbe()
        self._cache = {}

    def resolve(self, name, offline=False):
        status = self._probe.probe(name, offline=offline)
        if status is None:
            status = CapabilityStatus.NOT_CONFIGURED
        return status

    def fold(self, names, offline=False):
        statuses = [self.resolve(name, offline=offline) for name in names]
        return fold(statuses)

    def status(self, names=None, offline=False):
        """Never contains the string 'error'; offline never yields success."""
        result = {}
        for name in (names or sorted(_KNOWN_CAPABILITIES)):
            status = self.resolve(name, offline=offline).value
            if status == BAD_STATUS:
                status = "unavailable"
            result[name] = status
        return result

    def structured(self, offline=False):
        statuses = self.status(offline=offline)
        result = {}
        for capability, status in statuses.items():
            local = capability in LOCAL_CAPABILITIES
            result[capability] = {
                "available": status == CapabilityStatus.AVAILABLE.value
                and (local or not offline),
                "status": status,
                "local": local,
            }
        return result

    def summary(self, offline=False):
        # plain text, no secrets
        lines = []
        for name, status in sorted(self.status(offline=offline).items()):
            lines.append(f"{name}: {status}")
        return "\n".join(lines)


_KNOWN_CAPABILITIES = {
    "local_ops", "files", "memory", "notes", "tasks", "scheduler",
    "text", "embeddings", "vision", "ollama",
}

capabilities = Capabilities()

__all__ = ["CapabilityStatus", "Capabilities", "CapabilityProbe",
           "fold", "capabilities"]