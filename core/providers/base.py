"""Provider abstraction (Day 2 sec. 5) — statuses, honest execution, gating.

The provider framework is the backbone for every external/interactive Day 2
capability (browsing, vision, media generation, Android, IoT, E-mail,
camera, travel, location, navigation, vehicle, finance, shopping, ...).

Rules enforced here:

* providers NEVER crash: ``execute()`` always returns a structured dict.
* honest statuses: AVAILABLE / UNAVAILABLE / NOT_CONFIGURED / OFFLINE /
  REQUIRES_AUTH / REQUIRES_PERMISSION / FAILED.
* a provider that lacks a real backend reports NOT_CONFIGURED or
  UNAVAILABLE — it may NOT fake success.
* offline-first: providers that require the network must report OFFLINE
  when no network is present.
* risky provider actions go through the shared ``CONFIRMATION`` gate and
  require `confirmed`/`trusted`/`request_id` to be honoured.
"""

import socket
import threading
import time

from core.confirmation import CONFIRMATION

# ----------------------------------------------------------------------
# Honest status vocabulary (Day 2 contract)
# ----------------------------------------------------------------------
STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_OFFLINE = "OFFLINE"
STATUS_REQUIRES_AUTH = "REQUIRES_AUTH"
STATUS_REQUIRES_PERMISSION = "REQUIRES_PERMISSION"
STATUS_FAILED = "FAILED"

ALL_STATUSES = (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
    STATUS_REQUIRES_PERMISSION,
    STATUS_FAILED,
)


def _make_result(success, status, message, data=None, **extra):
    payload = {
        "success": bool(success),
        "status": str(status if status in ALL_STATUSES else STATUS_FAILED),
        "message": str(message),
        "data": data if isinstance(data, dict) else {},
    }
    payload.update(extra)
    return payload


def ok(message="ok", data=None, **extra):
    return _make_result(True, STATUS_AVAILABLE, message, data, **extra)


def reject(status, message, data=None, **extra):
    """An honest non-success result (never claims success)."""
    return _make_result(False, status, message, data, **extra)


def probe_network(timeout=1.0):
    """Best-effort connectivity check. Never blocks long, never raises."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except Exception:
        return False


class Provider:
    """Base class. Subclasses override ``_execute`` and ``check``.

    * ``name``        — unique provider id (lowercase, underscores)
    * ``capabilities``— lowercased capability ids this provider owns
    * ``category``    — registry grouping label
    * ``requires_network`` — offline-first flag checked in ``execute()``
    * ``confirm_capabilities`` — capability ids that need CONFIRMATION.gate
    """

    name = "base"
    capabilities = ()
    category = "provider"
    requires_network = False
    confirm_capabilities = ()

    def __init__(self, settings=None):
        from config import get_settings
        self.settings = settings if settings is not None else get_settings()
        self._status = STATUS_NOT_CONFIGURED
        self._reason = "provider not configured"
        self._detail = {}
        self._checked_at = None

    # ------------------------------------------------------------------
    # Status plumbing
    # ------------------------------------------------------------------
    def set_status(self, status, reason="", detail=None):
        self._status = str(status)
        self._reason = str(reason or "")
        self._detail = dict(detail) if detail else {}
        self._checked_at = time.time()
        return self._status

    @property
    def status_code(self):
        return self._status

    def available(self):
        return self._status == STATUS_AVAILABLE

    def needing_network(self):
        return bool(self.requires_network) and not probe_network()

    def check(self):
        """Refresh and return the honest status dict. Default: not configured."""
        return self.set_status(STATUS_NOT_CONFIGURED, "provider not configured")

    def status(self):
        return {
            "name": self.name,
            "category": self.category,
            "capabilities": sorted(self.capabilities),
            "status": self._status,
            "reason": self._reason,
            "detail": self._detail,
            "checked_at": self._checked_at,
            "requires_network": bool(self.requires_network),
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def describe_capability(self, capability):
        candidates = [c for c in self.capabilities
                      if str(c.replace("-", "_")).lower() == str(capability).lower()
                      or c == capability]
        return candidates[0] if candidates else capability

    def execute(self, capability, **kwargs):
        """Public entry point. Never raises; always structured.

        Honouring the security contract, a capability in
        ``confirm_capabilities`` is refused unless the caller supplies a
        confirmed+request_id that pass ``CONFIRMATION.gate``.
        """
        try:
            target = self.describe_capability(capability)
            method = getattr(self, f"_cap_{target.replace('-', '_')}", None)

            if self.needing_network():
                return self._honest(STATUS_OFFLINE,
                                    f"{self.name} requires network access")
            if method is None:
                return self._honest(
                    STATUS_NOT_CONFIGURED,
                    f"{self.name} does not implement capability '{capability}'")
            if target in self.confirm_capabilities:
                confirmed = bool(kwargs.pop("confirmed", False))
                trusted = bool(kwargs.pop("trusted", False))
                request_id = kwargs.pop("request_id", None)
                allowed, reason = CONFIRMATION.gate(
                    f"{self.name}.{target}",
                    confirmed=confirmed,
                    trusted=trusted,
                    request_id=request_id,
                )
                if not allowed:
                    return self._honest(
                        STATUS_REQUIRES_AUTH, f"{target} requires confirmation")
                kwargs["_cleared"] = True
            return method(**kwargs)
        except Exception as exc:  # never surface raw exceptions
            return self._honest(STATUS_FAILED, f"{self.name} error: {exc}")

    def _honest(self, status, message):
        return _make_result(False, status, message,
                            {"provider": self.name,
                             "capabilities": sorted(self.capabilities)})

    # ------------------------------------------------------------------
    # Offline guard used by subclasses
    # ------------------------------------------------------------------
    @staticmethod
    def offline_check(message="unavailable while offline"):
        status = "OFFLINE" if not probe_network() else "UNAVAILABLE"
        return reject(status, message)


__all__ = [
    "Provider",
    "ALL_STATUSES",
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