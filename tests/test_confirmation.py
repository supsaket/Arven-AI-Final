"""Confirmation / trust system contract (row 32)."""

from core.confirmation import ConfirmationManager, risk_of
from core.recovery import ExecutionGuard


class TestPendingWorkflow:

    def test_require_approve(self):
        manager = ConfirmationManager()
        request_id = manager.require("delete file X", "high")
        assert manager.is_pending(request_id) is True
        ok, _ = manager.approve(request_id)
        assert ok is True
        assert manager.is_pending(request_id) is False

    def test_deny(self):
        manager = ConfirmationManager()
        request_id = manager.require("send email", "high")
        ok, _ = manager.deny(request_id)
        assert ok is True

    def test_cancel_pending_never_executes(self):
        manager = ConfirmationManager()
        request_id = manager.require("delete folder", "destructive")
        manager.cancel(request_id)
        allowed, _ = manager.gate("delete folder", confirmed=True,
                                  trusted=True, request_id=request_id)
        assert allowed is False

    def test_approve_missing_request(self):
        manager = ConfirmationManager()
        ok, reason = manager.approve("missing")
        assert ok is False

    def test_resolve_free_text(self):
        manager = ConfirmationManager()
        request_id = manager.require("run shell")
        ok, _ = manager.resolve(request_id, "yes")
        assert ok is True

    def test_audit_trail_recorded(self):
        manager = ConfirmationManager()
        request_id = manager.require("delete file")
        manager.approve(request_id)
        events = [e["event"] for e in manager.audit_trail()]
        assert "pending" in events
        assert "approved" in events


class TestTrust:

    def test_trust_expires(self):
        manager = ConfirmationManager(trust_ttl=0)
        request_id = manager.require("run shell")
        manager.approve(request_id, scope="shell")
        assert manager.is_trusted("shell") is False

    def test_trust_with_ttl(self):
        manager = ConfirmationManager(trust_ttl=300)
        request_id = manager.require("run shell")
        manager.approve(request_id, scope="shell")
        assert manager.is_trusted("shell") is True
        assert manager.trust_expires_at("shell") is not None


class TestGate:

    def test_destructive_never_auto_trusted(self):
        manager = ConfirmationManager()
        manager._trust["scope"] = 10**12  # pretend long-lived trust
        allowed, _ = manager.gate("delete file", trusted=True)
        assert allowed is False

    def test_high_requires_confirmation(self):
        manager = ConfirmationManager()
        allowed, _ = manager.gate("run shell", confirmed=False)
        assert allowed is False

    def test_low_passes(self):
        manager = ConfirmationManager()
        allowed, _ = manager.gate("date_time")
        assert allowed is True

    def test_destructive_gate_needs_all(self):
        manager = ConfirmationManager()
        request_id = manager.require("delete file", "destructive")
        allowed, _ = manager.gate("delete file", confirmed=True,
                                  trusted=True, request_id=request_id)
        assert allowed is True


class TestRiskOf:

    def test_risk_of_extracts_from_dict(self):
        assert risk_of({"risk": "high"}) == "high"
        assert risk_of("text") is None
        assert risk_of({}) is None


class TestExecutionGuardNotLocked:

    def test_guard_acquire_and_release(self):
        guard = ExecutionGuard()
        assert guard.acquire("key") is True
        assert guard.release("key") is True

    def test_guard_rejects_double_acquire(self):
        guard = ExecutionGuard()
        assert guard.acquire("key") is True
        assert guard.acquire("key", timeout=0) is False
        guard.release("key")