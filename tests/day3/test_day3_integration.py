"""Day 3 event response end-to-end + orchestration integration (T4, T9)."""

import pytest

from core.event_response import EventResponder
from core.kv import KeyValueStore


def make_responder(tmp_path, invoker=None):
    return EventResponder(kv=KeyValueStore(str(tmp_path / "events.json")),
                          invoker=invoker)


def registry_invoker(registry):
    return lambda name, args: registry.invoke(name, **args)


def test_real_low_risk_tool_dispatch(tmp_path, registry):
    responder = make_responder(
        tmp_path, invoker=registry_invoker(registry))
    responder.register(trigger="diagnostics_run", tool="diagnostics_run",
                       severity="all", description="run diagnostics")
    response = responder.ingest("test", "terminal.diagnostics_run",
                                severity="low")
    assert response["status"] == "handled"
    assert response["dispatched"] is True
    assert response["outcome"]["success"] is True
    stats = responder.stats()
    assert stats["handlers"] == 1
    assert stats["total_fires"] == 1


def test_dedup_window_suppresses_repeat(tmp_path, registry):
    responder = make_responder(
        tmp_path, invoker=registry_invoker(registry))
    responder.register(trigger="diagnostics_run", tool="diagnostics_run")
    first = responder.ingest("test", "one.diagnostics_run")
    assert first["status"] == "handled"
    second = responder.ingest("test", "one.diagnostics_run")
    assert second["deduplicated"] is True
    assert second["action"] == "dedup"
    assert second["matched"] is False
    assert responder.stats()["total_fires"] == 1


def test_cooldown_suppresses_handler_without_losing_record(tmp_path, registry):
    fires = {"count": 0}

    def tracking_invoker(name, args):
        fires["count"] += 1
        return registry.invoke(name, **args)

    responder = make_responder(tmp_path, invoker=tracking_invoker)
    responder.register(trigger="diagnostics_run", tool="diagnostics_run",
                       cooldown_seconds=3600)
    first = responder.ingest("test", "alpha.diagnostics_run")
    assert first["status"] == "handled"
    second = responder.ingest("test", "beta.diagnostics_run")  # cooldown active
    assert second["status"] == "unhandled"
    assert fires["count"] == 1
    assert responder.stats()["total_fires"] == 1


def test_high_severity_without_handler_escalates(tmp_path):
    responder = make_responder(tmp_path)
    response = responder.ingest("test", "critical.event", severity="high")
    assert response["status"] == "ESCALATED"
    assert "escalated" in response["message"]
    history = responder.history()
    assert history[0]["status"] == "escaped"


def test_bad_severity_rejected(tmp_path):
    responder = make_responder(tmp_path)
    with pytest.raises(ValueError, match="severity"):
        responder.ingest("test", "event", severity="nonsense")


def test_register_invalid_severity_rejected(tmp_path):
    responder = make_responder(tmp_path)
    with pytest.raises(ValueError, match="severity"):
        responder.register(trigger="x", severity="bogus")


def test_register_empty_trigger_rejected(tmp_path):
    responder = make_responder(tmp_path)
    with pytest.raises(ValueError):
        responder.register(trigger="   ")


def test_handler_without_invoker_reports_unavailable(tmp_path):
    responder = make_responder(tmp_path)
    responder.register(trigger="x", tool="some_tool")
    response = responder.ingest("test", "x", severity="low")
    # _fire surfaces UNAVAILABLE because no invoker is configured
    assert response["status"] == "UNAVAILABLE"
    assert "no invoker" in response["message"]


def test_planner_runner_inline_end_to_end(tmp_path, registry):
    from core.planner import AdaptivePlanner
    from core.plan_execution import PlanRunner

    planner = AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json")))
    plan = planner.create_plan("end to end", [
        {"action": "diagnostics_run", "args": {}},
        {"action": "context_summary", "args": {}},
    ])
    runner = PlanRunner(planner=planner, registry=registry,
                        responder=make_responder(tmp_path),
                        kv=KeyValueStore(str(tmp_path / "pr.json")))
    outcome = runner.run(plan["id"], approve=True, per_step_timeout=5)
    assert outcome["status"] == "complete"
    assert outcome["steps"][-1]["status"] == "complete"
    assert planner.get_plan(plan["id"])["status"] == "complete"