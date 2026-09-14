"""Day 2 — features 50/101/51/99/52/53/55/56 focused tests.

Covers: mission lifecycle (archive-not-delete, dependency gating, timeout,
blocked/escalation, restore-after-restart), continuity snapshot/resume/orphan,
context ranking + decay, world-state projection math + consistency, experience
similarity + lessons, decision weight math + log, workflow topo validation +
cycle refusal + risky-step gate + resume, and skill define/invoke/trace +
validation. All kv paths are per-test tempfiles.
"""

import json
import time

import pytest

from core.confirmation import CONFIRMATION
from core.safety import RISK_HIGH, RISK_DESTRUCTIVE
from memory.database import MemoryDatabase

from core.missions import MissionsEngine, MissionEngine
from core.continuity import ContinuityManager
from core.context_engine import ContextEngine
from core.world_state import WorldState
from core.experience import ExperienceVault
from core.decisions import DecisionEngine
from core.workflows import WorkflowEngine
from core.skill_builder import SkillStore


# ---------------------------------------------------------------------------
# Feature 50 — Missions
# ---------------------------------------------------------------------------
class TestMissions:

    def test_create_and_lifecycle(self, tmp_path):
        engine = MissionsEngine(tmp_path / "missions.json")
        mission = engine.create_mission(
            "Deploy build",
            [
                {"id": "build", "title": "Compile"},
                {"id": "test", "title": "Run tests", "depends": ["build"]},
            ],
            priority=2, budget_seconds=60,
        )
        assert mission["status"] == "active"
        assert [s["status"] for s in mission["steps"]] == ["open", "open"]
        assert engine.run_step(mission["id"], "test")["status"] == "waiting"
        assert engine.run_step(mission["id"], "build")["status"] == "done"
        assert engine.run_step(mission["id"], "test")["status"] == "done"
        engine.finish(mission["id"])
        summary = engine.summary(mission["id"])
        assert summary["progress_pct"] == 100.0
        assert engine.get_mission(mission["id"])["status"] == "completed"

    def test_dependency_failure_blocks(self, tmp_path):
        engine = MissionsEngine(tmp_path / "m.json")

        def boom():
            raise RuntimeError("boom")

        mission = engine.create_mission(
            "m",
            [{"id": "a", "title": "a"},
             {"id": "b", "title": "b", "depends": ["a"]}],
        )
        failed = engine.run_step(mission["id"], "a", fn=boom)
        assert failed["status"] == "failed"
        blocked = engine.run_step(mission["id"], "b")
        assert blocked["status"] == "blocked"
        assert engine.get_mission(mission["id"])["steps"][1]["status"] == "blocked"

    def test_timeout_bounds_a_step(self, tmp_path):
        engine = MissionsEngine(tmp_path / "m.json")
        mission = engine.create_mission(
            "slow", [{"id": "s", "title": "sleep"}]
        )
        result = engine.run_step(
            mission["id"], "s", fn=lambda: time.sleep(2), timeout=0.05
        )
        assert result["status"] == "failed"
        assert "budget" in result["reason"]

    def test_pause_resume_cancel_archive_non_destructive(self, tmp_path):
        engine = MissionsEngine(tmp_path / "m.json")
        mission = engine.create_mission(
            "job", [{"id": "s", "title": "s"}]
        )
        engine.pause(mission["id"])
        assert engine.get_mission(mission["id"])["status"] == "paused"
        engine.resume(mission["id"])
        assert engine.get_mission(mission["id"])["status"] == "active"

        engine.cancel(mission["id"], reason="no longer useful")
        mission_after = engine.get_mission(mission["id"])
        assert mission_after["status"] == "failed"   # cancel records, no delete
        assert any(e["event"] == "cancelled" for e in engine.audit(mission["id"]))
        assert mission["id"] in engine.list_missions()

        other = engine.create_mission("keep", [{"id": "x", "title": "x"}])
        engine.archive(other["id"])
        archived = engine.get_mission(other["id"])
        assert archived["status"] == "archived"
        assert other["id"] in engine.list_missions(status="archived")
        assert other["id"] in engine.list_missions()

    def test_escalate_returns_structured_note(self, tmp_path):
        engine = MissionsEngine(tmp_path / "m.json")
        mission = engine.create_mission(
            "risky", [{"id": "s", "title": "s"}]
        )
        mission, note = engine.escalate(mission["id"], "operator intervention")
        assert mission["status"] == "blocked"
        assert note["reason"] == "operator intervention"
        assert note["status"] == "blocked"
        assert note["external_action"] == "none"

    def test_validation_refusals(self, tmp_path):
        engine = MissionsEngine(tmp_path / "m.json")
        with pytest.raises(ValueError):
            engine.create_mission("", [{"id": "a", "title": "a"}])
        with pytest.raises(ValueError):
            engine.create_mission("x", [])
        with pytest.raises(ValueError):
            engine.create_mission(
                "x",
                [{"id": "dup", "title": "a"}, {"id": "dup", "title": "b"}],
            )
        with pytest.raises(ValueError):
            engine.create_mission(
                "x", [{"id": "a", "title": "a", "depends": ["ghost"]}]
            )

    def test_restore_after_restart(self, tmp_path):
        path = tmp_path / "missions.json"
        engine1 = MissionsEngine(path)
        mission = engine1.create_mission(
            "persist",
            [{"id": "a", "title": "a"},
             {"id": "b", "title": "b", "depends": ["a"]}],
        )
        assert engine1.run_step(mission["id"], "a")["status"] == "done"
        engine2 = MissionsEngine(path)  # fresh instance, same kv path
        info = engine2.restore()
        assert info["restored"] >= 1
        restored = engine2.get_mission(mission["id"])
        assert restored["title"] == "persist"
        assert restored["status"] == "active"
        assert [s["status"] for s in restored["steps"]] == ["done", "open"]
        assert engine2.summary(mission["id"])["next_actionable_step"]["id"] == "b"

    def test_summary_next_actionable(self, tmp_path):
        engine = MissionsEngine(tmp_path / "m.json")
        mission = engine.create_mission(
            "chain",
            [{"id": "a", "title": "a"},
             {"id": "b", "title": "b", "depends": ["a"]},
             {"id": "c", "title": "c", "depends": ["b"]}],
        )
        assert engine.summary(mission["id"])["next_actionable_step"]["id"] == "a"
        engine.run_step(mission["id"], "a")
        assert engine.summary(mission["id"])["next_actionable_step"]["id"] == "b"
        assert engine.summary(mission["id"])["progress_pct"] == pytest.approx(33.3, abs=0.1)

    def test_mission_engine_alias(self, tmp_path):
        engine = MissionEngine(tmp_path / "m.json")
        assert isinstance(engine, MissionsEngine)


