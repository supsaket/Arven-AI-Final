"""Provider framework — Day 2 provider abstraction (features 39-46, 79-85, 93...)."""

from core.providers.base import (
    ALL_STATUSES,
    Provider,
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
    STATUS_REQUIRES_PERMISSION,
    STATUS_FAILED,
    ok,
    reject,
    probe_network,
)
from core.providers.registry import ProviderRegistry, providers_registry

__all__ = [
    "ALL_STATUSES",
    "Provider",
    "ProviderRegistry",
    "providers_registry",
    "STATUS_AVAILABLE",
    "STATUS_UNAVAILABLE",
    "STATUS_NOT_CONFIGURED",
    "STATUS_OFFLINE",
    "STATUS_REQUIRES_AUTH",
    "STATUS_REQUIRES_PERMISSION",
    "STATUS_FAILED",
    "ok",
    "reject",
    "probe_network",
]