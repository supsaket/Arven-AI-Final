"""Day 3 offline honesty: external probes fail gracefully, local stays up."""

import pytest

from core.cyber_toolkit import CyberToolkit
from core.kv import KeyValueStore

OFFLINE_HOST = "offline-host.invalid"   # RFC 6761: guaranteed unresolvable


@pytest.fixture()
def toolkit(tmp_path):
    toolkit = CyberToolkit(kv=KeyValueStore(str(tmp_path / "cyber.json")))
    toolkit.add_scope(OFFLINE_HOST)
    return toolkit


def test_dns_probe_offline_is_honest(toolkit):
    out = toolkit.scan(OFFLINE_HOST, tool="dns", confirmed=True)
    assert out["status"] == "EXECUTED"
    evidence = out["evidence"]
    assert evidence["resolved"] is False
    assert "error" in evidence          # real failure surfaced, not faked
    assert evidence["error"]  # non-empty error explanation


def test_tls_probe_offline_is_honest(toolkit):
    out = toolkit.scan(OFFLINE_HOST, tool="tls", confirmed=True)
    assert out["status"] == "EXECUTED"
    evidence = out["evidence"]
    assert evidence.get("tls") is False
    assert "error" in evidence


def test_local_capability_works_without_network(registry):
    assert registry.invoke("diagnostics_run")["success"] is True
    assert registry.invoke("date_time")["success"] is True
    assert registry.invoke("plan_list")["success"] is True


def test_run_local_plan_offline(tmp_path, registry):
    from core.planner import AdaptivePlanner
    from core.event_response import EventResponder
    from core.plan_execution import PlanRunner

    planner = AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json")))
    plan = planner.create_plan("local while offline", [
        {"action": "diagnostics_run", "args": {}},
        {"action": "context_summary", "args": {}},
    ])
    runner = PlanRunner(planner=planner, registry=registry,
                        responder=EventResponder(
                            kv=KeyValueStore(str(tmp_path / "e.json"))),
                        kv=KeyValueStore(str(tmp_path / "pr.json")))
    outcome = runner.run(plan["id"], approve=True)
    assert outcome["status"] == "complete"
    assert outcome["steps"][0]["status"] == "complete"


def test_terminal_health_reports_status_honestly(tmp_path, registry):
    from core.terminal_engine import TerminalEngine
    te = TerminalEngine(registry=registry,
                        kv=KeyValueStore(str(tmp_path / "te.json")))
    health = te.health()
    assert health["registry_tools"] == 436
    assert health["worst_status"] in {
        "AVAILABLE", "UNAVAILABLE", "OFFLINE", "REQUIRES_AUTH",
        "REQUIRES_PERMISSION", "NOT_CONFIGURED", "FAILED"}