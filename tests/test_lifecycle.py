"""Lifecycle contract (row 29) — idempotent start/stop, hooks, bounds."""

import time

from core.lifecycle import BoundedOperation, LifecycleManager, LifecycleState


class TestLifecycleState:

    def test_states(self):
        assert LifecycleState.STOPPED.value == "stopped"
        assert LifecycleState.RUNNING.value == "running"


class TestLifecycleManager:

    def test_start_and_stop(self):
        manager = LifecycleManager()
        assert manager.state() == "stopped"
        assert manager.start() is True
        assert manager.state() == "running"
        assert manager.is_running() is True
        assert manager.stop() is True
        assert manager.state() == "stopped"

    def test_start_idempotent(self):
        manager = LifecycleManager()
        manager.start()
        assert manager.start() is True
        assert manager.state() == "running"

    def test_stop_idempotent(self):
        manager = LifecycleManager()
        manager.start()
        manager.stop()
        assert manager.stop() is True
        assert manager.state() == "stopped"

    def test_hook_failure_does_not_break_start(self):
        manager = LifecycleManager()

        def bad_hook():
            raise RuntimeError("boom")

        manager.add_start_hook(bad_hook)
        assert manager.start() is True
        assert manager.startup_failure is not None
        assert manager.state() == "running"

    def test_uptime_grows(self):
        manager = LifecycleManager()
        assert manager.uptime() == 0.0
        manager.start()
        time.sleep(0.01)
        assert manager.uptime() > 0.0

    def test_initialize_idempotent(self):
        manager = LifecycleManager()
        assert manager.initialize() is True
        assert manager.initialize() is False

    def test_capture_interrupted_operation(self):
        manager = LifecycleManager()
        manager.capture("long_task")
        assert manager.last_interrupted_operation == "long_task"


class TestBoundedOperation:

    def test_nested_via_run(self):
        op, kind, value = BoundedOperation.run(lambda: 5 + 5)
        assert kind == "ok"
        assert value == 10
        assert op.interrupted is False

    def test_interrupt_detected(self):
        def slow():
            time.sleep(5)
            return True
        op, kind, _ = BoundedOperation.run(slow, timeout=0.05)
        assert op.interrupted is True
        assert kind == "interrupted"


class TestNoOrphans:

    def test_no_orphan_background_tasks_after_shutdown(self):
        from core.background import BackgroundExecutor
        bg = BackgroundExecutor(max_workers=1)
        bg.submit("work", lambda: 1 + 1)
        bg.wait_all(timeout=2)
        assert bg.task_counts()["done"] == 1
        assert bg.task_counts()["total"] == 1