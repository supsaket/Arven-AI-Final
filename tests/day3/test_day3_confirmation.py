"""Day 3 confirmation workflow (T2/T3/T9)."""

import time

import pytest

from core.confirmation import ConfirmationManager, CONFIRMATION, risk_of
from core.safety import RISK_DESTRUCTIVE, RISK_HIGH, RISK_MEDIUM


def test_require_and_approve_flow():
    mgr = ConfirmationManager(ttl=60)
    rid = mgr.require("test.action", risk=RISK_HIGH)
    assert rid.startswith("cfm-")
    assert mgr.is_pending(rid) is True
    ok, reason = mgr.approve(rid)
    assert ok is True
    assert mgr.is_pending(rid) is False
    assert reason == "approved"


def test_double_approve_rejected():
    mgr = ConfirmationManager(ttl=60)
    rid = mgr.require("test.action", risk=RISK_HIGH)
    mgr.approve(rid)
    ok, reason = mgr.approve(rid)   # already consumed
    assert ok is False
    assert "no such pending" in reason


def test_deny_and_audit_trail_recorded():
    mgr = ConfirmationManager(ttl=60)
    rid = mgr.require("test.action", risk=RISK_HIGH)
    ok, _ = mgr.deny(rid)
    assert ok is True
    events = [e["event"] for e in mgr.audit_trail()]
    assert "pending" in events
    assert "denied" in events


def test_expiry_expires_pending():
    mgr = ConfirmationManager(ttl=0.05)
    rid = mgr.require("test.action", risk=RISK_HIGH)
    time.sleep(0.1)
    assert mgr.is_pending(rid) is False
    ok, reason = mgr.approve(rid)
    assert ok is False
    assert "expired" in reason


def test_resolve_yes_no_vocabulary():
    mgr = ConfirmationManager(ttl=60)
    assert mgr.resolve_yes_no("yes") is True
    assert mgr.resolve_yes_no("no") is False
    assert mgr.resolve_yes_no("maybe") is None
    rid = mgr.require("t", risk=RISK_HIGH)
    ok, _ = mgr.resolve(rid, "yes")
    assert ok is True
    rid2 = mgr.require("t", risk=RISK_HIGH)
    ok2, msg = mgr.resolve(rid2, "banana")
    assert ok2 is False
    assert "say yes or no" in msg


def test_gate_medium_needs_no_confirmation():
    mgr = ConfirmationManager(ttl=60)
    allowed, reason = mgr.gate("backup_list")
    assert allowed is True


def test_gate_high_needs_pending_request():
    mgr = ConfirmationManager(ttl=60)
    action = "send mail to a@b.com"   # classified HIGH by SAFETY
    allowed, reason = mgr.gate(action, confirmed=True)
    assert allowed is False

    rid = mgr.require("high", risk=RISK_HIGH)
    allowed, reason = mgr.gate(action, confirmed=True, request_id=rid)
    assert allowed is True
    assert mgr.is_pending(rid) is False     # consumed by the gate


def test_gate_destructive_trusted_pending():
    mgr = ConfirmationManager(ttl=60)
    action = "wipe volume"          # classified DESTRUCTIVE by SAFETY
    allowed, reason = mgr.gate(action, confirmed=True, trusted=True)
    assert allowed is False
    rid = mgr.require("destructive", risk=RISK_DESTRUCTIVE)
    allowed, reason = mgr.gate(action, confirmed=True, trusted=True,
                               request_id=rid)
    assert allowed is True


def test_shared_authority_is_real():
    rid = CONFIRMATION.require("day3.confirmation.global")
    assert CONFIRMATION.is_pending(rid) is True
    ok, _ = CONFIRMATION.resolve(rid, "yes")
    assert ok is True


def test_risk_of_extracts_from_dict():
    assert risk_of({"risk": "high"}) == "high"
    assert risk_of({"risk": None}) is None
    assert risk_of("nope") is None