"""Confirmation / trust system.

Single shared authority for risky actions:
* risk classification (low/medium/high/destructive)
* pending-confirmation workflow (require -> approve/deny/cancel)
* scoped trust with TTL (a trusted scope expires)
* destructive actions are NEVER auto-trusted
* at-most-once execution guarantee is enforced by the ExecutionGuard

The ToolRegistry routes risky invocations through this manager, and the Brain
routes destructive requests through the same shared authority — there is no
second path that bypasses it.
"""

import threading
import time

from core.recovery import ExecutionGuard
from core.safety import (
    SAFETY,
    RISK_HIGH,
    RISK_DESTRUCTIVE,
)

_YES = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "go", "do it", "confirm"}
_NO = {"no", "n", "nope", "cancel", "stop", "don't", "abort"}


def risk_of(result):
    """Extract a risk label from a tool result if present."""
    if isinstance(result, dict):
        return result.get("risk")
    return None


class ConfirmationManager:

    def __init__(self, ttl=60, trust_ttl=300):
        self.ttl = ttl
        self.trust_ttl = trust_ttl
        self.guard = ExecutionGuard()

        self._lock = threading.Lock()
        self._pending = {}      # request_id -> {context, expiry, risk}
        self._audit = []        # list of events
        self._trust = {}        # scope -> expiry timestamp

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------
    def risk_classification(self, action, target=""):
        return SAFETY.risk_label(action, target)

    def requires_confirmation(self, action, target=""):
        risk = self.risk_classification(action, target)
        return SAFETY.requires_confirmation(risk) or risk == RISK_DESTRUCTIVE

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def require(self, context, risk=RISK_HIGH):
        """Open a pending confirmation. Returns a request_id."""
        request_id = f"cfm-{time.time_ns()}"
        with self._lock:
            self._pending[request_id] = {
                "context": str(context),
                "risk": str(risk),
                "expiry": time.monotonic() + self.ttl,
                "trusted": False,
            }
        self._record("pending", request_id, str(context), str(risk))
        return request_id

    def approve(self, request_id, scope=None):
        with self._lock:
            entry = self._pending.get(request_id)
            if entry is None:
                return False, "no such pending confirmation"
            if time.monotonic() > entry["expiry"]:
                del self._pending[request_id]
                return False, "confirmation expired"
            del self._pending[request_id]
            risk = entry["risk"]
            if scope:
                self._trust[scope] = time.monotonic() + self.trust_ttl
            self._record("approved", request_id, entry["context"], risk)
            return True, "approved"

    def deny(self, request_id):
        with self._lock:
            entry = self._pending.pop(request_id, None)
            if entry is None:
                return False, "no such pending confirmation"
            self._record("denied", request_id, entry["context"], entry["risk"])
            return True, "denied"

    def cancel(self, request_id):
        return self.deny(request_id)

    def is_pending(self, request_id):
        with self._lock:
            entry = self._pending.get(request_id)
            return entry is not None and time.monotonic() <= entry["expiry"]

    # ------------------------------------------------------------------
    # Trust
    # ------------------------------------------------------------------
    def is_trusted(self, scope):
        with self._lock:
            if scope in self._trust:
                if time.monotonic() <= self._trust[scope]:
                    return True
                del self._trust[scope]
            return False

    def trust_expires_at(self, scope):
        with self._lock:
            return self._trust.get(scope, None)

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------
    def resolve_yes_no(self, text):
        lowered = str(text or "").strip().lower()
        if lowered in _YES:
            return True
        if lowered in _NO:
            return False
        return None

    def resolve(self, request_id, text):
        """Resolve a pending confirmation from free text."""
        verdict = self.resolve_yes_no(text)
        if verdict is None:
            return False, "unrecognised answer — say yes or no"
        return self.approve(request_id) if verdict else self.deny(request_id)

    # ------------------------------------------------------------------
    # Gate used by registry / brain
    # ------------------------------------------------------------------
    def gate(self, action, target="", confirmed=False, trusted=False, request_id=None):
        """Return (allowed, reason).

        destructive => confirmed AND trusted must both be true (never auto).
        high        => must be confirmed (trust grants scope, not bypass).
        """
        risk = self.risk_classification(action, target)

        if risk == RISK_DESTRUCTIVE:
            if not (confirmed and trusted and request_id and self.is_pending_ok(request_id)):
                return False, "destructive action requires explicit confirmation"
            return True, "ok"

        if risk == RISK_HIGH:
            if not (confirmed and request_id and self.is_pending_ok(request_id)):
                return False, "action requires confirmation"
            return True, "ok"

        return True, "ok"

    def is_pending_ok(self, request_id):
        with self._lock:
            entry = self._pending.get(request_id)
            if entry and time.monotonic() <= entry["expiry"]:
                # consumed by the gate
                self._record("allowed", request_id, entry["context"], entry["risk"])
                del self._pending[request_id]
                return True
            return False

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _record(self, event, request_id, context, risk):
        self._audit.append({
            "event": event,
            "request_id": request_id,
            "context": context,
            "risk": risk,
            "at": time.time(),
        })
        if len(self._audit) > 200:
            self._audit = self._audit[-200:]

    def audit_trail(self):
        return list(self._audit)


# Shared authority — a single instance used by the registry, tools and Brain.
CONFIRMATION = ConfirmationManager()

__all__ = [
    "ConfirmationManager",
    "CONFIRMATION",
    "risk_of",
    "resolve_yes_no",
]