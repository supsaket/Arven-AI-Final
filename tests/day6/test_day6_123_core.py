"""Feature 123 — Mechatronics Co-Design & Hardware-in-the-Loop engine: core.

Verifies the deterministic design/analysis layers: system spec validation,
mechanical math (with traceability), electrical sanity checks, electronics
architecture, kinematics (FK/IK + joint limits), PID control, sensor/actuator
models, and the engineering validation report.
"""

import math

from core import mechatronics as mech

from tools.builder import build_registry


def test_engine_imports_and_singleton():
    e = mech.engine()
    assert e is not None
    assert mech._FEATURE_ID == 123


# --------------------------------------------------------------------------
# System specification + persistence
# --------------------------------------------------------------------------
def test_create_system_persists(engine):
    out = engine.create_system(
        "rov", requirements=["hold heading"], mass=12.0, dims={"x": 1, "y": 2, "z": 3})
    assert out["success"] is True
    assert out["system"]["mass"] == 12.0
    saved = engine.kv.get("system:rov")
    assert saved["name"] == "rov"
    assert saved["dimensions"]["y"] == 2.0


def test_create_system_requires_name(engine):
    out = engine.create_system("")
    assert out["success"] is False
    assert out["status"] == "VALIDATION_FAILED"
    assert out["error_code"] == "VALIDATION_FAILED"
    assert out["feature_id"] == 123


# --------------------------------------------------------------------------
# Mechanical analysis (traceable) + COM + actuator sizing
# --------------------------------------------------------------------------
def test_mechanical_shaft_power_traceability(engine):
    out = engine.mechanical(torque=2.0, rpm=3000)
    assert out["success"] is True
    steps = out["results"]
    assert any(s["quantity"] == "shaft_power" for s in steps)
    sp = next(s for s in steps if s["quantity"] == "shaft_power")
    expected = 2.0 * (2 * math.pi * 3000 / 60.0)
    assert abs(sp["RESULT"] - expected) < 1e-6
    assert sp["UNITS"] == "W"
    assert "INPUT" in sp and "FORMULA" in sp and "ASSUMPTIONS" in sp


def test_mechanical_requires_input(engine):
    out = engine.mechanical()
    assert out["success"] is False
    assert out["status"] == "VALIDATION_FAILED"


def test_center_of_mass(engine):
    out = engine.center_of_mass([{"mass": 1, "x": 0, "y": 0, "z": 0},
                                 {"mass": 3, "x": 4, "y": 0, "z": 0}])
    assert out["success"] is True
    assert out["center_of_mass"][0] == 3.0
    assert out["total_mass"] == 4.0


def test_actuator_sizing(engine):
    out = engine.actuator_sizing(mass=10.0, friction=0.2, acceleration=2.0,
                                 radius=0.1, efficiency=0.8, safety_factor=1.5)
    assert out["success"] is True
    weight = 10.0 * mech._G
    expect = (weight + 0.2 * weight + 20.0) * 1.5 / 0.8
    assert abs(out["force_sized"] - expect) < 1e-6
    assert abs(out["torque_sized"] - expect * 0.1) < 1e-6


# --------------------------------------------------------------------------
# Electrical + power budget
# --------------------------------------------------------------------------
def test_electrical_ohms_law_and_power(engine):
    out = engine.electrical(voltage=12, current=2)
    assert out["success"] is True
    formulas = [s["FORMULA"] for s in out["results"]]
    assert any(f.startswith("P=V*I") for f in formulas)


def test_electrical_rejects_negative(engine):
    out = engine.electrical(voltage=-5, current=1)
    assert out["success"] is False
    assert out["status"] == "VALIDATION_FAILED"


def test_power_budget_duty_cycle(engine):
    out = engine.power_budget([
        {"name": "motor", "voltage": 12, "current": 2.0, "duty": 0.5},
        {"name": "sensor", "voltage": 5, "current": 0.1, "duty": 1.0},
    ])
    assert out["success"] is True
    assert abs(out["average_power"] - (24 * 0.5 + 0.5)) < 1e-6


# --------------------------------------------------------------------------
# Electronics architecture
# --------------------------------------------------------------------------
def test_electronics_architecture(engine):
    out = engine.electronics_architecture(
        mcu="ESP32", sensors=["imu"], actuators=["servo"],
        drivers=["pwm"], comms=["uart"], power_rails=["5V"], protection=["fuse"])
    assert out["success"] is True
    assert out["architecture"]["mcu"] == "ESP32"
    assert engine.kv.get("architecture")["mcu"] == "ESP32"