# ---------------------------------------------------------------------------
# Feature 101 — Continuity
# ---------------------------------------------------------------------------
class TestContinuity:

    def test_snapshot_resume_restores_state(self, tmp_path):
        path = tmp_path / "cont.json"
        engine1 = MissionsEngine(path)
        mission = engine1.create_mission(
            "memorable",
            [{"id": "a", "title": "a"},
             {"id": "b", "title": "b", "depends": ["a"]}],
        )
        engine1.run_step(mission["id"], "a")
        snap = ContinuityManager(path, engine=engine1).snapshot(mission["id"])
        assert snap["pending"] == ["b"]

        engine2 = MissionsEngine(path)  # simulated restart
        manager2 = ContinuityManager(path, engine=engine2)
        plan = manager2.resume()
        assert len(plan) == 1
        assert plan[0]["restored"] is True
        restored = engine2.get_mission(mission["id"])
        assert [s["status"] for s in restored["steps"]] == ["done", "open"]
        assert restored["status"] == "active"

    def test_orphan_report_and_quarantine(self, tmp_path):
        orphan_path = tmp_path / "snap.json"
        store = ContinuityManager(orphan_path, engine=None).store
        broken_snapshot = {
            "ghost_mission": {
                "ts": time.time(),
                "mission_id": "ghost_mission",
                "pending": ["a"],
                "mission_state": {
                    "id": "ghost_mission",
                    "title": "ghost",
                    "status": "active",
                    "steps": [{"id": "a", "title": "a",
                               "status": "open", "depends": ["z"]}],
                },
            }
        }
        store.set("continuity.snapshots", broken_snapshot)
        engine = MissionsEngine(tmp_path / "empty_missions.json")
        manager = ContinuityManager(orphan_path, engine=engine)
        report = manager.orphan_report()
        kinds = {r["kind"] for r in report}
        assert "orphan_snapshot" in kinds
        assert "orphan_step" in kinds
        assert all(r["severity"] == "soft" for r in report)

        engine2 = MissionsEngine(tmp_path / "quarantine.json")
        mission = engine2.create_mission("misbehaving", [{"id": "s", "title": "s"}])
        engine2.escalate(mission["id"], "out of bounds")
        manager2 = ContinuityManager(tmp_path / "q.json", engine=engine2)
        result = manager2.quarantine()
        assert mission["id"] in result["quarantined"]
        assert result["deleted"] == 0
        assert engine2.get_mission(mission["id"])["status"] == "paused"
        assert any(
            e["event"] == "quarantined"
            for e in engine2.audit(mission["id"])
        )


