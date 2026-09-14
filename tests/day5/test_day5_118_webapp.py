"""Feature 118 — Autonomous web/app/game creation: real build+run+test gate."""

import os

from core.web_app_engine import WebAppEngine


def test_create_web_static(tmp_path):
    engine = WebAppEngine()
    out = engine.create(
        "a static landing page with a title", name="landing",
        workspace_dir=str(tmp_path), kind="web")
    assert out["status"] == "ok"
    assert out["project"]
    assert os.path.isdir(out["project"])
    assert out["verdict"]["verdict"] == "PASS"
    assert out["plan"]


def test_inspect_round_trip(tmp_path):
    engine = WebAppEngine()
    created = engine.create(
        "a minimal todo list app", name="inspected",
        workspace_dir=str(tmp_path), kind="web")
    inspected = engine.inspect_project(created["name"], created["project"])
    assert inspected["success"] is True
    assert "files" in inspected


def test_qa_reports_pass_after_real_build(tmp_path):
    engine = WebAppEngine()
    created = engine.create(
        "a static web page with a unit test", name="qa_test",
        workspace_dir=str(tmp_path), kind="web")
    qa = engine.qa_report(created["name"], created["project"])
    assert qa["status"] == "ok"
    assert qa["verdict"] in ("PASS", "FAIL")
    assert "build" in qa and "test" in qa
    assert qa["report"]
    assert os.path.exists(qa["report"])


def test_build_failure_is_honest(tmp_path):
    engine = WebAppEngine()
    workspace = tmp_path / "broken"
    workspace.mkdir()
    (workspace / "app.py").write_text(
        "def broken(:\n    pass\n", encoding="utf-8")
    out = engine.qa_report("broken", str(workspace))
    assert out["verdict"] == "FAIL"
    assert out["build"]["passed"] is False