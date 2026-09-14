"""Feature 123 — deterministic simulation + digital twin lifecycle."""

import json


def test_simulate_is_deterministic(engine):
    a = engine.simulate(duration=2.0, dt=0.05)
    b = engine.simulate(duration=2.0, dt=0.05)
    assert a["success"] is True
    assert a["deterministic"] is True
    assert a["final_velocity"] == b["final_velocity"]
    assert a["model"] == "first_order_velocity"


def test_simulate_rejects_zero_dt(engine):
    out = engine.simulate(duration=1.0, dt=0)
    assert out["success"] is False
    assert out["status"] == "VALIDATION_FAILED"
    assert out["feature_id"] == 123


def test_twin_create_save_load(engine):
    out = engine.twin_create("arm", {"name": "arm",
                                     "system": {"motion": {"target_velocity": 1.0}}})
    assert out["success"] is True
    loaded = engine.twin_load("arm")
    assert loaded["success"] is True
    assert loaded["twin"]["name"] == "arm"


def test_twin_modify_and_reload(engine):
    engine.twin_create("leg", {"name": "leg"})
    engine.twin_modify("leg", {"state": {"knee": 30}})
    loaded = engine.twin_load("leg")
    assert loaded["twin"]["state"]["knee"] == 30


def test_twin_validate_incomplete(engine):
    engine.twin_create("ghost")
    out = engine.twin_validate("ghost")
    assert out["success"] is True
    assert out["valid"] is False
    assert "missing system definition" in out["problems"]


def test_twin_validate_complete(engine):
    engine.twin_create("ok", {"name": "ok",
                              "system": {"motion": {}}} )
    out = engine.twin_validate("ok")
    assert out["valid"] is True


def test_twin_export_writes_json(engine):
    engine.twin_create("exp", {"name": "exp"})
    out = engine.twin_export("exp")
    assert out["success"] is True
    with open(out["path"], encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["name"] == "exp"


def test_twin_simulate_records_history(engine):
    engine.twin_create("dyn", {"name": "dyn",
                               "system": {"motion": {"target_velocity": 2.0,
                                                     "kp": 2.0}}})
    out = engine.twin_simulate("dyn", duration=2.0, dt=0.1)
    assert out["success"] is True
    twin = engine.twin_load("dyn")["twin"]
    assert len(twin["simulations"]) == 1
    # P-only closed-loop steady state: v = kp*target/(1+kp) = 4/3
    assert abs(out["final_velocity"] - (4.0 / 3.0)) < 0.05


def test_twin_persistence_across_instances(tmp_path):
    from core.mechatronics import MechatronicsEngine
    kv = str(tmp_path / "persist.json")
    e1 = MechatronicsEngine(kv_path=kv)
    e1.twin_create("mine", {"name": "mine", "system": {"motion": {}}})
    e2 = MechatronicsEngine(kv_path=kv)
    loaded = e2.twin_load("mine")
    assert loaded["success"] is True
    assert loaded["twin"]["name"] == "mine"


def test_stray_kv_never_written_to_default(tmp_path):
    # engine created with tmp kv must not touch data/mechatronics.json
    from core.mechatronics import MechatronicsEngine
    e = MechatronicsEngine(kv_path=str(tmp_path / "iso.json"))
    assert e.kv.path == str(tmp_path / "iso.json")