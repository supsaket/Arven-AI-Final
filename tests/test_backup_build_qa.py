"""Tests: Backups (61), Build/Pipeline (47), QA (62), Diagnostics (63), Profiler (64)."""

import ast
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from core.backup import BackupManager, classify_path
from core.build_agent import PipelineRunner
from core.diagnostics import Diagnostics
from core.performance import Profiler
from core.qa_engine import QARunner


# ----------------------------------------------------------------------
# Feature 61 — Backups
# ----------------------------------------------------------------------
class TestBackupManager:

    def _workspace(self, tmp_path):
        ws = tmp_path / "ws"
        data = ws / "data"
        data.mkdir(parents=True)
        (data / "kv.json").write_text('{"k": "v"}', encoding="utf-8")
        (data / "note.txt").write_text("hello world", encoding="utf-8")
        out = ws / "Output"
        out.mkdir(parents=True)
        (out / "artefact.txt").write_text("artefact", encoding="utf-8")
        return ws

    def test_snapshot_copies_files_and_manifest(self, tmp_path):
        ws = self._workspace(tmp_path)
        mgr = BackupManager(ws, ws / "Output")
        summary = mgr.snapshot("initial")
        assert summary["count"] == 3
        snap_dir = ws / "Backups" / summary["id"]
        assert (snap_dir / "manifest.json").exists()
        manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["files"]) == 3
        # real copies preserved
        assert (snap_dir / "data" / "kv.json").exists()
        assert (snap_dir / "Output" / "artefact.txt").exists()

    def test_verify_recomputes_checksums(self, tmp_path):
        ws = self._workspace(tmp_path)
        mgr = BackupManager(ws, ws / "Output")
        summary = mgr.snapshot("v1")
        result = mgr.verify(summary["id"])
        assert result["verified"] is True
        assert result["status"] == "AVAILABLE"
        # tamper -> detect mismatch
        snap_dir = ws / "Backups" / summary["id"]
        (snap_dir / "data" / "note.txt").write_text("tampered", encoding="utf-8")
        tampered = mgr.verify(summary["id"])
        assert tampered["verified"] is False
        assert tampered["status"] == "FAILED"

    def test_list_snapshots(self, tmp_path):
        ws = self._workspace(tmp_path)
        mgr = BackupManager(ws, ws / "Output")
        mgr.snapshot("a")
        listed = mgr.list_snapshots()
        assert len(listed) == 1
        assert listed[0]["id"].endswith("a")

    def test_rotate_archives_oldest(self, tmp_path):
        ws = self._workspace(tmp_path)
        mgr = BackupManager(ws, ws / "Output")
        one = mgr.snapshot("one")
        two = mgr.snapshot("two")
        three = mgr.snapshot("three")
        result = mgr.rotate(keep=1)
        assert one["id"] in result["archived"]
        assert two["id"] in result["archived"]
        # archived (moved), not deleted
        archive = ws / "Backups" / "_archive"
        assert (archive / one["id"] / "manifest.json").exists()
        assert (archive / two["id"] / "manifest.json").exists()
        # the newest is still kept in place
        assert three["id"] in result["kept"]
        assert (ws / "Backups" / three["id"] / "manifest.json").exists()

    def test_restore_refuses_without_confirmation(self, tmp_path):
        ws = self._workspace(tmp_path)
        mgr = BackupManager(ws, ws / "Output")
        summary = mgr.snapshot("v")
        target = tmp_path / "restore_target"
        result = mgr.restore(summary["id"], target)
        assert result["restored"] is False
        assert "confirmation" in result["message"].lower()

    def test_restore_gated_into_target_dir(self, tmp_path):
        from core.confirmation import CONFIRMATION
        ws = self._workspace(tmp_path)
        mgr = BackupManager(ws, ws / "Output")
        summary = mgr.snapshot("v")
        # open + approve a pending confirmation, pass its request_id
        request_id = CONFIRMATION.require("restore test snapshot")
        CONFIRMATION.approve(request_id)
        target = tmp_path / "restore_target"
        result = mgr.restore(summary["id"], target, confirmed=True,
                             request_id=request_id)
        assert result["restored"] is True
        assert (target / "data" / "kv.json").exists()
        assert (target / "Output" / "artefact.txt").exists()

    def test_classify_path(self):
        assert classify_path("data/kv.json")["bucket"] == "data"
        assert classify_path("Output/report.md")["bucket"] == "output"
        assert classify_path("config/settings.json")["bucket"] == "config"