# ---------------------------------------------------------------------------
# Feature 51 — Context / Working Memory
# ---------------------------------------------------------------------------
class TestContextEngine:

    def test_context_for_ranks_by_overlap_and_recency(self, tmp_path):
        engine = ContextEngine(tmp_path / "ctx.json")
        now = time.time()
        engine.push_event("deploy the rocket to mars orbit", tags=["space"], ts=now - 100)
        engine.push_event("the cat sat on the mat", ts=now - 50)
        engine.push_event("mars rover landed safely", tags=["space"], ts=now - 10)
        results = engine.context_for("mars rover", limit=10)
        assert results[0]["text"] == "mars rover landed safely"
        assert all("cat sat" not in r["text"] for r in results)
        assert results[0]["source"] == "working"
        assert results[0]["score"] > results[1]["score"]

    def test_longterm_recall_with_importance_threshold(self, tmp_path):
        memory = MemoryDatabase(tmp_path / "memory.db")
        memory.add("mars mission surface data", category="mission", importance=8)
        memory.add("mars trivia for fun", category="misc", importance=2)
        engine = ContextEngine(tmp_path / "ctx.json", memory_db=memory)
        engine.push_event("unrelated lunch plans", ts=time.time() - 100)
        results = engine.context_for("mars mission", limit=10, importance_threshold=5)
        texts = [r["text"] for r in results]
        assert any("surface data" in t for t in texts)
        assert any(r["source"] == "longterm" for r in results)
        assert not any("trivia" in t for t in texts)

    def test_claims_decay_soft_and_never_delete(self, tmp_path):
        engine = ContextEngine(tmp_path / "ctx.json")
        now = time.time()
        engine.record_claim("the rocket is on the pad", strength=1.0, ts=now - 3 * 86400)
        engine.record_claim("fresh fact today", strength=1.0, ts=now)
        assert len(engine.get_claims()) == 2
        decayed = engine.decay_days(2)
        assert decayed == 1
        claims = engine.get_claims()
        assert len(claims) == 2  # nothing deleted
        old, fresh = claims
        assert old["decayed"] is True
        assert old["strength"] == pytest.approx(0.3)
        assert fresh["decayed"] is False

    def test_focus_and_summarize_window(self, tmp_path):
        engine = ContextEngine(tmp_path / "ctx.json")
        assert engine.focus(["space", "launch"]) == ["space", "launch"]
        engine.push_event("ignition sequence start", tags=["launch"])
        engine.push_event("booster separation", tags=["launch"])
        engine.push_event("orbit insertion confirmed", tags=["launch"])
        summary = engine.summarize_window(limit=10)
        assert summary["event_count"] == 3
        assert summary["tags"]["launch"] == 3
        assert "ignition" in summary["top_keywords"]
        assert summary["focus_topics"] == ["space", "launch"]


