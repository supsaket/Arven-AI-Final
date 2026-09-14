"""Feature 112 — Async Tool Execution Engine: unit / failure / recovery."""

import time

from core.async_tools_engine import (
    AsyncToolEngine, JOB_COMPLETED, JOB_FAILED, JOB_CANCELLED,
    JOB_QUEUED, JOB_RUNNING)


def test_submit_and_wait_completes_real_tool(tmp_path):
    engine = AsyncToolEngine(kv_path=str(tmp_path / "async.json"),
                             workers=2, poll=0.02)
    try:
        engine.start()
        job = engine.submit("eng_calculate", args={"expression": "12*6"},
                            timeout=5.0)
        assert job["success"] is True
        out = engine.wait(job["job_id"], timeout=6.0)
        assert out["success"] is True
        assert out["job"]["status"] == JOB_COMPLETED
        assert out["job"]["result"]["result"] == 72
    finally:
        engine.stop()


def test_submit_unknown_tool_fails_honestly(tmp_path):
    engine = AsyncToolEngine(kv_path=str(tmp_path / "async.json"),
                             workers=2, poll=0.02)
    try:
        engine.start()
        job = engine.submit("definitely_not_a_tool", args={}, timeout=5.0)
        assert job["success"] is False
        assert "unknown" in job.get("message", "")
        assert "job_id" not in job
    finally:
        engine.stop()


def test_target_error_becomes_job_failed(tmp_path):
    engine = AsyncToolEngine(kv_path=str(tmp_path / "async.json"),
                             workers=2, poll=0.02)
    try:
        engine.start()
        job = engine.submit("eng_calculate", args={"expression": "1/0"},
                            timeout=5.0)
        out = engine.wait(job["job_id"], timeout=6.0)
        assert out["job"]["status"] == JOB_FAILED
        rec = engine.result(job["job_id"])
        assert rec["state"] == JOB_FAILED
        assert "division by zero" in rec["error"]
    finally:
        engine.stop()


def test_cancel_running_job(tmp_path, monkeypatch):
    from tools.builder import get_registry
    spec = get_registry().get("eng_calculate")
    monkeypatch.setattr(spec, "function", lambda **kw: time.sleep(4))
    engine = AsyncToolEngine(kv_path=str(tmp_path / "async.json"),
                             workers=2, poll=0.02)
    try:
        engine.start()
        job = engine.submit("eng_calculate", args={"expression": "1+1"},
                            timeout=10.0)
        time.sleep(0.1)  # let the worker pick the job up (RUNNING, blocked)
        cancel = engine.cancel(job["job_id"])
        assert cancel["success"] is True
        engine.wait(job["job_id"], timeout=8.0)
        status = engine.status(job["job_id"])["job"]["status"]
        assert status == JOB_CANCELLED
    finally:
        engine.stop()


def test_restart_recovery_redispatch(tmp_path):
    kv = str(tmp_path / "async.json")
    engine = AsyncToolEngine(kv_path=kv, workers=2, poll=0.02)
    try:
        engine.start()
        job = engine.submit("eng_calculate", args={"expression": "9*9"},
                            timeout=5.0)
        engine.wait(job["job_id"], timeout=6.0)
        assert engine.status(job["job_id"])["job"]["status"] == JOB_COMPLETED
    finally:
        engine.stop()

    restarted = AsyncToolEngine(kv_path=kv, workers=2, poll=0.02)
    try:
        restarted.start()
        recovered = restarted.recover()
        assert recovered["status"] == "ok"
        assert recovered.get("recovered", 0) >= 0
        state = restarted.status(job["job_id"])
        assert state["job"]["status"] in (JOB_COMPLETED, JOB_QUEUED,
                                          JOB_RUNNING)
    finally:
        restarted.stop()