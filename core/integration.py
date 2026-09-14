"""Core integration / orchestration (row 37).

Wires the runtime subsystems together:
* scheduler  -> fires due actions as structured events
* background -> capacity-aware executor for deferrable work
* proactive  -> periodic suggestion loop that respects quiet hours
* registry   -> single tool authority used by every subsystem
* lifecycle  -> start/stop that is idempotent and always leaves no orphans

Exposes ``ARVEN`` — the runtime orchestrator.
"""

import threading

from core.lifecycle import LifecycleManager
from core.background import BackgroundExecutor
from core.health import run_system_check
from core.scheduler import SchedulerEngine, scheduler_store
from core.proactive import ProactiveEngine, proactive_engine
from core.selftest import selftest as selftest_runner


class Integration:

    def __init__(self, registry=None, lifecycle=None, background=None,
                 scheduler_engine=None, proactive=None):
        from tools.builder import get_registry
        self.registry = registry or get_registry()
        self.lifecycle = lifecycle or LifecycleManager()
        self.background = background or BackgroundExecutor(max_workers=2)
        self.scheduler_engine = scheduler_engine or SchedulerEngine(
            store=scheduler_store)
        self.proactive = proactive or proactive_engine
        self._lock = threading.Lock()
        self._observer = None

    # ------------------------------------------------------------------
    def start(self):
        with self._lock:
            if self.lifecycle.state() in ("running", "starting"):
                return {"started": False, "state": self.lifecycle.state()}
            self.lifecycle.start()
            self.background = BackgroundExecutor(max_workers=2)
            return {"started": True, "state": self.lifecycle.state()}

    def stop(self):
        with self._lock:
            prior = self.lifecycle.state()
            self.background.shutdown()
            self.lifecycle.stop()
            return {"stopped": prior in ("running", "starting"),
                    "state": self.lifecycle.state()}

    # ------------------------------------------------------------------
    def _fire(self, task):
        action = task.get("action") or task.get("content") or ""
        if not action:
            return None
        if self._observer is not None:
            return self._observer(action)
        try:
            return self.registry.invoke("run_shell",
                                        confirmed=False,
                                        command="" + str(action))
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def attach_observer(self, observer):
        """Replace the default fire path with an external handler."""
        self._observer = observer

    def run_due_tasks(self):
        return self.scheduler_engine.fire()

    # ------------------------------------------------------------------
    def tick(self):
        """One background cycle: due tasks then a proactive suggestion."""
        due = self.run_due_tasks()
        suggestion = self.proactive.suggest() if self.proactive.enabled else None
        return {"due_tasks": due, "proactive_suggestions": suggestion}

    def health(self, offline=True):
        return run_system_check(offline=offline)

    def selftest(self):
        return selftest_runner.run()

    @property
    def status(self):
        return {"integration": "wired",
                "lifecycle": self.lifecycle.state(),
                "tools": len(self.registry.names()),
                "background_tasks": len(self.background.list()),
                "scheduler": self.scheduler_engine.status() if hasattr(
                    self.scheduler_engine, "status") else "ok"}


ARVEN = Integration()

__all__ = ["Integration", "ARVEN"]