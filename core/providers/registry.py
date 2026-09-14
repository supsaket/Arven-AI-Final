"""Provider registry (Day 2) — discovery + honest capability routing.

* ``register(provider)`` / ``get(name)`` / ``all_providers()``
* ``providers_for(capability)`` — providers that own the capability
* ``execute(capability, **kwargs)`` — routes to the best provider for the
  capability (prefers an AVAILABLE one), never raises.
* ``capability_status(capability)`` — worst honest status among candidates;
  missing capability => NOT_CONFIGURED.
* ``status_all()`` — snapshot of every provider (for command centre /
  diagnostics). Refreshes through each provider's ``check()``.
"""

import threading

from core.providers.base import (
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    reject,
)


class ProviderRegistry:

    def __init__(self):
        self._providers = {}
        self._lock = threading.RLock()

    def register(self, provider):
        from core.providers.base import Provider
        if not isinstance(provider, Provider):
            raise TypeError("ProviderRegistry.register requires a Provider")
        with self._lock:
            self._providers[provider.name] = provider
        return provider

    def get(self, name):
        with self._lock:
            return self._providers.get(name)

    def has(self, name):
        return self.get(name) is not None

    def all_providers(self):
        with self._lock:
            return [self._providers[n] for n in sorted(self._providers)] 

    def names(self):
        with self._lock:
            return sorted(self._providers)

    def providers_for(self, capability):
        needle = str(capability).replace("-", "_").lower()
        found = []
        with self._lock:
            for provider in self._providers.values():
                for owned in provider.capabilities:
                    if str(owned).replace("-", "_").lower() == needle:
                        found.append(provider)
                        break
        return found

    def check_all(self):
        """Refresh provider statuses (each may probe its backend)."""
        for provider in self.all_providers():
            try:
                provider.check()
            except Exception:
                provider.set_status("FAILED", "check raised")
        return self

    def status_all(self):
        self.check_all()
        return [p.status() for p in self.all_providers()]

    def execute(self, capability, **kwargs):
        """Route a capability call to the best suited provider.

        Order: AVAILABLE providers first, then any provider that owns the
        capability. No candidates -> honest NOT_CONFIGURED. Never raises.
        """
        providers = self.providers_for(capability)
        if not providers:
            return reject(
                STATUS_NOT_CONFIGURED,
                f"no provider configured for capability '{capability}'",
                {"capability": capability,
                 "known_capabilities": self.known_capabilities()})
        ordered = sorted(providers, key=lambda p: (p.status_code != STATUS_AVAILABLE, p.name))
        return ordered[0].execute(capability, **kwargs)

    def known_capabilities(self):
        with self._lock:
            return sorted({c for p in self._providers.values() for c in p.capabilities})

    def capability_status(self, capability):
        """Worst honest status among providers owning ``capability``."""
        providers = self.providers_for(capability)
        if not providers:
            return STATUS_NOT_CONFIGURED
        order = ["AVAILABLE", "UNAVAILABLE", "OFFLINE",
                 "REQUIRES_AUTH", "REQUIRES_PERMISSION",
                 "NOT_CONFIGURED", "FAILED"]
        rank = {s: i for i, s in enumerate(order)}
        worst = min(providers, key=lambda p: rank.get(p.status_code, len(order)))
        return worst.status_code

    def summary(self):
        self.check_all()
        return {
            "provider_count": len(self._providers),
            "capabilities": self.known_capabilities(),
            "providers": [
                {"name": p.name, "status": p.status_code,
                 "capabilities": sorted(p.capabilities)}
                for p in self.all_providers()
            ],
        }


# Shared registry instance.
providers_registry = ProviderRegistry()

__all__ = ["ProviderRegistry", "providers_registry"]