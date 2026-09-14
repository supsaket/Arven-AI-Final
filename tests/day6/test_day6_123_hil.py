"""Feature 123 — HIL engine, safety, faults, BOM and wiring validation."""


def test_hil_pass_with_tolerance(engine):
    out = engine.hil_run({"value": 10}, expected=10.0, measured=9.0,
                         tolerance_abs=2.0)
    assert out["success"] is True
    assert out["verdict"] == "PASS"
    assert out["absolute_error"] == 1.0
    assert out["max_deviation"] == 1.0


def test_hil_fail_with_tolerance(engine):
    out = engine.hil_run({"value": 10}, expected=10.0, measured=5.0,
                         tolerance_abs=1.0)
    assert out["verdict"] == "FAIL"


def test_hil_inconclusive_without_tolerance(engine):
    out = engine.hil_run({"value": 10}, expected=10.0, measured=9.0)
    assert out["verdict"] == "INCONCLUSIVE"


def test_hil_relative_tolerance(engine):
    out = engine.hil_run({"value": 100}, expected=100.0, measured=99.0,
                         tolerance_rel=0.02)
    assert out["verdict"] == "PASS"
    assert out["relative_error"] < 0.02


def test_hil_metrics_present(engine):
    out = engine.hil_run({"value": 10}, expected=10.0, measured=8.0,
                         tolerance_abs=1.0)
    for metric in ("rmse", "mean_deviation", "max_deviation"):
        assert metric in out


def test_hil_requires_value(engine):
    out = engine.hil_run({})
    assert out["status"] == "VALIDATION_FAILED"


def test_hil_safety_blocks_without_authorization(engine):
    out = engine.hil_safety(device=None, authorized=False, confirmed=False,
                            request_id=None)
    assert out["success"] is False
    assert out["status"] == "SAFETY_DENIED"
    assert out["feature_id"] == 123


def test_hil_safety_blocks_on_estop(engine):
    out = engine.hil_safety(device="x", authorized=True, confirmed=True,
                            request_id="rid", estop=True)
    assert out["status"] == "SAFETY_DENIED"


def test_hil_safety_allows_confirmed_execute(engine):
    out = engine.hil_safety(device="x", limits={"max_current": 2.0},
                            authorized=True, confirmed=True,
                            request_id="rid", execute=True)
    assert out["success"] is True
    assert out["allowed"] is True
    assert out["executed"] is True
    assert any(c["check"] == "estop" and c["pass"] for c in out["checks"])


# --------------------------------------------------------------------------
# Fault detection
# --------------------------------------------------------------------------
def test_fault_out_of_range(engine):
    out = engine.fault_detect("out_of_range", series=[1.0, 5.0, -2.0],
                              limits={"min": 0, "max": 3})
    assert out["success"] is True
    assert out["detected"] is True
    assert any(f["type"] == "out_of_range" for f in out["faults"])


def test_fault_saturation(engine):
    out = engine.fault_detect("saturation", series=[0.5, 1.0, 1.2], sat=1.0)
    assert any(f["type"] == "saturation" for f in out["faults"])


def test_fault_timeout(engine):
    out = engine.fault_detect("timeout", timeout=2)
    assert any(f["type"] == "timeout" for f in out["faults"])


def test_fault_clean_series(engine):
    out = engine.fault_detect("out_of_range", series=[1.0, 2.0, 3.0],
                              limits={"min": 0, "max": 5})
    assert out["faults"] == []
    assert out.get("detected") is not True


def test_fault_disconnect(engine):
    out = engine.fault_detect("disconnect")
    assert any(f["type"] == "disconnect" for f in out["faults"])


# --------------------------------------------------------------------------
# BOM honesty
# --------------------------------------------------------------------------
def test_bom_no_invented_prices(engine):
    out = engine.bom([{"name": "MCU", "qty": 1, "unit_cost": None},
                      {"name": "Driver", "qty": 2}])
    assert out["success"] is True
    assert out["estimated"] is False
    for row in out["rows"]:
        assert row["price_available"] is False
        assert "not invented" in row["note"]
    assert out["line_total"] == 0.0


def test_bom_with_known_price(engine):
    out = engine.bom([{"name": "MCU", "qty": 2, "unit_cost": 3.5}])
    assert out["rows"][0]["price_available"] is True
    assert out["line_total"] == 7.0


def test_bom_requires_items(engine):
    out = engine.bom()
    assert out["status"] == "VALIDATION_FAILED"


# --------------------------------------------------------------------------
# Wiring / interface plan
# --------------------------------------------------------------------------
def test_wiring_duplicate_detected(engine):
    nets = [{"source": "A", "dest": "B"}, {"source": "A", "dest": "B"}]
    out = engine.wiring(nets=nets)
    assert out["success"] is True
    assert out["valid"] is False
    assert any(p["problem"] == "duplicate net" for p in out["problems"])


def test_wiring_missing_endpoint(engine):
    nets = [{"source": "A"}]
    out = engine.wiring(nets=nets)
    assert out["valid"] is False
    assert any(p["problem"] == "missing endpoint" for p in out["problems"])


def test_wiring_ok(engine):
    nets = [{"source": "MCU.PW1", "dest": "MOTOR.PA0"}]
    out = engine.wiring(nets=nets, interfaces=["pwm"])
    assert out["valid"] is True
    assert out["problems"] == []
    assert out["interfaces"] == ["pwm"]


def test_wiring_requires_net(engine):
    out = engine.wiring()
    assert out["status"] == "VALIDATION_FAILED"