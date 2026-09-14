"""Day 2 focused tests: Command Center (98), Multimodal (107),
Robotics/Automation (94) + Actuation/Learning (108), Engineering (95).
Provider probes are shallow; no real network or robot hardware."""

import os

import pytest

from core.command_center import CommandCenter
from core.engineering import EngineeringProjects
from core.kv import KeyValueStore
from core.multimodal import MultimodalInput
from core.robot import RobotController


@pytest.fixture
def kv(tmp_path):
    return KeyValueStore(str(tmp_path / "kv.json"))


# ----------------------------------------------------------------------
# 98 Command Center / Admin
# ----------------------------------------------------------------------

class TestCommandCenter:

    def test_dashboard_fields_present(self, kv, tmp_path):
        center = CommandCenter(kv=kv, workspace_root=str(tmp_path))
        dash = center.dashboard()
        for field in ("providers", "provider_statuses", "capabilities",
                      "tools", "memory", "scheduler", "selftest",
                      "workspace", "flags", "generated_at"):
            assert field in dash
        assert dash["tools"]["count"] >= 1
        assert isinstance(dash["tools"]["names"], list)
        assert dash["generated_at"]

    def test_health_rollup(self, kv, tmp_path):
        center = CommandCenter(kv=kv, workspace_root=str(tmp_path))
        rollup = center.health_rollup()
        assert rollup["worst_status"] in (
            "AVAILABLE", "UNAVAILABLE", "OFFLINE", "REQUIRES_AUTH",
            "REQUIRES_PERMISSION", "NOT_CONFIGURED", "FAILED",
        )
        assert rollup["rolled_up"] is True

    def test_selftest_passthrough(self, kv):
        center = CommandCenter(kv=kv)
        result = center.run_selftest()
        assert "total" in result
        assert "passed" in result
        assert "failed" in result
        assert result["total"] >= 0

    def test_flag_audit(self, kv):
        center = CommandCenter(kv=kv)
        center.set_flag("maintenance_mode", "on", by="unit test")
        assert center.flags()["maintenance_mode"] == "on"
        audit = center.flag_audit("maintenance_mode")
        assert audit and audit[0]["value"] == "on"


# ----------------------------------------------------------------------
# 107 Multimodal Interaction
# ----------------------------------------------------------------------

class TestMultimodal:

    def test_ingest_classification(self, kv):
        input_ = MultimodalInput(kv=kv)
        record = input_.ingest({"text": "hello"})
        assert record["modalities"] == ["text"]
        assert record["turn_id"]
        record = input_.ingest({"text": "see", "image_path": "pic.png"})
        assert record["modalities"] == ["text", "image"]
        record = input_.ingest({"audio_text": "transcript", "speaker": "saket"})
        assert record["modalities"] == ["audio"]

    def test_route_records_channels(self, kv):
        input_ = MultimodalInput(kv=kv)
        routed = input_.route({"text": "hello boss"})
        assert routed["modalities"] == ["text"]
        assert routed["results"][0]["channel"] == "conversation"
        assert routed["results"][0]["status"] == "AVAILABLE"
        assert len(input_.conversation_records()) == 1

    def test_image_route_honest(self, kv):
        input_ = MultimodalInput(kv=kv)
        routed = input_.route({"image_path": str(os.path.abspath(__file__))})
        image_result = [r for r in routed["results"]
                        if r["modality"] == "image"][0]
        # either delegated to vision or honestly unconfigured — never fabricated
        assert image_result["status"] in ("AVAILABLE", "NOT_CONFIGURED",
                                          "UNAVAILABLE", "FAILED")

    def test_recent_turns(self, kv):
        input_ = MultimodalInput(kv=kv)
        for i in range(3):
            input_.ingest({"text": f"turn {i}"})
        recent = input_.recent_turns(2)
        assert [t["payload"]["text"] for t in recent] == ["turn 1", "turn 2"]

    def test_unavailable_modality_honest(self, kv):
        input_ = MultimodalInput(kv=kv)
        routed = input_.route({})
        assert routed["results"][0]["status"] == "UNAVAILABLE"


# ----------------------------------------------------------------------
# 94 + 108 Robotics & Automation / Actuation & Robot Learning
# ----------------------------------------------------------------------