# --------------------------------------------------------------------------
# Robotics / kinematics
# --------------------------------------------------------------------------
def test_forward_kinematics_link_count(engine):
    links = [{"length": 1, "offset": 0, "alpha": 0}]
    out = engine.forward_kinematics(links, [0.5])
    assert out["success"] is True
    assert len(out["frames"]) == 2


def test_ik_planar_2r_rejects_outside_workspace(engine):
    links = [{"length": 1, "offset": 0, "alpha": 0} for _ in range(2)]
    out = engine.inverse_kinematics(links, [5.0, 0.0])
    assert out["success"] is False
    assert out["operation"] == "mechatronics/kinematics/ik"
    assert out["recoverable"] is True


def test_ik_planar_2r_closed_form(engine):
    links = [{"length": 1, "offset": 0, "alpha": 0} for _ in range(2)]
    target = [1.0, 1.0]
    out = engine.inverse_kinematics(links, target)
    assert out["success"] is True
    t1, t2 = out["joints"]
    fx = math.cos(t1) + math.cos(t1 + t2)
    fy = math.sin(t1) + math.sin(t1 + t2)
    assert abs(fx - target[0]) < 1e-6
    assert abs(fy - target[1]) < 1e-6


def test_joint_limits_violation(engine):
    out = engine.joint_limits([{"joint": "j1", "min": -1, "max": 1,
                                "angle": 3}])
    assert out["success"] is False
    assert out["operation"] == "mechatronics/kinematics/limits"
    assert out["data"]["violations"][0]["joint"] == "j1"


# --------------------------------------------------------------------------
# Control (PID)
# --------------------------------------------------------------------------
def test_pid_sim_converges(engine):
    out = engine.pid_tune(kp=2.0, ki=0.5, kd=0.1, setpoint=1.0, steps=500,
                          dt=0.05, saturation=10.0)
    assert out["success"] is True
    assert abs(out["final_output"] - 1.0) < 0.05


def test_pid_sim_rejects_bad_dt(engine):
    out = engine.pid_tune(kp=1, ki=0, kd=0, setpoint=1, dt=0)
    assert out["success"] is False


# --------------------------------------------------------------------------
# Sensor / actuator models
# --------------------------------------------------------------------------
def test_sensor_model_offset_and_range(engine):
    out = engine.sensor_model("imu", 1.0, scale=2.0, offset=1.0)
    assert out["success"] is True
    assert out["measured"] == 3.0
    bad = engine.sensor_model("imu", 1.0, max_range=0.9)
    assert bad["success"] is False
    assert bad["status"] == "OUT_OF_RANGE"
    assert bad["device"] == "imu"


def test_actuator_model_current_limit(engine):
    out = engine.actuator_model("servo", 5.0, current_limit=0.3)
    assert out["success"] is False
    assert out["status"] == "CURRENT_LIMIT"


# --------------------------------------------------------------------------
# Engineering validation report
# --------------------------------------------------------------------------
def test_validation_report_overall(engine):
    good = engine.validation_report()
    assert good["overall"] in ("PASS", "INCOMPLETE")
    broken = engine.validation_report(results={"Electrical": "FAIL"})
    assert broken["overall"] == "INCOMPLETE"
    assert "Electrical" in broken["failed"]


# --------------------------------------------------------------------------
# Registry integrity for feature 123
# --------------------------------------------------------------------------
def test_feature123_tools_registered(names):
    expected = {"mechatronics_create_system", "mechatronics_validate",
                "mechatronics_simulate", "mechatronics_discover",
                "mechatronics_connect", "mechatronics_disconnect",
                "mechatronics_read", "mechatronics_write", "mechatronics_hil",
                "mechatronics_diagnostics", "mechatronics_bom",
                "mechatronics_interfaces"}
    assert expected <= set(names)


def test_feature123_tool_risk_gates(registry):
    for name in ("mechatronics_connect", "mechatronics_write",
                 "mechatronics_hil"):
        assert registry.get(name).risk == "high"
    for name in ("mechatronics_discover", "mechatronics_diagnostics"):
        assert registry.get(name).risk == "low"


def test_feature123_catalog_row(registry):
    from core.features import feature
    row = feature(123)
    assert row is not None
    for tool in row["tools"]:
        assert tool in registry.names()