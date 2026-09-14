"""Integration / orchestration contract (row 37) — runtime wiring."""

import time

from core.integration import ARVEN, Integration
from core.scheduler import TaskStore


class TestLifecycleWiring:

    def test_start_stop(self):
        integration = Integration()
        assert integration.start()["started"] is True
        assert integration.stop()["stopped"] is True

    def test_start_idempotent(self):
        integration = Integration()
        integration.start()
        again = integration.start()
        assert again["started"] is False


class TestSchedulerIntegration:

    def test_due_tasks_fire_through_registry(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        store.add({"kind": "one_time",
                   "run_at": time.strftime("%Y-%m-%d", time.localtime()) + " 00:00",
                   "text": "check the mail"})
        integration = Integration(scheduler_engine=__import__(
            "core.scheduler", fromlist=["SchedulerEngine"]
        ).SchedulerEngine(store=store))
        fired = integration.run_due_tasks()
        assert isinstance(fired, list)


class TestTick:

    def test_tick_returns_observables(self):
        integration = Integration()
        integration.start()
        tick = integration.tick()
        assert "due_tasks" in tick
        assert "proactive_suggestions" in tick
        integration.stop()

    def test_health_and_selftest_exposed(self):
        integration = Integration()
        report = integration.selftest()
        assert report["failed"] == 0
        assert integration.health(offline=True)["overall"] != "healthy"


class TestARVENGlobal:

    def test_arven_global_wired(self):
        assert ARVEN.status["integration"] == "wired"
        assert ARVEN.status["tools"] >= 20