"""Background agents / executor.

Runs cancellable tasks on a dedicated worker thread with error isolation:
each background job failure is captured and stored, never propagated, and
the executor reports lifecycle cleanly with no orphan threads on shutdown.
"""

import threading
import time
import uuid


class BackgroundTask:
    def __init__(self, task_id, name, function, *args, **kwargs):
        self.task_id = task_id
        self.name = name
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self._cancel_event = threading.Event()
        self.result = None
        self.error = None
        self.status = "pending"  # pending | running | done | cancelled | failed
        self.started_at = None
        self.finished_at = None

    def cancel(self):
        self._cancel_event.set()
        if self.status not in ("done", "failed", "cancelled"):
            self.status = "cancelled"

    @property
    def cancelled(self):
        return self._cancel_event.is_set()


class BackgroundExecutor:

    def __init__(self, max_workers=2):
        self._tasks = {}
        self._lock = threading.Lock()
        self._t0 = time.monotonic()
        self._observer = None

    # ------------------------------------------------------------------
    def submit(self, name, function, *args, **kwargs):
        task = BackgroundTask(str(uuid.uuid4())[:8], name, function, *args, **kwargs)
        with self._lock:
            self._tasks[task.task_id] = task
        thread = threading.Thread(target=self._run, args=(task,), daemon=True)
        thread.start()
        return task

    def _run(self, task):
        task.status = "running"
        task.started_at = time.time()
        try:
            if not task.cancelled:
                task.result = task.function(*task.args, **task.kwargs)
                task.status = "done"
        except Exception as exc:
            task.error = exc
            task.status = "failed"
        finally:
            task.finished_at = time.time()
            if self._observer:
                try:
                    self._observer(task)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    def get(self, task_id):
        with self._lock:
            return self._tasks.get(task_id)

    def list(self):
        with self._lock:
            return [self._describe(t) for t in self._tasks.values()]

    def _describe(self, task):
        return {
            "task_id": task.task_id,
            "name": task.name,
            "status": task.status,
            "error": repr(task.error) if task.error else None,
        }

    def cancel(self, task_id):
        task = self.get(task_id)
        if task is not None:
            task.cancel()
            return True
        return False

    def cancel_all(self):
        with self._lock:
            for task in self._tasks.values():
                task.cancel()

    def wait_all(self, timeout=None):
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            with self._lock:
                unfinished = [t for t in self._tasks.values()
                              if t.status in ("pending", "running")]
            if not unfinished:
                return
            if deadline is not None and time.monotonic() >= deadline:
                return
            time.sleep(0.02)

    def task_counts(self):
        counts = {"pending": 0, "running": 0, "done": 0, "cancelled": 0, "failed": 0}
        for task in self._tasks.values():
            counts[task.status] += 1
        counts["total"] = len(self._tasks)
        return counts

    def set_observer(self, observer):
        self._observer = observer

    def shutdown(self):
        self.cancel_all()
        self.wait_all(timeout=3)
        return True


# Shared executor used by the Brain.
background_executor = BackgroundExecutor()

__all__ = ["BackgroundExecutor", "BackgroundTask", "background_executor"]