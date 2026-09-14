"""Day 3 failure modes: safe, deterministic, honest negative paths."""

import time

import pytest

from core.event_response import EventResponder
from core.kv import KeyValueStore
from core.undo import TransactionManager


# ----------------------------------------------------------------------
# T2 — PlanRunner bounded execution, honest interruption, no infinite loop
# ----------------------------------------------------------------------

def _runner(tmp_path, registry, monkeypatch=None):
    from core.planner import AdaptivePlanner
    from core.plan_execution import PlanRunner
    planner = AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json")))
    return PlanRunner(
        planner=planner, registry=registry,
        responder=EventResponder(kv=KeyValueStore(str(tmp_path / "e.json"))),
        kv=KeyValueStore(str(tmp_path / "pr.json")))


def test_step_timeout_is_honest_failure(tmp_path, registry, monkeypatch):
    from core.plan_execution import PlanRunner
    runner = _runner(tmp_path, registry)
    plan = runner.planner.create_plan("timed plan", [
        {"action": "diagnostics_run", "args": {}},
        {"action": "slow_step", "args": {}},
    ])

    original = PlanRunner._invoke_step
    def slow(self, plan_id, tool_name, args, approve):
        if tool_name == "slow_step":
            time.sleep(0.4)
        return original(self, plan_id, tool_name, args, approve)
    monkeypatch.setattr(PlanRunner, "_invoke_step", slow)

    outcome = runner.run(plan["id"], approve=True, per_step_timeout=0.15)
    step2 = [s for s in outcome["steps"] if s["tool"] == "slow_step"][0]
    assert step2["status"] == "blocked"
    assert "exceeded" in step2["message"]
    assert outcome["escalated"] is True


def test_escalation_terminates_no_infinite_loop(tmp_path, registry):
    runner = _runner(tmp_path, registry)
    plan = runner.planner.create_plan("losing plan", [
        {"action": "no_such_tool_abc", "args": {}}])
    started = time.monotonic()
    outcome = runner.run(plan["id"], approve=True, max_replans=2)
    elapsed = time.monotonic() - started
    assert outcome["escalated"] is True
    assert elapsed < 5
    tools = [s["tool"] for s in outcome["steps"]]
    assert "@manual_review" in tools        # non-dispatchable rescue marker
    assert len(runner.history()) >= 1


def test_replan_with_fallback_completes(tmp_path, registry):
    runner = _runner(tmp_path, registry)
    plan = runner.planner.create_plan("recover", [
        {"action": "no_such_tool_xyz", "args": {},
         "fallbacks": [{"action": "diagnostics_report", "args": {}}]},
    ])
    outcome = runner.run(plan["id"], approve=True, max_replans=2)
    assert outcome["status"] == "complete"
    assert outcome["steps"][-1]["status"] == "complete"


def test_replan_budget_exhausted_escalates(tmp_path, registry):
    runner = _runner(tmp_path, registry)
    plan = runner.planner.create_plan("deep fallback", [
        {"action": "no_such_tool_1", "args": {},
         "fallbacks": [{"action": "no_such_tool_2", "args": {}}]},
    ])
    started = time.monotonic()
    outcome = runner.run(plan["id"], approve=True, max_replans=1)
    assert time.monotonic() - started < 5
    assert outcome["escalated"] is True
    assert "@manual_review" in [s["tool"] for s in outcome["steps"]]


# ----------------------------------------------------------------------
# T4 — event responder negatives
# ----------------------------------------------------------------------

def test_event_bad_severity_rejected(tmp_path):
    responder = EventResponder(kv=KeyValueStore(str(tmp_path / "e.json")))
    with pytest.raises(ValueError, match="severity"):
        responder.ingest("src", "type", severity="insane")


def test_event_registration_bad_args(tmp_path):
    responder = EventResponder(kv=KeyValueStore(str(tmp_path / "e2.json")))
    with pytest.raises(ValueError):
        responder.register(trigger="", tool="x")
    with pytest.raises(ValueError):
        responder.register(trigger="x", severity="wat")


# ----------------------------------------------------------------------
# T5 — undo negatives
# ----------------------------------------------------------------------

def test_undo_op_after_close_rejected(tmp_path):
    kv = KeyValueStore(str(tmp_path / "u.json"))
    txn = TransactionManager(kv=kv)
    rid = txn.begin()["id"]
    txn.rollback(rid)
    with pytest.raises(ValueError, match="rolled_back"):
        txn.op(rid, "k", "v")


def test_undo_unknown_txn_raises(tmp_path):
    txn = TransactionManager(kv=KeyValueStore(str(tmp_path / "u2.json")))
    with pytest.raises(KeyError):
        txn.rollback("ghost-txn")


# ----------------------------------------------------------------------
# T1/T3 — terminal negatives
# ----------------------------------------------------------------------

def test_terminal_answer_unknown_request(tmp_path, registry):
    from core.terminal_engine import TerminalEngine
    te = TerminalEngine(registry=registry,
                        kv=KeyValueStore(str(tmp_path / "te.json")))
    out = te.answer("cfm-does-not-exist", "yes")
    assert out["ok"] is False
    assert "no such pending" in out["message"]