# ----------------------------------------------------------------------
# Feature 47 — Build / Pipeline
# ----------------------------------------------------------------------
class TestPipelineRunner:

    def test_run_success_writes_manifest(self, tmp_path):
        out = tmp_path / "Output"
        runner = PipelineRunner(output_root=out)
        report = runner.run("proj", [
            {"id": "compile", "action": lambda: "ok", "artifacts": ["bin/a.dll"]},
            {"id": "test", "action": lambda: "pass", "artifacts": ["bin/report.json"]},
        ])
        assert report["complete"] is True
        assert report["failed_stage"] is None
        assert report["stages"][0]["status"] == "passed"
        assert report["stages"][1]["status"] == "passed"
        assert "bin/a.dll" in report["artifacts"]
        assert (out / "Build").exists()
        manifest_files = list((out / "Build").glob("*.json"))
        assert manifest_files
        manifest = json.loads(manifest_files[0].read_text(encoding="utf-8"))
        assert manifest["name"] == "proj"
        assert manifest["complete"] is True

    def test_stage_timeout(self, tmp_path):
        runner = PipelineRunner(output_root=tmp_path / "Output")
        def slow():
            time.sleep(1)
        report = runner.run("slowproj", [
            {"id": "hang", "action": slow, "timeout": 0.1},
        ])
        assert report["complete"] is False
        assert report["stages"][0]["status"] == "timeout"
        assert report["partial"] is True

    def test_stage_failure_returns_error_and_partial(self, tmp_path):
        runner = PipelineRunner(output_root=tmp_path / "Output")
        def boom():
            raise RuntimeError("compile broke")
        report = runner.run("bad", [
            {"id": "step1", "action": lambda: "ok"},
            {"id": "step2", "action": boom},
            {"id": "step3", "action": lambda: "never"},
        ])
        assert report["complete"] is False
        assert report["failed_stage"] == "step2"
        assert report["stages"][-1]["status"] == "failed"
        assert "compile broke" in report["error"]
        # an artefact manifest is written with exit summary
        items = list((tmp_path / "Output" / "Build").glob("*.json"))
        manifest = json.loads(items[0].read_text(encoding="utf-8"))
        assert "failed at stage 'step2'" in manifest["exit_summary"]

    def test_pipeline_from_script_validation(self, tmp_path):
        runner = PipelineRunner(output_root=tmp_path / "Output")
        ok, _ = runner.pipeline_from_script({
            "name": "x",
            "stages": [{"id": "a", "action": lambda: 1}],
        })
        assert ok is True
        bad, errors = runner.pipeline_from_script({"name": "x", "stages": [{"id": "a"}]})
        assert bad is False
        assert any("action" in e for e in errors)

    def test_git_check_honest(self):
        runner = PipelineRunner()
        result = runner.git_check()
        assert result["status"] in ("AVAILABLE", "NOT_CONFIGURED", "UNAVAILABLE")
        assert "available" in result

    def test_fetch_remote_no_repo_not_configured(self, tmp_path):
        runner = PipelineRunner(output_root=tmp_path)
        result = runner.fetch_remote("https://example.com/repo.git", workdir=tmp_path)
        assert result["status"] == "NOT_CONFIGURED"


