"""Feature 113 — Mission steering + feature 114 reasoning control."""

import core.mission_steering as ms
import core.reasoning_control as rc


def test_classify_kinds(tmp_path):
    steered = ms.MissionSteering(kv_path=str(tmp_path / "classify.json"))
    out = steered.classify(
        "Continue building the pcb design and then test it")
    assert out["kind"] in ms.STEERING_KINDS
    assert out["reason"]


def test_steering_status_and_history(tmp_path):
    steering = ms.MissionSteering(kv_path=str(tmp_path / "steer.json"))
    out = steering.status()
    assert "total_events" in out
    assert "by_kind" in out
    hist = steering.history()
    assert isinstance(hist, list)


def test_reasoning_estimate_and_set(tmp_path):
    control = rc.ReasoningControl(kv_path=str(tmp_path / "reason.json"))
    estimate = control.estimate("complex design with three subsystems")
    assert estimate["success"] is True
    assert estimate["estimated_level"] in rc.LEVELS
    changed = control.set_level("HIGH")
    assert changed["level"] == "HIGH"


def test_reasoning_invalid_level_fails_honestly(tmp_path):
    control = rc.ReasoningControl(kv_path=str(tmp_path / "reason.json"))
    out = control.set_level("quantum")
    assert out["success"] is False
    assert "invalid" in out.get("status",
                                out.get("message", "")).lower()