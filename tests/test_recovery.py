"""Recovery contract (row 25) — classification and at-most-once guard."""

from core.recovery import (
    ExecutionGuard,
    RecoveryAction,
    classify,
    run_tool_with_recovery,
)


class TestRecoveryAction:

    def test_statuses(self):
        assert classify("ok").status == "ok"
        assert classify({"status": "ok"}).status == "ok"
        assert classify({"status": "unavailable"}).status == "blocked"
        assert classify({"status": "denied"}).status == "blocked"
        assert classify(RuntimeError("nope")).status == "failed"

    def test_classify_unknown_never_raises(self):
        assert isinstance(classify({"anything": 1}), RecoveryAction)
        assert isinstance(classify(None), RecoveryAction)


class TestExecutionGuard:

    def test_at_most_once(self):
        guard = ExecutionGuard()
        assert guard.acquire("dup-key") is True
        assert guard.acquire("dup-key", timeout=0.05) is False
        assert guard.release("dup-key") is True
        # after release the key is fresh again
        assert guard.acquire("dup-key") is True
        guard.release("dup-key")

    def test_acquire_with_none_timeout_blocks(self):
        from concurrent.futures import ThreadPoolExecutor
        guard = ExecutionGuard()
        guard.acquire("blocked")

        def attempt():
            return guard.acquire("blocked", timeout=None)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            import time
            time.sleep(0.1)
            assert future.running() is True
            guard.release("blocked")
            assert future.result(timeout=2) is True


class TestRunWithRecovery:

    def test_success_path(self, tmp_path):
        def work(**kwargs):
            return {"success": True, "value": kwargs.get("x")}
        result = run_tool_with_recovery(work, kwargs={"x": 5},
                                        action="probe", attempts=2)
        assert result["success"] is True

    def test_failure_is_packaged(self, tmp_path):
        def work(**kwargs):
            raise RuntimeError("boom")

        result = run_tool_with_recovery(work, kwargs={}, action="probe", attempts=1)
        assert result["success"] is False
        assert "error" in str(result.get("status", "")).lower() or \
            result.get("status") == "error"