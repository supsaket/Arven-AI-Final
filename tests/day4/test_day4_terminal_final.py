"""Day 4 — terminal acceptance: the ALL-111 surface works end to end.

Covered here: CLI command surface, the live all-111 verifier, the acceptance
generator, one full terminal mission chain, and app text entry.
"""

import pytest

import cli
import main as main_module
from core.event_response import EventResponder
from core.kv import KeyValueStore
from core.missions import MissionsEngine
from core.planner import AdaptivePlanner
from core.terminal_engine import TerminalEngine

_REQUIRED_FLAGS = ("--features", "--feature", "--capabilities", "--resources",
                   "--dependencies", "--orchestrate", "--steps")


def make_engine(tmp_path, registry):
    return TerminalEngine(
        registry=registry,
        kv=KeyValueStore(str(tmp_path / "terminal.json")),
        planner=AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json"))),
        responder=EventResponder(kv=KeyValueStore(str(tmp_path / "events.json"))),
        missions=MissionsEngine(path=str(tmp_path / "missions.json")))


def test_cli_exposes_all111_command_surface():
    with open("cli.py", encoding="utf-8") as handle:
        src = handle.read()
    for flag in _REQUIRED_FLAGS:
        assert flag in src, flag


def test_verify_all_111_reconciles_catalog():
    import verify_all_111
    assert verify_all_111.main() == 0


def test_acceptance_generator_writes_111_rows(tmp_path, monkeypatch):
    import generate_day3_111_acceptance as gen
    out = tmp_path / "DAY3_111_ACCEPTANCE.md"
    monkeypatch.setattr(gen, "OUT", str(out))
    assert gen.main() == 0
    text = out.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    assert len(rows) == 112  # 1 header + 111 feature rows (separator has no space)
    assert "_Totals: 111 rows;" in text


def test_terminal_mission_uses_all111_tool(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    result = te.mission("day4 acceptance", [
        {"title": "software", "tool": "capability_software", "args": {}},
    ])
    assert result["status"] == "COMPLETE"
    assert result["mission_status"] == "completed"
    assert result["summary"]["progress_pct"] == 100.0
    assert all(s["status"] == "done" for s in result["steps"])


def test_terminal_health_reports_registry_total(tmp_path, registry):
    te = make_engine(tmp_path, registry)
    assert te.status()["registry_tools"] == 436
    assert te.health()["registry_tools"] == 436


def test_cli_feature_flag(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--feature", "110"]) == 0
    out = capsys.readouterr().out
    assert "RESULT ok" in out
    assert "feature fully registered" in out


def test_cli_capabilities_flag(tmp_path, registry, capsys, monkeypatch):
    from core.capability_awareness import CapabilityAwareness
    monkeypatch.setattr(
        cli, "_capability_instance",
        lambda: CapabilityAwareness(kv_path=str(tmp_path / "capcli.json")))
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--capabilities"]) == 0
    out = capsys.readouterr().out
    assert "CAPABILITIES" in out
    assert "PROVIDERS" in out


def test_cli_features_flag(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert cli.main(["--features"]) == 0
    out = capsys.readouterr().out
    assert "FEATURES 123" in out
    assert "111 | Advanced Autonomous Command & Mission Orchestration" in out


def test_app_text_entry_runs_via_main(tmp_path, registry, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine",
                        lambda: make_engine(tmp_path, registry))
    assert main_module.run_text(["--feature", "23"]) == 0
    assert "feature fully registered" in capsys.readouterr().out