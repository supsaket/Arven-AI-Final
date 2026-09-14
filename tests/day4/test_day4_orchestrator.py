"""Day 4 — Feature 111: Advanced Autonomous Command & Mission Orchestration.

The orchestrator is always bounded and gated: high-risk steps need approval,
failures are honest, and paused missions resume from the persisted record.
"""

import os

import pytest

from core.kv import KeyValueStore
from core.mission_orchestrator import MissionOrchestrator
from core.missions import MissionsEngine
from core.planner import AdaptivePlanner


def _orch(tmp_path):
    data = tmp_path / "orch"
    data.mkdir(parents=True, exist_ok=True)
    missions = MissionsEngine(path=str(data / "missions.json"))
    return MissionOrchestrator(
        kv_path=str(data / "orch.json"),
        report_dir=str(tmp_path / "reports"),
        planner=AdaptivePlanner(kv=KeyValueStore(str(data / "planner.json"))),
        missions=missions)


def test_capable_is_honest(tmp_path, registry):
    orch = MissionOrchestrator(kv_path=str(tmp_path / "orch.json"),
                               registry=registry)
    out = orch.capable("check harness software")
    linked = any("software" in tool for tool in out["tools"])
    assert out["supported"] is True
    assert linked
    empty = orch.capable("")
    assert empty["supported"] is False


def test_run_completes_real_steps(tmp_path):
    orch = _orch(tmp_path)
    out = orch.run("check software",
                   [{"title": "software", "tool": "capability_software",
                     "args": {}}])
    assert out["success"] is True
    assert out["status"] == "COMPLETE"
    record = out["step_records"][0]
    assert record["status"] == "done"
    assert record["tool"] == "capability_software"


def test_high_risk_step_blocked_without_approval(tmp_path):
    orch = _orch(tmp_path)
    out = orch.run("shell",
                   [{"title": "shell", "tool": "run_shell",
                     "args": {"command": "echo hi"}}],
                   approve=False)
    assert out["step_records"][0]["status"] == "failed"
    assert out["status"] != "COMPLETE"


def test_high_risk_step_runs_with_approval(tmp_path):
    orch = _orch(tmp_path)
    out = orch.run("shell2",
                   [{"title": "shell", "tool": "run_shell",
                     "args": {"command": "echo ok"}}],
                   approve=True)
    assert out["step_records"][0]["status"] == "done"
    assert out["status"] == "COMPLETE"


def test_planning_only_steps_never_execute(tmp_path):
    orch = _orch(tmp_path)
    out = orch.run("planning",
                   [{"title": "no registered tool", "tool": None,
                     "args": {}}])
    assert out["status"] != "COMPLETE"
    assert out["step_records"][0]["note"] == "planning-only step"


def test_resume_after_pause_executes_open_steps(tmp_path):
    orch = _orch(tmp_path)
    created = orch.create("paused",
                          [{"title": "s", "tool": "capability_software",
                            "args": {}}])
    mission_id = created["mission_id"]
    orch._missions_instance().pause(mission_id, reason="test pause")
    out = orch.resume(mission_id, approve=True)
    assert out["status"] == "COMPLETE"


def test_resume_from_fresh_engine_uses_persisted_steps(tmp_path):
    orch1 = _orch(tmp_path)
    created = orch1.create("persist",
                           [{"title": "s", "tool": "capability_software",
                             "args": {}}])
    mission_id = created["mission_id"]
    orch1._missions_instance().pause(mission_id, reason="kill")
    orch2 = _orch(tmp_path)  # brand-new engine, same stores
    out = orch2.resume(mission_id, approve=False)
    assert out["status"] == "COMPLETE"


def test_cancel_marks_mission_cancelled(tmp_path):
    orch = _orch(tmp_path)
    created = orch.create("cancelme",
                          [{"title": "s", "tool": "capability_software",
                            "args": {}}])
    mission_id = created["mission_id"]
    out = orch.cancel(mission_id)
    assert out["success"] is True
    mission = orch._missions_instance().get_mission(mission_id)
    assert mission["status"] == "failed"  # cancellation is audited, honest


def test_report_writes_markdown_artifact(tmp_path):
    orch = _orch(tmp_path)
    created = orch.run("do it",
                       [{"title": "s", "tool": "capability_software",
                         "args": {}}])
    out = orch.report(created["mission_id"])
    assert out["success"] is True
    assert os.path.exists(out["path"])
    with open(out["path"], encoding="utf-8") as handle:
        assert "do it" in handle.read()


def test_registry_orchestrate_is_gated(registry):
    out = registry.invoke("orchestrate", goal="x", steps="capability_software")
    assert out["status"] == "confirm_required"
    assert out["success"] is False


def test_registry_orchestrator_status(registry):
    out = registry.invoke("orchestrator_status")
    assert out["success"] is True
    assert "active_missions" in out
    assert out["registry_tools"] == 436