# ---------------------------------------------------------------------------
# Feature 99 — World State
# ---------------------------------------------------------------------------
class TestWorldState:

    def test_projection_is_real_extrapolation(self, tmp_path):
        state = WorldState(tmp_path / "ws.json")
        state.set_entity("rocket", tags=["asset"])
        state.update_attribute("rocket", "speed", 0.0, ts=0.0)
        state.update_attribute("rocket", "speed", 10.0, ts=100.0)
        projection = state.project("rocket", "speed", dt_hours=1)
        assert projection["projected"] is True
        assert projection["rate"] == pytest.approx(0.1)
        assert projection["value"] == pytest.approx(370.0)
        unprojected = WorldState(tmp_path / "ws.json")
        unprojected.set_entity("solo", tags=[])
        unprojected.update_attribute("solo", "x", 5.0, ts=0.0)
        assert unprojected.project("solo", "x", dt_hours=1)["projected"] is False

    def test_point_in_time_query(self, tmp_path):
        state = WorldState(tmp_path / "ws.json")
        state.set_entity("rocket", created_at=5, tags=["asset"])
        state.update_attribute("rocket", "fuel", 100.0, ts=10.0)
        state.update_attribute("rocket", "fuel", 50.0, ts=20.0)
        assert state.query({"attr:fuel": 100.0}, as_of=15)  # value before 20s
        assert not state.query({"attr:fuel": 50.0}, as_of=15)
        assert state.query({"attr:fuel": 50.0}, as_of=1e12)
        assert state.query({"attr:fuel": 50.0})
        assert not state.query({"attr:fuel": 100.0})
        assert state.query({"tag": "asset"})

    def test_delta_history(self, tmp_path):
        state = WorldState(tmp_path / "ws.json")
        state.set_entity("tank", created_at=0)
        state.update_attribute("tank", "level", 100.0, ts=10.0)
        state.update_attribute("tank", "level", 50.0, ts=20.0)
        state.update_attribute("tank", "level", 70.0, ts=30.0)
        deltas = state.delta_history("tank", "level")
        assert len(deltas) == 3
        assert deltas[0]["delta"] is None
        assert deltas[1]["delta"] == pytest.approx(-50.0)
        assert deltas[2]["delta"] == pytest.approx(20.0)

    def test_consistency_check_stale_and_conflicting_twins(self, tmp_path):
        state = WorldState(tmp_path / "ws.json")
        state.set_entity("sensor_a", tags=["twin"])
        state.set_entity("sensor_b", tags=["twin"])
        state.update_attribute(
            "sensor_a", "reading", 1.0, ts=time.time() - 4_000_000
        )
        state.update_attribute("sensor_b", "reading", 2.0, ts=time.time())
        report = state.consistency_check(stale_threshold_seconds=100_000)
        severities = {(i["severity"], i.get("entity"), i.get("attribute"))
                      for i in report["issues"]}
        assert ("stale", "sensor_a", "reading") in severities
        assert any(
            i["severity"] == "conflict" and i["attribute"] == "reading"
            for i in report["issues"]
        )

    def test_restart_persistence(self, tmp_path):
        path = tmp_path / "ws.json"
        state1 = WorldState(path)
        state1.set_entity("drone", attributes={"battery": 80}, tags=["fleet"])
        state2 = WorldState(path)
        drone = state2.get_entity("drone")
        assert drone["attributes"]["battery"]["value"] == 80
        assert len(drone["attributes"]["battery"]["history"]) == 1


# ---------------------------------------------------------------------------
# Feature 52 — Experience
# ---------------------------------------------------------------------------
class TestExperience:

    def test_similar_scores_and_reward_weighting(self, tmp_path):
        vault = ExperienceVault(tmp_path / "exp.json")
        vault.record("when the rocket fails to ignite", "run preflight checks",
                     outcome="failure", reward=-1.0, tags=["space"])
        vault.record("rocket ignition failure debug", "check fuel valves",
                     outcome="success", reward=3.0, tags=["space", "debug"])
        similar = vault.similar("rocket ignition failed", k=5)
        assert similar[0]["experience"]["action"] == "check fuel valves"
        assert similar[0]["score"] > similar[1]["score"]

    def test_lessons_suggest_action(self, tmp_path):
        vault = ExperienceVault(tmp_path / "exp.json")
        vault.record("rocket ignition failed", "check fuel valves",
                     outcome="success", reward=3.0)
        vault.record("rocket ignition failed", "check fuel valves",
                     outcome="success", reward=2.0)
        vault.record("rocket ignition failed", "ignore and retry",
                     outcome="failure", reward=-2.0)
        lesson = vault.lessons("rocket")
        assert lesson["total"] == 3
        assert lesson["successes"] == 2
        assert lesson["failures"] == 1
        assert lesson["suggested_action"] == "check fuel valves"
        assert lesson["success_rate"] == pytest.approx(2 / 3, abs=0.001)

    def test_context_hints_have_real_scores(self, tmp_path):
        vault = ExperienceVault(tmp_path / "exp.json")
        vault.record("mission launch", "press launch button", outcome="success", reward=5.0)
        vault.record("mission launch", "abort launch", outcome="failure")
        hints = vault.context_hints("mission launch", k=5)
        assert len(hints) == 2
        assert all(h["score"] > 0 for h in hints)
        assert any(h["outcome"] == "failure" for h in hints)
        assert hints[0]["score"] >= hints[1]["score"]

    def test_record_validates_outcome(self, tmp_path):
        vault = ExperienceVault(tmp_path / "exp.json")
        with pytest.raises(ValueError):
            vault.record("x", "y", outcome="maybe")


