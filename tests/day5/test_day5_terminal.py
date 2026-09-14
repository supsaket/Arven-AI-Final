"""Day 5 — terminal acceptance: features 112-122 CLI + live verifier."""

import pytest

import cli
from core.event_response import EventResponder
from core.kv import KeyValueStore
from core.missions import MissionsEngine
from core.planner import AdaptivePlanner
from core.terminal_engine import TerminalEngine

_REQUIRED_FLAGS = ("--features", "--feature", "--test-feature", "--providers",
                   "--capabilities", "--dependencies")

_NEW_FEATURES = list(range(112, 123))


@pytest.fixture()
def engine(tmp_path, registry):
    return TerminalEngine(
        registry=registry,
        kv=KeyValueStore(str(tmp_path / "terminal5.json")),
        planner=AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner5.json"))),
        responder=EventResponder(kv=KeyValueStore(str(tmp_path / "events5.json"))),
        missions=MissionsEngine(path=str(tmp_path / "missions5.json")))


def test_cli_exposes_all122_surface():
    with open("cli.py", encoding="utf-8") as handle:
        src = handle.read()
    for flag in _REQUIRED_FLAGS:
        assert flag in src, flag


def test_verify_all_122_reconciles_catalog():
    import verify_all_122
    assert verify_all_122.main() == 0


def test_acceptance_generator_writes_122_rows(tmp_path, monkeypatch):
    import generate_day5_122_acceptance as gen
    out = tmp_path / "DAY_NEW_FEATURES_112_122_ACCEPTANCE.md"
    monkeypatch.setattr(gen, "OUT", str(out))
    assert gen.main() == 0
    text = out.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    assert len(rows) == 123  # 1 header + 122 feature rows
    assert rows[0].startswith("| ID |")
    assert rows[1].startswith("| 1 |")
    assert rows[-1].startswith("| 122 |")


def test_cli_features_flag_shows_122(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--features"]) == 0
    out = capsys.readouterr().out
    assert "FEATURES 123" in out
    for fid in _NEW_FEATURES:
        assert f"{fid} |" in out


@pytest.mark.parametrize("fid", [112, 113, 114, 115, 116, 117, 118,
                                 119, 120, 121, 122])
def test_cli_test_feature_executes(engine, capsys, monkeypatch, tmp_path, fid):
    from core import cad_3d
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    if fid == 112:
        from core.async_tools_engine import AsyncToolEngine
        eng = AsyncToolEngine(kv_path=str(tmp_path / "async_cli.json"),
                              poll=0.02)
        eng.start()
        import tools.async_tools
        monkeypatch.setattr(tools.async_tools, "_engine", lambda: eng)
        try:
            assert cli.main(["--test-feature", "112"]) == 0
        finally:
            eng.stop()
        out = capsys.readouterr().out
        assert "FEATURE 112 EXEC: PASS" in out
        return
    if fid == 116:
        monkeypatch.setattr(cad_3d, "_OUT", str(tmp_path / "cad"))
    assert cli.main(["--test-feature", str(fid)]) == 0
    out = capsys.readouterr().out
    assert f"FEATURE {fid} EXEC: PASS" in out


def test_cli_feature_flag_new(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--feature", "121"]) == 0
    out = capsys.readouterr().out
    assert "feature fully registered" in out


def test_cli_providers_flag(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--providers"]) == 0
    out = capsys.readouterr().out
    assert "registry_tools" in out or "REGISTRY" in out.upper()


def test_terminal_status_reports_registry(engine):
    assert engine.status()["registry_tools"] == 436
    assert engine.health()["registry_tools"] == 436