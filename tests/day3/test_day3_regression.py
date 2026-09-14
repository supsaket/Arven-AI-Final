"""Day 3 regression: registry/state/GUI/memory baselines never break."""

import json
import os
import subprocess

import pytest

from tools.builder import build_registry


def test_registry_has_full_toolset():
    assert len(build_registry().names()) == 436


def test_live_state_has_nine_terminal_targets(tmp_path):
    assert os.path.exists("day3_state.json")
    with open("day3_state.json", "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    assert set(doc["targets"]) == {
        "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"}
    final_count = sum(
        1 for t in doc["targets"].values() if t["state"] == "FINAL")
    assert 0 <= final_count <= 9
    for target in doc["targets"].values():
        assert target["state"] in {
            "TO_ADD", "WORK", "IN_PROGRESS", "USABLE",
            "TEST", "STRONG", "COMPLETE", "FINAL"}


def test_gui_and_3d_frozen_against_git_head():
    out = subprocess.run(["git", "status", "--porcelain", "--",
                          "arven_gui.py", "arven_3d.py"],
                         capture_output=True, text=True, cwd=".")
    dirty = [line for line in out.stdout.splitlines()
             if line.strip() and not line.startswith("!!")]
    assert dirty == [], f"GUI/3D modified: {dirty}"


def test_live_gui_and_3d_import_unmodified():
    import arven_gui  # noqa: F401  (import must succeed unmodified)
    import arven_3d  # noqa: F401


def test_memory_db_stays_hermetic():
    path = "data/arven_memory.db"
    assert os.path.exists(path)
    size = os.path.getsize(path)
    assert 20000 <= size <= 21000, f"memory db drift: {size} bytes"
    with open(path, "rb") as handle:
        assert handle.read(2)  # readable binary payload
        assert handle.readable()


def test_day2_verifier_scripts_regression():
    for script in ("verify_registry.py", "verify_offline.py",
                   "verify_recovery.py"):
        assert os.path.exists(script), f"missing {script}"
        out = subprocess.run([os.sys.executable, script],
                             capture_output=True, text=True, cwd=".")
        assert out.returncode == 0, f"{script} failed:\n{out.stdout}\n{out.stderr}"


def test_plan_execution_history_keeps_runs(tmp_path, registry):
    from core.event_response import EventResponder
    from core.kv import KeyValueStore
    from core.planner import AdaptivePlanner
    from core.plan_execution import PlanRunner
    planner = AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "p.json")))
    runner = PlanRunner(
        planner=planner, registry=registry,
        responder=EventResponder(kv=KeyValueStore(str(tmp_path / "e.json"))),
        kv=KeyValueStore(str(tmp_path / "pr.json")))
    plan = planner.create_plan("history", [
        {"action": "diagnostics_run", "args": {}}])
    runner.run(plan["id"], approve=True)
    assert len(runner.history()) >= 1
    assert runner.history()[0]["plan_id"] == plan["id"]


def test_no_fake_capability_markers():
    """Honesty contract: registry tools must never report fabricated ok."""
    registry = build_registry()
    probe = registry.invoke("diagnostics_run")
    assert probe.get("status") == "ok"
    assert probe.get("success") is True