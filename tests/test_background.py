"""Background agents contract (row 19) — submit, isolate, cancel, count."""

import time

from core.background import BackgroundExecutor


class TestSubmit:

    def test_task_runs(self):
        bg = BackgroundExecutor(max_workers=1)
        task = bg.submit("add", lambda a, b: a + b, 1, 2)
        bg.wait_all(timeout=3)
        assert task.status == "done"
        assert task.result == 3

    def test_error_isolated(self):
        bg = BackgroundExecutor(max_workers=1)

        def broken():
            raise ValueError("boom")

        task = bg.submit("broken", broken)
        bg.wait_all(timeout=3)
        assert task.status == "failed"
        assert task.error is not None

    def test_counts(self):
        bg = BackgroundExecutor(max_workers=1)
        bg.submit("add", lambda: 1)
        bg.wait_all(timeout=3)
        counts = bg.task_counts()
        assert counts["total"] == 1
        assert counts["done"] == 1


class TestCancel:

    def test_cancel_pending(self):
        bg = BackgroundExecutor(max_workers=1)
        task = bg.submit("slow", lambda: time.sleep(3))
        time.sleep(0.05)
        assert bg.cancel(task.task_id) is True
        assert task.cancelled is True


class TestShutdown:

    def test_shutdown_clean(self):
        bg = BackgroundExecutor(max_workers=1)
        bg.submit("work", lambda: time.sleep(0.01))
        bg.wait_all(timeout=2)
        assert bg.shutdown() is True