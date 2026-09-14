"""Feature 115 — Computer use: honest status + bounded workflows."""

from core.computer_use_engine import ComputerUseEngine


def test_status_reports_honest_capabilities(tmp_path):
    engine = ComputerUseEngine(screenshot_dir=str(tmp_path / "shots"))
    out = engine.status()
    assert out["status"] == "ok"
    assert "available" in out["windows_backend"]
    assert "available" in out["screen_capture"]
    assert out["input_primitive"]
    assert "dry_run never executes" in out["safe_default"]


def test_windows_list_is_bounded(tmp_path):
    engine = ComputerUseEngine(screenshot_dir=str(tmp_path / "shots"))
    out = engine.windows(limit=5)
    assert "window_count" in out
    assert isinstance(out["windows"], list)
    assert len(out["windows"]) <= 5


def test_workflow_dry_run_plans_without_executing(tmp_path):
    engine = ComputerUseEngine(screenshot_dir=str(tmp_path / "shots"))
    out = engine.workflow("click the start menu", dry_run=True,
                          max_iterations=3)
    assert out["status"] == "ok"
    assert out["dry_run"] is True
    assert out["iterations"] == 3
    assert "loop" in out
    planned = [action["planned"] for attempt in out["loop"]
               for action in attempt["actions"] if "planned" in action]
    assert planned                # dry-run only ever plans, never executes
    assert all(planned)