# ---------------------------------------------------------------------------
# Feature 53 — Decisions
# ---------------------------------------------------------------------------
class TestDecisions:

    def test_weighted_normalized_math(self, tmp_path):
        engine = DecisionEngine(tmp_path / "dec.json")
        engine.add_criteria("speed", 2, "benefit")
        engine.add_criteria("cost", 1, "cost")
        engine.add_option("car", {"speed": 10, "cost": 100})
        engine.add_option("bike", {"speed": 4, "cost": 20})
        result = engine.evaluate()
        assert result["normalized"]["car"] == {"speed": 1.0, "cost": 0.0}
        assert result["normalized"]["bike"] == {"speed": 0.0, "cost": 1.0}
        assert result["scores"]["car"] == pytest.approx(2 / 3)
        assert result["scores"]["bike"] == pytest.approx(1 / 3)
        assert result["recommendation"]["name"] == "car"
        assert result["confidence"] == pytest.approx(0.5)

    def test_criteria_validation(self, tmp_path):
        engine = DecisionEngine(tmp_path / "dec.json")
        with pytest.raises(ValueError):
            engine.add_criteria("bad", 0, "benefit")
        engine.add_criteria("cost", 1, "-")
        with pytest.raises(ValueError):
            engine.add_option("x", {"missing_criterion": 1})

    def test_evaluation_log_persists_across_instances(self, tmp_path):
        path = tmp_path / "dec.json"
        engine1 = DecisionEngine(path)
        engine1.add_criteria("reliability", 1, "benefit")
        engine1.add_option("alpha", {"reliability": 9})
        result = engine1.evaluate()
        engine2 = DecisionEngine(path)
        log = engine2.log()
        assert len(log) == 1
        assert log[0]["recommendation"]["name"] == "alpha"
        assert log[0]["scores"] == result["scores"]

    def test_pros_cons_store_and_read(self, tmp_path):
        engine = DecisionEngine(tmp_path / "dec.json")
        engine.pros_cons("refactor", pros=["cleaner tests"], cons=["takes time"])
        engine.pros_cons("refactor", pros=["cleaner tests"], cons=["takes time"])
        entry = engine.pros_cons("refactor")
        assert entry["pros"] == ["cleaner tests"]
        assert entry["cons"] == ["takes time"]


