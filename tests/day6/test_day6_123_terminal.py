"""Day 6 — terminal acceptance: feature 123 CLI surface + live verifier.

Includes: verify_all_123.py master verifier, DAY6 acceptance generator, and
real CLI invocations (--feature 123, --test-feature 123, --mechatronics-*).
"""

import pytest

import cli
from core.event_response import EventResponder
from core.kv import KeyValueStore
from core.missions import MissionsEngine
from core.planner import AdaptivePlanner
from core.terminal_engine import TerminalEngine

_MECH_FLAGS = ("--mechatronics-spec", "--mechatronics-simulate",
               "--mechatronics-validate", "--mechatronics-discover",
               "--mechatronics-connect", "--mechatronics-status",
               "--mechatronics-read", "--mechatronics-write",
               "--mechatronics-hil", "--mechatronics-diagnostics",
               "--mechatronics-bom")

_EXPECTED_NEW_TOOLS = {
    "mechatronics_create_system", "mechatronics_validate",
    "mechatronics_simulate", "mechatronics_discover", "mechatronics_connect",
    "mechatronics_disconnect", "mechatronics_read", "mechatronics_write",
    "mechatronics_hil", "mechatronics_diagnostics", "mechatronics_bom",
    "mechatronics_interfaces",
}


@pytest.fixture()
def engine(tmp_path, registry):
    return TerminalEngine(
        registry=registry,
        kv=KeyValueStore(str(tmp_path / "terminal6.json")),
        planner=AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner6.json"))),
        responder=EventResponder(kv=KeyValueStore(str(tmp_path / "events6.json"))),
        missions=MissionsEngine(path=str(tmp_path / "missions6.json")))


def test_cli_exposes_featuresurface():
    src = open("cli.py", encoding="utf-8").read()
    assert "--feature" in src and "--features" in src
    for flag in _MECH_FLAGS:
        assert flag in src, flag


def test_verify_all_123_reconciles_catalog():
    import verify_all_123
    assert verify_all_123.main() == 0


def test_verify_all_122_still_reconciles():
    import verify_all_122
    assert verify_all_122.main() == 0


def test_cli_features_flag_shows_123(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--features"]) == 0
    out = capsys.readouterr().out
    assert "FEATURES 123" in out
    assert "123 |" in out
    assert "mechatronics" in out


def test_cli_feature_123_flag(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--feature", "123"]) == 0
    out = capsys.readouterr().out
    assert "feature fully registered" in out


def test_cli_test_feature_123_executes(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--test-feature", "123"]) == 0
    out = capsys.readouterr().out
    assert "FEATURE 123 EXEC: PASS" in out


def test_cli_mechatronics_discover(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--mechatronics-discover"]) == 0
    out = capsys.readouterr().out
    assert "MECHATRONICS DISCOVER" in out
    assert "SIMULATED" in out  # honest hint that no real HW present here


def test_cli_mechatronics_hil(engine, capsys, monkeypatch):
    from core import mechatronics
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    # force fresh persist-isolated engine so HIL runs locally
    tmp = capsys  # noqa
    mech = mechatronics.MechatronicsEngine(
        kv_path=str(engine.kv.path), out_dir="Output/mechatronics")
    monkeypatch.setattr(mechatronics, "_engine", mech)
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    assert cli.main(["--mechatronics-hil", "10"]) == 0
    out = capsys.readouterr().out
    assert "RESULT" in out


def test_cli_mechatronics_connect_and_status(engine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_build_engine", lambda: engine)
    from core import mechatronics
    monkeypatch.setattr(mechatronics, "_engine",
                        mechatronics.MechatronicsEngine(
                            kv_path=str(engine.kv.path)))
    assert cli.main(["--mechatronics-connect", "SIMULATED"]) == 0
    assert cli.main(["--mechatronics-status"]) == 0


def test_registry_total_cardinality(names):
    assert len(names) == 436
    assert len(names) == len(set(names))


def test_catalog_123_rows_and_no_duplicates(names):
    from core.features import list_features
    rows = list_features()
    ids = [r["id"] for r in rows]
    assert ids == list(range(1, 124))
    assert len(set(ids)) == 123
    for r in rows:
        for tool in r["tools"]:
            assert tool in names, f"feature {r['id']} missing {tool}"


def test_feature123_tools_all_working(registry):
    for name in _EXPECTED_NEW_TOOLS:
        tool = registry.get(name)
        assert tool is not None, name
        assert tool.available is True
        assert callable(tool.function)


def test_acceptance_generator_writes_123_rows(tmp_path, monkeypatch):
    import generate_day6_123_acceptance as gen
    out = tmp_path / "DAY6_FEATURE_123_ACCEPTANCE.md"
    monkeypatch.setattr(gen, "OUT", str(out))
    assert gen.main() == 0
    text = out.read_text(encoding="utf-8")
    assert "FEATURE 123" in text or "feature 123" in text.lower()
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    assert len(rows) == 124  # 1 header + 123 feature rows
    assert rows[1].startswith("| 1 |")
    assert rows[-1].startswith("| 123 |")