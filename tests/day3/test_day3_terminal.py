"""Day 3 terminal engine + CLI + text entry (T1/T3/T8)."""

import json

import pytest

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.planner import AdaptivePlanner
from core.event_response import EventResponder
from core.missions import MissionsEngine
from core.terminal_engine import TerminalEngine
from core.cyber_toolkit import CyberToolkit
import tools.day2_tools as d2
import cli
import main as main_module


def make_engine(tmp_path, registry):
    planner = AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json")))
    responder = EventResponder(kv=KeyValueStore(str(tmp_path / "events.json")))
    missions = MissionsEngine(path=str(tmp_path / "missions.json"))
    return TerminalEngine(
        registry=registry,
        kv=KeyValueStore(str(tmp_path / "terminal.json")),
        planner=planner, responder=responder, missions=missions)


def take_cyber_to_tmp(tmp_path, monkeypatch):
    """Route the day2 cyber engine to a temp store with NO scopes."""
    toolkit = CyberToolkit(kv=KeyValueStore(str(tmp_path / "cyber.json")))
    monkeypatch.setattr(d2, "_engine_cyber", lambda: toolkit)
    return toolkit


def test_intent_resolves_known_requests(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    assert te.resolve_intent("please list the plans")["tool"] == "plan_list"
    assert te.resolve_intent("diagnostics run")["tool"] == "diagnostics_run"
    assert te.resolve_intent("backup snapshot")["tool"] == "backup_snapshot"


def test_intent_no_match_is_honest(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    out = te.resolve_intent("unimaginable gibberish xyzq")
    assert out["tool"] is None
    assert out["reason"] == "no ARVEN capability matched your request"
    assert te.resolve_intent("")["reason"] == "empty request"


def test_act_full_chain(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.act("please list the plans")
    assert result["status"] == "ok"
    assert result["success"] is True
    chain = result["chain"]
    assert chain["intent"]["tool"] == "plan_list"
    assert chain["authorization"]["allowed"] is True
    assert chain["confirmation"]["risk"] == "low"   # plan_list declared risk
    assert chain["execution"]["status"] == "ok"
    assert chain["memory"]["stored"] is False
    assert chain["audit"]["action"] == "plan_list"
    assert len(te.audit()) >= 1


def test_act_infer_simple_topic_arg(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.act("security explain port_scanning")
    assert result["status"] == "ok"
    assert result["success"] is True
    assert result["chain"]["intent"]["tool"] == "cyber_explain"


def test_act_missing_required_argument(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.act("backup snapshot")
    assert result["status"] == "invalid_argument"
    assert "label" in result["message"]


def test_act_unknown_intent(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.act("no such capability forever")
    assert result["status"] == "NO_MATCH"
    assert result["success"] is False


def test_act_confirmation_gate_then_answer(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.act("cyber scan target https://localhost/")
    assert result["status"] == "confirm_required"
    rid = result["request_id"]
    assert CONFIRMATION.is_pending(rid) is True
    answer = te.answer(rid, "yes")
    assert answer["ok"] is True


def test_act_approved_gated_tool_is_honest_about_scope(tmp_path, registry,
                                                        monkeypatch):
    take_cyber_to_tmp(tmp_path, monkeypatch)
    te = make_engine(tmp_path, registry)
    result = te.act("cyber scan target https://localhost/", approve=True)
    # gate consumed; execution is honest about scope (no scopes configured)
    assert result["status"] == "AUTHORIZATION_REQUIRED"
    chain = result["chain"]
    assert chain["confirmation"]["approved"] is True


def test_mission_flow_completes(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.mission("day3 ops check", [
        {"title": "health", "tool": "diagnostics_run", "args": {}},
        {"title": "session context", "tool": "context_summary", "args": {}},
    ])
    assert result["status"] == "COMPLETE"
    assert result["mission_status"] == "completed"
    assert result["success"] is True
    assert result["summary"]["progress_pct"] == 100.0
    assert all(s["status"] == "done" for s in result["steps"])


def test_mission_failed_step_is_honest(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.mission("broken mission", [
        {"title": "hop", "tool": "no_such_tool_xyz", "args": {}},
    ])
    assert result["status"] != "COMPLETE"
    assert result["success"] is False
    assert result["steps"][0]["status"] == "failed"


def test_status_and_health(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    info = te.status()
    assert info["registry_tools"] == 436
    health = te.health()
    assert health["registry_tools"] == 436
    assert health["worst_status"] in {
        "AVAILABLE", "UNAVAILABLE", "OFFLINE", "REQUIRES_AUTH",
        "REQUIRES_PERMISSION", "NOT_CONFIGURED", "FAILED"}


def test_audit_ordering(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    te.act("list the plans")
    te.act("diagnostics run")
    entries = te.audit(limit=50)
    assert len(entries) >= 2
    assert entries[0]["action"] == "diagnostics_run"


def test_cli_parse_params_failures():
    with pytest.raises(SystemExit):
        cli._parse_params(["nokey"])
    cli._parse_params(["target=https://x.test", "flag=true", "n=3"])
    with pytest.raises(SystemExit, match="duplicate"):
        cli._parse_params(["a=1", "a=2"])


def test_cli_parse_steps():
    steps = cli._parse_steps(["diagnostics_run", "web_search|{\"q\": \"x\"}"])
    assert steps[0] == {"title": "diagnostics_run", "tool": "diagnostics_run",
                        "args": {}}
    assert steps[1]["args"] == {"q": "x"}
    with pytest.raises(SystemExit):
        cli._parse_steps([])


def test_cli_ask_runs_full_chain(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--ask", "please list the plans"]) == 0
    captured = capsys.readouterr().out
    assert "RESULT" in captured
    assert "action: plan_list" in captured
    assert "CHAIN" in captured


def test_cli_mission(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--mission", "ops", "--step", "diagnostics_run",
                     "--step", "context_summary"]) == 0
    assert "mission_status: completed" in capsys.readouterr().out


def test_cli_health(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--health"]) == 0
    assert "registry_tools" in capsys.readouterr().out


def test_app_text_entry_runs_via_main(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert main_module.run_text(["--ask", "list the plans"]) == 0
    assert "action: plan_list" in capsys.readouterr().out


def test_cli_parameters_and_approve_flag(tmp_path, registry, capsys,
                                         monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--ask", "security explain tls",
                     "--param", "topic=tls"]) == 0
    out = capsys.readouterr().out
    assert "RESULT ok" in out