# ---------------------------------------------------------------------------
# Feature 55 — Workflows
# ---------------------------------------------------------------------------
class TestWorkflows:

    def test_define_rejects_cycles_and_unknown_tools(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")

        def step_a(**kw):
            return {"ok": True}

        def step_b(**kw):
            return {"ok": True}

        with pytest.raises(ValueError):
            engine.define(
                "cycle",
                [{"id": "a", "action": step_a, "depends": ["b"]},
                 {"id": "b", "action": step_b, "depends": ["a"]}],
            )
        with pytest.raises(ValueError):
            engine.define("bad tool", [{"id": "s", "action": "no_such_tool_123"}])
        defined = engine.define("has tool", [{"id": "s", "action": "read_file"}])
        assert defined["status"] == "ready"

    def test_run_executes_in_dependency_order(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")
        calls = []

        def step_a(**kw):
            calls.append("a")
            return {"who": "a"}

        def step_b(**kw):
            calls.append("b")
            return {"x": kw.get("x")}

        workflow = engine.define(
            "ordered",
            [{"id": "a", "title": "first", "action": step_a},
             {"id": "b", "title": "second", "action": step_b,
              "args": {"x": 7}, "depends": ["a"]}],
        )
        result = engine.run(workflow["id"])
        assert result["status"] == "completed"
        assert calls == ["a", "b"]
        step_results = {s["id"]: s for s in result["steps"]}
        assert step_results["b"]["result"] == {"x": 7}

    def test_risky_step_gate_and_resume(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")

        def dummy_delete(**kw):
            return {"deleted": kw.get("target", "none")}

        workflow = engine.define(
            "cleanup",
            [{"id": "wipe", "title": "Delete temp", "action": dummy_delete,
              "args": {"target": "tmpfile"}}],
        )
        first = engine.run(workflow["id"])
        assert first["status"] == "requires_auth"
        assert first["requires_confirmation"] is True
        assert engine.get(workflow["id"])["status"] == "paused"

        request_id = CONFIRMATION.require("delete temp in test", risk=RISK_DESTRUCTIVE)
        resumed = engine.run(
            workflow["id"], confirmed=True, trusted=True, request_id=request_id
        )
        assert resumed["status"] == "completed"
        step = resumed["steps"][0]
        assert step["status"] == "done"
        assert step["result"] == {"deleted": "tmpfile"}

    def test_risky_tool_step_never_auto_runs(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")
        target = tmp_path / "do_not_touch.txt"
        workflow = engine.define(
            "risky-tool",
            [{"id": "del", "title": "delete", "action": "delete_file",
              "args": {"path": str(target)}}],
        )
        result = engine.run(workflow["id"])
        assert result["status"] == "requires_auth"
        assert result["requires_confirmation"] is True
        assert engine.get(workflow["id"])["steps"][0]["status"] == "requires_auth"

    def test_step_timeout_guard(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")

        def slow(**kw):
            time.sleep(5)

        workflow = engine.define("slow", [{"id": "s", "action": slow}])
        result = engine.run(workflow["id"], timeout=0.05)
        assert result["status"] == "failed"
        assert "0.05" in result["message"]

    def test_progress_persists_across_instances(self, tmp_path):
        path = tmp_path / "wf.json"
        payload = tmp_path / "note.txt"
        payload.write_text("hello world", encoding="utf-8")
        verified = []

        def verify_step(**kw):
            verified.append(1)
            return {"verified": True}

        engine1 = WorkflowEngine(path)
        workflow = engine1.define(
            "persistent",
            [{"id": "read", "title": "read file", "action": "read_file",
              "args": {"path": str(payload)}},
             {"id": "verify", "title": "verify", "action": verify_step,
              "depends": ["read"]}],
        )
        first = engine1.run(workflow["id"])
        assert first["status"] == "completed"
        assert len(verified) == 1

        engine2 = WorkflowEngine(path)  # fresh instance, same kv
        persisted = engine2.get(workflow["id"])
        assert {s["status"] for s in persisted["steps"]} == {"done"}
        resumed = engine2.run(workflow["id"])
        assert resumed["status"] == "completed"
        assert len(verified) == 1  # completed steps are not re-executed

    def test_failed_step_is_honest_and_persisted(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")

        def failing(**kw):
            raise RuntimeError("kaboom")

        def later(**kw):
            return {"ok": True}

        workflow = engine.define(
            "fails",
            [{"id": "f", "action": failing},
             {"id": "l", "action": later, "depends": ["f"]}],
        )
        result = engine.run(workflow["id"])
        assert result["status"] == "failed"
        assert "kaboom" in result["message"]
        persisted = engine.get(workflow["id"])
        steps = {s["id"]: s for s in persisted["steps"]}
        assert steps["f"]["status"] == "failed"
        assert steps["l"]["status"] == "pending"
        refused = engine.run(workflow["id"])
        assert refused["status"] == "failed"
        assert "kaboom" in refused["message"]

    def test_abort_is_audited(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")

        def dummy_delete(**kw):
            return {"deleted": True}

        workflow = engine.define("abortable", [{"id": "s", "action": dummy_delete}])
        assert engine.run(workflow["id"])["status"] == "requires_auth"
        engine.abort(workflow["id"], reason="policy change")
        assert engine.get(workflow["id"])["status"] == "aborted"
        after = engine.run(workflow["id"])
        assert after["aborted"] is True

    def test_templates_store_and_define(self, tmp_path):
        engine = WorkflowEngine(tmp_path / "wf.json")
        engine.save_template("daily", [{"id": "read", "action": "read_file"}])
        assert engine.list_templates() == ["daily"]
        workflow = engine.define("daily job", template="daily")
        assert engine.get(workflow["id"])["steps"][0]["action"] == "read_file"


# ---------------------------------------------------------------------------
# Feature 56 — Skills
# ---------------------------------------------------------------------------
class TestSkills:

    def test_define_invoke_trace(self, tmp_path):
        store = SkillStore(tmp_path / "skills.json")

        def compute_step(**kw):
            return {"sum": int(kw["a"]) + int(kw["b"])}

        store.define(
            "summarize_numbers",
            description="add two ints",
            parameters=[{"name": "a", "type": "int", "required": True},
                        {"name": "b", "type": "int", "required": True}],
            procedure=[{"step": "compute", "detail": "sum", "action": compute_step}],
        )
        trace = store.invoke("summarize_numbers", {"a": 3, "b": 4})
        assert trace["status"] == "completed"
        assert trace["outputs"]["compute"]["sum"] == 7
        assert trace["steps"][0]["status"] == "done"

    def test_missing_and_extra_params_refused(self, tmp_path):
        store = SkillStore(tmp_path / "skills.json")
        store.define(
            "greet",
            parameters=[{"name": "name", "type": "text", "required": True}],
            procedure=[{"step": "say", "detail": "", "action": "read_file"}],
        )
        with pytest.raises(ValueError):
            store.invoke("greet", {})
        with pytest.raises(ValueError):
            store.invoke("greet", {"name": "x", "surprise": 1})

    def test_type_coercion(self, tmp_path):
        store = SkillStore(tmp_path / "skills.json")

        def echo(**kw):
            return {"n": kw["n"]}

        store.define(
            "coerce_n",
            parameters=[{"name": "n", "type": "int", "required": True}],
            procedure=[{"step": "echo", "detail": "", "action": echo}],
        )
        result = store.invoke("coerce_n", {"n": "5"})
        value = result["outputs"]["echo"]["n"]
        assert value == 5
        assert isinstance(value, int)

    def test_risky_action_gated(self, tmp_path):
        store = SkillStore(tmp_path / "skills.json")

        def dummy_delete(**kw):
            return {"gone": True}

        store.define("purge", procedure=[{"step": "purge", "detail": "", "action": dummy_delete}])
        first = store.invoke("purge")
        assert first["status"] == "requires_auth"
        assert first["requires_confirmation"] is True
        assert first["steps"][0]["status"] == "requires_auth"
        request_id = CONFIRMATION.require("purge via skill", risk=RISK_DESTRUCTIVE)
        second = store.invoke("purge", confirmed=True, trusted=True, request_id=request_id)
        assert second["status"] == "completed"
        assert second["outputs"]["purge"] == {"gone": True}

    def test_define_validation_and_share(self, tmp_path):
        store = SkillStore(tmp_path / "skills.json")
        with pytest.raises(ValueError):
            store.define("bad", parameters=[{"name": "p", "type": "hologram"}],
                         procedure=[{"step": "s", "action": "read_file"}])
        with pytest.raises(ValueError):
            store.define("bad", parameters=[
                {"name": "p", "type": "int"}, {"name": "p", "type": "int"}],
                procedure=[{"step": "s", "action": "read_file"}])
        with pytest.raises(ValueError):
            store.define("bad", procedure=[])
        with pytest.raises(ValueError):
            store.define("bad", procedure=[{"step": "s", "action": "no_such_tool_99"}])
        store.define("ok", parameters=[{"name": "p", "type": "int"}],
                     procedure=[{"step": "s", "action": "read_file"}])
        assert store.list() == ["ok"]
        exported = json.loads(store.share("ok"))
        assert exported["name"] == "ok"
        assert exported["procedure"][0]["action"] == "read_file"

    def test_verify_and_restart_honesty(self, tmp_path):
        path = tmp_path / "skills.json"

        def checker(**kw):
            return True

        store1 = SkillStore(path)
        store1.define("gated", parameters=[{"name": "x", "type": "int"}],
                      procedure=[{"step": "s", "action": "read_file"}],
                      verify=checker)
        assert store1.verify("gated", {"x": 1})["verified"] is True

        store2 = SkillStore(path)  # fresh instance — runtime verifier is gone
        check = store2.verify("gated", {"x": 1})
        assert check["source"] == "unavailable"
        assert check["verified"] is False
        assert store1.list() == ["gated"]

    def test_verify_not_defined(self, tmp_path):
        store = SkillStore(tmp_path / "skills.json")
        store.define("plain", procedure=[{"step": "s", "action": "read_file"}])
        check = store.verify("plain")
        assert check["verified"] is None
        assert "no verifier" in check["message"]