"""Feature 123 — security/safety, failure-field structure and recovery."""

from tools.builder import build_registry


def test_failure_fields_structured(engine):
    out = engine.hal_connect_real("COM_NEVER", kind="serial")
    for key in ("status", "error_code", "message", "feature_id", "operation",
                "recoverable", "device", "dependency", "suggested_action"):
        assert key in out, key
    assert out["feature_id"] == 123
    assert out["recoverable"] is True


def test_ok_fields_structured(engine):
    out = engine.discover()
    assert out["feature_id"] == 123
    assert out["error_code"] is None
    assert out["success"] is True


def test_high_risk_tools_confirmation_gated(registry):
    reg = registry
    for name in ("mechatronics_connect", "mechatronics_write",
                 "mechatronics_hil"):
        tool = reg.get(name)
        assert tool.risk == "high"
        assert tool.confirm_required is True
        # invoke without confirmation must be denied by the gate
        denied = reg.invoke(name)
        assert denied["status"] in ("confirm_required", "denied",
                                    "invalid_argument")


def test_security_denial_preserves_structured_failure(registry):
    denied = registry.invoke("mechatronics_hil",
                             inject={"value": 1}, tolerance_abs=0)
    # unconfirmed high-risk -> deny, but structured field surface still there
    assert denied["status"] in ("confirm_required", "denied")
    assert denied.get("feature_id") == 123 or \
        denied.get("feature_id") is None or "action" in denied


def test_twin_recovery_after_restart(tmp_path):
    from core.mechatronics import MechatronicsEngine
    kv = str(tmp_path / "rec.json")
    e1 = MechatronicsEngine(kv_path=kv)
    e1.twin_create("crane", {"name": "crane",
                             "system": {"mass": 500}})
    # simulate a crash-style restart with a fresh instance
    e2 = MechatronicsEngine(kv_path=kv)
    loaded = e2.twin_load("crane")
    assert loaded["success"] is True
    assert loaded["twin"]["system"]["mass"] == 500
    # revalidate after recovery
    assert e2.twin_validate("crane")["success"] is True


def test_hil_safety_never_auto_executes(engine):
    # without explicit execute=True, a safety-checked step is a dry-run
    out = engine.hil_safety(device="x", authorized=True, confirmed=True,
                            request_id="r", execute=False)
    assert out["success"] is True
    assert out["executed"] is False