class TestRobot:

    def test_envelope_refusal(self, kv):
        robot = RobotController(kv=kv, simulated=True)
        robot.arm(confirmed=True)
        plan = robot.plan_move("shoulder", target_deg=500.0)
        assert plan["within_envelope"] is False
        result = robot.execute_plan(plan, confirmed=True, trusted=True)
        assert result["status"] == "REFUSED"
        assert "envelope" in result["message"].lower()

    def test_gated_execution(self, kv):
        robot = RobotController(kv=kv, simulated=True)
        # not armed -> refused
        plan = robot.plan_move("gripper", target_deg=60.0)
        refused = robot.execute_plan(plan, confirmed=True)
        assert refused["status"] == "REFUSED"
        # armed but not confirmed -> refused
        robot.arm(confirmed=True)
        refused = robot.execute_plan(plan, confirmed=False)
        assert refused["status"] == "REFUSED"

    def test_simulated_execution_changes_state(self, kv):
        robot = RobotController(kv=kv, simulated=True)
        robot.arm(confirmed=True)
        plan = robot.plan_move("elbow", target_deg=12.0)
        assert plan["safe"] is True
        result = robot.execute_plan(plan, confirmed=True, trusted=True)
        assert result["status"] == "EXECUTED"
        assert result["simulated"] is True
        assert result["current"] == 12.0

    def test_teach_and_replay(self, kv):
        robot = RobotController(kv=kv, simulated=True)
        robot.arm(confirmed=True)
        robot.teach("scoop", [
            {"axis": "shoulder", "target": 20.0},
            {"axis": "elbow", "target": 10.0},
        ])
        assert "scoop" in robot.learned_skills()
        replay = robot.replay("scoop", confirmed=True)
        assert replay["status"] == "REPLAYED"
        assert robot.learned_skills()["scoop"]["steps"] == 2

    def test_replay_precondition(self, kv):
        robot = RobotController(kv=kv, simulated=True)
        robot.teach("nomove", [{"axis": "shoulder", "target": 5.0}])
        # not armed -> precondition refusal
        replay = robot.replay("nomove", confirmed=True)
        assert replay["status"] == "REFUSED"

    def test_real_backend_missing_honest(self, kv):
        robot = RobotController(kv=kv, simulated=False, hardware_backend=None)
        robot.arm(confirmed=True)
        plan = robot.plan_move("gripper", target_deg=55.0)
        result = robot.execute_plan(plan, confirmed=True, trusted=True)
        assert result["status"] == "NOT_CONFIGURED"
        assert result["simulated"] is False

    def test_collision_proxy(self, kv):
        robot = RobotController(kv=kv, simulated=True)
        proxy = robot.collision_proxy({"shoulder": 170.0, "elbow": 130.0})
        assert proxy["heuristic"] is True
        assert isinstance(proxy["conflicts"], list)


# ----------------------------------------------------------------------
# 95 Engineering Design & Coding Assistant
# ----------------------------------------------------------------------

class TestEngineering:

    def test_spec_assembly(self, kv):
        eng = EngineeringProjects(kv=kv)
        spec = eng.create_spec("Vision", ["parse input", "route turn"],
                               ["input API", "output API"])
        assert spec["name"] == "Vision"
        assert len(spec["requirements"]) == 2
        assert len(spec["interfaces"]) == 2
        assert eng.get_spec("Vision")["status"] == "draft"

    def test_sprint_board(self, kv):
        eng = EngineeringProjects(kv=kv)
        eng.add_task("Vision", "Implement parser", "malini", 4)
        eng.add_task("Vision", "Wire routing", "malini", 2)
        tasks = eng.sprint_board()
        assert len(tasks) == 2
        assert tasks[0]["est_hours"] == 4.0
        eng.move_task(tasks[1]["id"], "In Progress")
        assert eng.sprint_board()[1]["column"] == "In Progress"

    def test_review_checklists(self, kv):
        eng = EngineeringProjects(kv=kv)
        assert "Logic is correct" in eng.review_checklist("code_review")[0]
        assert eng.review_checklist("design_review")
        with pytest.raises(KeyError):
            eng.review_checklist("nope")

    def test_measurement_stats(self, kv):
        eng = EngineeringProjects(kv=kv)
        eng.record_measurement("Latency Test", "latency_ms", 10, "ms")
        third = eng.record_measurement("Latency Test", "latency_ms", 30, "ms")
        assert third["average"] == 20.0
        assert third["min"] == 10.0
        assert third["max"] == 30.0
        assert third["count"] == 2

    def test_export(self, kv, tmp_path):
        eng = EngineeringProjects(kv=kv)
        eng.create_spec("Docs", ["clear docs"], ["markdown"])
        eng.add_task("Docs", "Write guide", "malini", 1)
        path = eng.export("Docs", directory=str(tmp_path / "eng"))
        assert os.path.exists(path)
        text = open(path, encoding="utf-8").read()
        assert "Engineering Design — Docs" in text
        assert "Write guide" in text