# ----------------------------------------------------------------------
# Feature 62 — QA Engine
# ----------------------------------------------------------------------
class TestQARunner:

    def _good_file(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(
            '"""A fine module."""\n'
            'import os\n\n\n'
            'def greet(name):\n'
            '    """Greet someone."""\n'
            '    return "hi " + name\n',
            encoding="utf-8")
        return path

    def test_syntax_check_real(self, tmp_path):
        runner = QARunner(tmp_path)
        good = self._good_file(tmp_path)
        assert runner.syntax_check(good)["ok"] is True
        bad = tmp_path / "bad.py"
        bad.write_text("def broken(:\n", encoding="utf-8")
        assert runner.syntax_check(bad)["ok"] is False

    def test_line_length(self, tmp_path):
        runner = QARunner(tmp_path)
        path = tmp_path / "long.py"
        path.write_text("# " + "x" * 200 + "\n", encoding="utf-8")
        result = runner.line_length(path, max=100)
        assert result["ok"] is False
        assert len(result["violations"]) == 1

    def test_imports_resolve(self, tmp_path):
        runner = QARunner(tmp_path)
        good = self._good_file(tmp_path)
        assert runner.imports_resolve(good)["ok"] is True
        bad = tmp_path / "nope.py"
        bad.write_text("import definitely_not_a_module_xyz\n", encoding="utf-8")
        missing = runner.imports_resolve(bad)
        assert missing["ok"] is False
        assert "definitely_not_a_module_xyz" in missing["missing"]

    def test_trailing_whitespace_and_todos(self, tmp_path):
        runner = QARunner(tmp_path)
        path = tmp_path / "ws.py"
        path.write_text("x = 1   \ny = 2\n# TODO fix\n", encoding="utf-8")
        assert runner.trailing_whitespace(path)["ok"] is False
        assert runner.count_todos(tmp_path)["count"] >= 1

    def test_run_pytest_honest(self, tmp_path):
        runner = QARunner(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(exist_ok=True)
        pass_file = tests_dir / "test_pass_tmp.py"
        pass_file.write_text(
            "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        result = runner.run_pytest(pass_file)
        assert result["status"] == "AVAILABLE"
        assert result["passed"] == 1
        assert result["failed"] == 0

    def test_run_pytest_fail_case(self, tmp_path):
        runner = QARunner(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(exist_ok=True)
        fail_file = tests_dir / "test_fail_tmp.py"
        fail_file.write_text(
            "def test_bad():\n    assert False\n", encoding="utf-8")
        result = runner.run_pytest(fail_file)
        assert result["status"] == "FAILED"
        assert result["failed"] == 1
        assert result["returncode"] != 0

    def test_run_pytest_crash_case(self, tmp_path):
        runner = QARunner(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(exist_ok=True)
        crash_file = tests_dir / "test_crash_tmp.py"
        crash_file.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        result = runner.run_pytest(crash_file)
        assert result["returncode"] != 0

    def test_report_writes_json(self, tmp_path):
        runner = QARunner(tmp_path)
        good = self._good_file(tmp_path)
        report = runner.report(good)
        assert report["overall"] in ("PASS", "FAIL")
        assert (tmp_path / "Output" / "QA").exists()
        assert report["report_path"].endswith(".json")


# ----------------------------------------------------------------------
# Feature 63 — Diagnostics
# ----------------------------------------------------------------------
class TestDiagnostics:

    def test_run_returns_structured_snapshot(self, tmp_path):
        diag = Diagnostics(tmp_path)
        snap = diag.run()
        assert "disk" in snap
        assert "memory" in snap
        assert "cpu" in snap
        assert "python" in snap
        assert "network" in snap
        assert "core_health" in snap
        assert "providers" in snap
        assert "system_check" in snap
        for key, value in snap["core_health"].items():
            assert value["status"] in ("AVAILABLE", "FAILED")
        assert snap["python"]

    def test_report_writes_markdown(self, tmp_path):
        diag = Diagnostics(tmp_path)
        outcome = diag.report("snapshot")
        assert outcome["path"].endswith(".md")
        assert "ARVEN Diagnostics" in outcome["markdown"]
        assert (tmp_path / "Output" / "Diagnostics").exists()


# ----------------------------------------------------------------------
# Feature 64 — Profiler
# ----------------------------------------------------------------------
class TestProfiler:

    def test_timed_measures_and_stores(self, tmp_path):
        prof = Profiler(kv_path=tmp_path / "perf.json")
        def spin():
            time.sleep(0.01)
            return 42
        value, duration = prof.timed("work", spin)
        assert value == 42
        assert duration > 0
        stats = prof.report("work")
        assert stats["count"] == 1
        assert stats["min"] == pytest.approx(stats["max"], abs=0.1)

    def test_benchmark_and_hotspots_math(self, tmp_path):
        prof = Profiler(kv_path=tmp_path / "perf.json")
        prof.benchmark("fast", lambda: None, iterations=50)
        prof.benchmark("warm", lambda: None, iterations=5)
        hotspots = prof.hotspots()
        assert hotspots, "expected at least one hotspot"
        for h in hotspots:
            assert h["count"] > 0
            assert h["avg"] >= 0
        # avg == total/count
        for h in hotspots:
            assert round(h["avg"], 6) == round(h["total"] / h["count"], 6)
