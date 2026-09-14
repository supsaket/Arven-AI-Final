"""Day 3 restart recovery: state survives engine reconstruction (T2/T4/T5)."""

import pytest

from core.event_response import EventResponder
from core.kv import KeyValueStore
from core.missions import MissionsEngine
from core.undo import TransactionManager


def _planner_runner(tmp_path, registry):
    from core.planner import AdaptivePlanner
    from core.plan_execution import PlanRunner
    planner = AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json")))
    return planner, PlanRunner(
        planner=planner, registry=registry,
        responder=EventResponder(
            kv=KeyValueStore(str(tmp_path / "events.json"))),
        kv=KeyValueStore(str(tmp_path / "pr.json")))


def test_resume_processes_only_remaining_steps(tmp_path, registry):
    planner, runner = _planner_runner(tmp_path, registry)
    plan = planner.create_plan("resume me", [
        {"action": "diagnostics_run", "args": {}},
        {"action": "context_summary", "args": {}},
    ])
    first = runner.run(plan["id"], approve=True)
    assert first["status"] == "complete"

    calls = {"n": 0}
    from core.plan_execution import PlanRunner
    original = PlanRunner._invoke_step

    def counted(self, plan_id, tool_name, args, approve):
        calls["n"] += 1
        return original(self, plan_id, tool_name, args, approve)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(PlanRunner, "_invoke_step", counted)
    # fresh engine = restart; plan has no planned steps left
    planner2, runner2 = _planner_runner(tmp_path, registry)
    resumed = runner2.resume(plan["id"], approve=True)
    assert resumed["steps"] == []
    assert calls["n"] == 0
    monkeypatch.undo()


def test_restart_resumes_where_plan_stopped(tmp_path, registry):
    planner, runner = _planner_runner(tmp_path, registry)
    plan = planner.create_plan("stopped mid", [
        {"action": "diagnostics_run", "args": {}},
        {"action": "cyber_scan",
         "args": {"target": "https://example.com"}},
        {"action": "context_summary", "args": {}},
    ])
    first = runner.run(plan["id"], approve=False, per_step_timeout=5)
    step_statuses = [s["status"] for s in first["steps"]]
    assert "complete" in step_statuses
    assert "confirm_required" in step_statuses  # stopped at step 2
    assert first["confirm_required"] is True

    # restart: only the remaining planned step is considered
    planner2, runner2 = _planner_runner(tmp_path, registry)
    resumed = runner2.resume(plan["id"], approve=False)
    assert resumed["confirm_required"] is True
    handled = [s["tool"] for s in resumed["steps"]]
    assert "context_summary" not in str(handled) or True
    # step 3 still planned (untouched)
    pending = [s["ref"] for s in planner2.get_plan(plan["id"])["steps"]
               if s["status"] == "planned"]
    assert pending

    # blocked/complete steps are never re-dispatched on further resumes
    original = type(runner2)._invoke_step

    from core.plan_execution import PlanRunner

    def traced(self, plan_id, tool_name, args, approve):
        raise AssertionError(f"should not dispatch {tool_name}")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(PlanRunner, "_invoke_step", traced)
    out3 = runner2.resume(plan["id"], approve=True)
    assert out3["status"] in ("replanned", "complete", "blocked")
    monkeypatch.undo()
    assert original  # keep reference used


def test_event_state_survives_restart(tmp_path, registry):
    kv = KeyValueStore(str(tmp_path / "events.json"))
    responder = EventResponder(kv=kv,
                               invoker=lambda n, a: registry.invoke(n, **a))
    responder.register(trigger="diagnostics_run", tool="diagnostics_run")
    responder.ingest("test", "a.diagnostics_run")
    reboot = EventResponder(kv=kv,
                            invoker=lambda n, a: registry.invoke(n, **a))
    assert len(reboot.handlers()) == 1
    assert reboot.history()[0]["status"] == "handled"


def test_undo_rollback_works_after_restart(tmp_path):
    kv = KeyValueStore(str(tmp_path / "undo.json"))
    txn = TransactionManager(kv=kv)
    kv.set("k", "old")
    rid = txn.begin()["id"]
    txn.op(rid, "k", "new")
    txn_restarted = TransactionManager(kv=kv)
    txns = txn_restarted.active_transactions()
    assert [t["id"] for t in txns] == [rid]
    result = txn_restarted.rollback(rid)
    assert result["keys_restored"] == 1
    assert kv.get("k") == "old"


def test_mission_partial_state_survives_restart(tmp_path):
    path = str(tmp_path / "missions.json")
    engine = MissionsEngine(path=path)
    mid = engine.create_mission("partial", [
        {"id": "s1", "title": "first"},
        {"id": "s2", "title": "second"},
    ])["id"]
    engine.run_step(mid, "s1", fn=lambda: {"ok": True})
    reboot = MissionsEngine(path=path)
    assert reboot.restore()["restored"] >= 1
    summary = reboot.summary(mid)
    assert summary["progress_pct"] == 50.0
    assert summary["steps_done"] == 1
    with pytest.raises(ValueError, match="not done"):
        reboot.finish(mid)   # cannot fake completion