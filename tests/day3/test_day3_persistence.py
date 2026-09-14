"""Day 3 persistence across restart (T4/T5/T6, machine-checkable W->S->R->L->V)."""

import pytest

from core.cyber_toolkit import CyberToolkit, LOCAL_MACHINE
from core.event_response import EventResponder
from core.kv import KeyValueStore
from core.missions import MissionsEngine
from core.undo import TransactionManager


def test_event_handlers_and_history_survive_restart(tmp_path, registry):
    kv = KeyValueStore(str(tmp_path / "events.json"))
    responder = EventResponder(kv=kv, invoker=lambda n, a: registry.invoke(n, **a))
    responder.register(trigger="diagnostics_run", tool="diagnostics_run")
    responder.ingest("test", "a.diagnostics_run")

    rebooted = EventResponder(kv=kv, invoker=lambda n, a: registry.invoke(n, **a))
    assert len(rebooted.handlers()) == 1
    assert rebooted.handlers()[0]["tool"] == "diagnostics_run"
    assert len(rebooted.history()) == 1
    assert rebooted.stats()["total_fires"] == 1


def test_event_lock_for_permission_manager_stateless_reused(tmp_path):
    kv = KeyValueStore(str(tmp_path / "second.json"))
    a = EventResponder(kv=kv)
    a.register(trigger="t1")
    b = EventResponder(kv=kv)
    assert [h["trigger"] for h in b.handlers()] == ["t1"]


def test_undo_committed_transaction_survives_restart(tmp_path):
    kv = KeyValueStore(str(tmp_path / "undo.json"))
    txn = TransactionManager(kv=kv)
    rid = txn.begin("cache write")["id"]
    txn.op(rid, "cache:key", {"v": 1})
    txn.commit(rid)

    rebuilt = TransactionManager(kv=kv)
    status = rebuilt.status(rid)
    assert status["status"] == "committed"
    assert status["ops"] == 1
    assert kv.get("cache:key") == {"v": 1}


def test_event_ledger_and_scopes_survive_restart(tmp_path, monkeypatch):
    kv = KeyValueStore(str(tmp_path / "cyber.json"))
    toolkit = CyberToolkit(kv=kv)
    toolkit.add_scope(LOCAL_MACHINE)
    toolkit.add_scope("offline-host.invalid")
    toolkit._dns_probe = lambda host: {"resolved": False, "error": "offline"}
    result = toolkit.scan("offline-host.invalid", tool="dns", confirmed=True)
    assert result["status"] == "EXECUTED"

    rebooted = CyberToolkit(kv=kv)
    assert set(rebooted.list_scopes()) == {LOCAL_MACHINE, "offline-host.invalid"}
    ledger = rebooted.audit()
    assert ledger and ledger[0]["kind"] == "scan"
    assert ledger[0]["target"] == "offline-host.invalid"
    # only primitive summaries persist — raw tool outputs are never stored
    summary = ledger[0]["summary"]
    assert all(isinstance(v, (bool, str, int, float, list, type(None)))
               for v in summary.values())


def test_cyber_scope_and_evidence_keys_kv(monkeypatch, tmp_path):
    kv = KeyValueStore(str(tmp_path / "cyber2.json"))
    toolkit = CyberToolkit(kv=kv)
    toolkit.add_scope("demo.test")
    assert kv.get("_scopes") == ["demo.test"]


def test_missions_survive_restart(tmp_path):
    path = str(tmp_path / "missions.json")
    engine = MissionsEngine(path=path)
    mid = engine.create_mission("persist me", [
        {"id": "s1", "title": "step one"},
        {"id": "s2", "title": "step two"},
    ])["id"]
    assert engine.run_step(mid, "s1", fn=lambda: {"n": 1})["status"] == "done"
    engine.run_step(mid, "s2", fn=lambda: {"n": 2})
    engine.finish(mid)

    rebooted = MissionsEngine(path=path)
    assert rebooted.restore()["restored"] >= 1
    assert rebooted.get_mission(mid)["status"] == "completed"
    summary = rebooted.summary(mid)
    assert summary["progress_pct"] == 100.0
    assert summary["steps_done"] == 2


def test_planner_and_execution_history_survive_restart(tmp_path, registry):
    from core.planner import AdaptivePlanner
    from core.plan_execution import PlanRunner

    planner_kv = KeyValueStore(str(tmp_path / "planner.json"))
    pr_kv = KeyValueStore(str(tmp_path / "pr.json"))
    planner = AdaptivePlanner(kv=planner_kv)
    plan = planner.create_plan("persistent plan", [
        {"action": "diagnostics_run", "args": {}}])
    runner = PlanRunner(planner=planner, registry=registry,
                        responder=EventResponder(
                            kv=KeyValueStore(str(tmp_path / "ev.json"))),
                        kv=pr_kv)
    runner.run(plan["id"], approve=True)

    planner2 = AdaptivePlanner(kv=planner_kv)
    runner2 = PlanRunner(planner=planner2, registry=registry,
                         responder=EventResponder(
                             kv=KeyValueStore(str(tmp_path / "ev.json"))),
                         kv=pr_kv)
    assert len(runner2.history()) == 1
    plan2 = planner2.get_plan(plan["id"])
    assert plan2["status"] == "complete"
    assert all(s["status"] == "complete" for s in plan2["steps"])