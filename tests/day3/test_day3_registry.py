"""Day 3 registry gates (T2/T3/T9)."""

import pytest

from core.confirmation import CONFIRMATION
from tools.registry import Tool, ToolError, ToolRegistry


def test_registry_has_all_day2_tools(registry, names):
    assert len(names) == 436
    assert "diagnostics_run" in names
    assert "plan_list" in names
    assert "backup_list" in names
    assert "cyber_scan" in names


def test_registry_describe_unknown(registry):
    assert registry.describe("no_such_tool")["error"] == "unknown tool"


def test_registry_duplicate_registration_raises():
    fresh = ToolRegistry()
    fresh.register(Tool("dup_x", lambda: {"ok": True}))
    with pytest.raises(ToolError):
        fresh.register(Tool("dup_x", lambda: {"ok": True}))


def test_registry_invoke_unknown_is_honest(registry):
    out = registry.invoke("no_such_tool_zzz")
    assert out["status"] == "error"
    assert out["success"] is False
    assert "unknown tool" in out["message"]


def test_high_risk_gated_prompt(registry):
    out = registry.invoke("cyber_scan", target="https://example.com")
    assert out["status"] == "confirm_required"
    assert out["success"] is False


def test_high_risk_gate_needs_pending_request(registry):
    rid = CONFIRMATION.require("day3.registry.cyber")
    assert CONFIRMATION.is_pending(rid) is True
    out = registry.invoke("cyber_scan", target="https://example.com",
                          confirmed=True, request_id=rid)
    assert out["status"] == "AUTHORIZATION_REQUIRED"  # passed the gate
    assert CONFIRMATION.is_pending(rid) is False        # consumed


def test_high_risk_gate_denies_stale_request(registry):
    before = len(CONFIRMATION.audit_trail())
    out = registry.invoke("cyber_scan", target="https://example.com",
                          confirmed=True, request_id="cfm-garbage")
    assert out["status"] == "denied"
    assert out["success"] is False
    assert "confirmation" in out["message"]


def test_destructive_tool_never_auto_trusted():
    fresh = ToolRegistry()
    calls = []
    tool = Tool("test_destructive_xyz",
                function=lambda: (calls.append(1) or {"ok": True, "count": len(calls)}),
                risk="destructive", confirm_required=True)
    fresh.register(tool)

    out = fresh.invoke("test_destructive_xyz")
    assert out["status"] == "confirm_required"

    out = fresh.invoke("test_destructive_xyz", confirmed=True)
    assert out["status"] == "denied"          # trusted missing
    assert calls == []

    rid = CONFIRMATION.require("day3.registry.destructive")
    out = fresh.invoke("test_destructive_xyz", confirmed=True, trusted=True,
                       request_id=rid)
    assert out["success"] is True            # trusted + confirmed + pending
    assert calls == [1]

    out = fresh.invoke("test_destructive_xyz")  # second call ungated again
    assert calls == [1]
    assert out["status"] == "confirm_required"


def test_unavailable_backend_denied():
    fresh = ToolRegistry()
    fresh.register(Tool("test_unavail_xyz", lambda: {"ok": True},
                        available=False))
    out = fresh.invoke("test_unavail_xyz")
    assert out["status"] == "unavailable"
    assert out["success"] is False


def test_undeclared_argument_rejected(registry):
    out = registry.invoke("diagnostics_run", surprise="x")
    assert out["status"] == "invalid_argument"

    out = registry.invoke("diagnostics_run", confirmed=True)  # gate params ok
    assert "confirmed" not in (out.get("status") or "")


def test_missing_required_argument_honest(registry):
    out = registry.invoke("backup_snapshot")
    assert out["status"] == "invalid_argument"
    assert out["message"].startswith("missing required argument")


def test_capabilities_keywords(registry):
    caps = registry.capabilities()
    assert "cyber" in caps
    assert "diagnostics" in caps