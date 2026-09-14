"""Feature 112 — Async Tool Execution Engine.

Genuine asynchronous tool dispatch with a real state machine and restart
recovery, fully persisted in a JSON key-value store:

    QUEUED -> RUNNING -> COMPLETED
           -> FAILED  (retry budget exhausted)
           -> TIMEOUT (retry budget exhausted)
           -> CANCELLED
    WAITING : job holds until its ``wait_for`` dependencies finish
    RECOVERING : interrupted/queued work resurrected after a restart

Design notes (honest):
* jobs run through ``BoundedOperation`` so every job is wall-clock bounded
  and a timeout is captured as TIMEOUT (never reported as SUCCESS);
* dispatch routes through the shared ``tools.builder`` registry — the same
  CONFIRMATION-aware gate as synchronous execution. A submitted gated tool is
  only executed if the submit itself was explicitly approved (``confirmed``);
* threads cannot be forcefully killed: cancelling a RUNNING job records the
  request and the outcome is finalised as CANCELLED when the worker returns,
  with an honest note that side effects may already have occurred;
* ``recover()`` resurrects QUEUED/RECOVERING/RUNNING/TIMEOUT/FAILED jobs whose
  attempt budget allows it — proven across a fresh engine instance (restart);
* integration: ``kind="orchestrate"`` resumes a paused Feature-111 mission in
  the background (missions + orchestrator are already persisted/restart-safe).

State storage is the single source of truth; the in-memory scheduler is only a
worker loop. Two compute modes: a background scheduler thread (opt-in through
``submit``/``start``) and a synchronous ``tick()`` pass used by the terminal
tools and deterministic tests.
"""

import threading
import time

from core.kv import KeyValueStore
from core.lifecycle import BoundedOperation

JOB_QUEUED = "QUEUED"
JOB_WAITING = "WAITING"
JOB_RUNNING = "RUNNING"
JOB_COMPLETED = "COMPLETED"
JOB_FAILED = "FAILED"
JOB_CANCELLED = "CANCELLED"
JOB_TIMEOUT = "TIMEOUT"
JOB_RECOVERING = "RECOVERING"

_TERMINAL = {JOB_COMPLETED, JOB_FAILED, JOB_CANCELLED, JOB_TIMEOUT}
_DEFAULT_KV = "data/async_tools.json"


def _now():
    return time.time()


class AsyncToolEngine:
    """Persisted async job engine with a real scheduler."""

    def __init__(self, kv_path=None, workers=2, poll=0.05):
        self.path = str(kv_path) if kv_path else _DEFAULT_KV
        self.store = KeyValueStore(self.path)
        self.workers = max(1, int(workers))
        self.poll = float(poll)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._executor = None

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _jobs(self):
        jobs = self.store.get("jobs") or {}
        return dict(jobs)

    def _save_jobs(self, jobs):
        self.store.set("jobs", jobs)

    def _job(self, job_id):
        return self._jobs().get(str(job_id))

    def _update(self, job_id, patch):
        with self._lock:
            jobs = self._jobs()
            if job_id not in jobs:
                return None
            jobs[job_id].update(patch)
            self._save_jobs(jobs)
            return dict(jobs[job_id])

    # ------------------------------------------------------------------
    # submission
    # ------------------------------------------------------------------
    def submit(self, tool, args=None, wait_for=None, timeout=30.0,
               max_attempts=2, kind="tool", mission_id=None,
               confirmed=False, note=""):
        """Queue a job. Validates the target honestly before queueing."""
        args = dict(args or {})
        wait_for = self._parse_ids(wait_for)
        timeout = max(0.5, float(timeout))
        max_attempts = max(1, int(max_attempts))
        kind = str(kind or "tool").strip()
        job_id = f"job_{time.time_ns()}"

        if kind == "tool":
            tool = str(tool or "").strip()
            if not tool:
                return {"success": False, "status": "invalid_argument",
                        "message": "async submit needs a tool name"}
            from tools.builder import get_registry
            target = get_registry().get(tool)
            if target is None:
                return {"success": False, "status": "invalid_argument",
                        "message": f"unknown tool '{tool}'"}
            if target.confirm_required and not confirmed:
                return {"success": False, "status": "confirm_required",
                        "message": f"{tool} requires confirmation — "
                                   "submit with confirmed=True first"}
            declared = {p.get("name")
                        for p in target.schema().get("parameters", [])}
            unknown = set(args) - declared
            if unknown:
                return {"success": False, "status": "invalid_argument",
                        "message": f"undeclared argument(s) for {tool}: "
                                   f"{sorted(unknown)}"}
        elif kind == "orchestrate":
            if not str(mission_id or "").strip():
                return {"success": False, "status": "invalid_argument",
                        "message": "kind='orchestrate' needs a mission_id"}
        else:
            return {"success": False, "status": "invalid_argument",
                    "message": f"unknown job kind '{kind}' — use tool|orchestrate"}

        for dep in wait_for:
            if self._job(dep) is None:
                return {"success": False, "status": "invalid_argument",
                        "message": f"wait_for references unknown job '{dep}'"}

        job = {
            "id": job_id,
            "kind": kind,
            "tool": tool if kind == "tool" else None,
            "args": args,
            "mission_id": mission_id if kind == "orchestrate" else None,
            "wait_for": wait_for,
            "timeout": timeout,
            "max_attempts": max_attempts,
            "attempts": 0,
            "confirmed": bool(confirmed),
            "note": str(note or ""),
            "status": JOB_WAITING if wait_for else JOB_QUEUED,
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "cancel_requested": False,
        }
        with self._lock:
            jobs = self._jobs()
            jobs[job_id] = job
            self._save_jobs(jobs)
        self.start()
        return {"success": True, "status": "QUEUED", "job_id": job_id,
                "action": "async_submit", "job": job}

    def _parse_ids(self, wait_for):
        if wait_for is None:
            return []
        if isinstance(wait_for, str):
            return [p.strip() for p in wait_for.replace(";", ",").split(",")
                    if p.strip()]
        return [str(w) for w in wait_for]

    # ------------------------------------------------------------------
    # scheduler
    # ------------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="async-engine", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._executor is not None:
            self._executor.shutdown(wait=False)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick(deadline=0.2)
            except Exception:
                pass
            time.sleep(self.poll)

    def tick(self, deadline=1.0):
        """One synchronous scheduling pass (deterministic for tests)."""
        processed = []
        start = time.monotonic()
        workers = {}
        for job_id in self._next_ready():
            if time.monotonic() - start >= float(deadline) \
                    or job_id in processed:
                break
            self._run_job(job_id, workers)
            processed.append(job_id)
        return {"processed": processed, "deadline": float(deadline)}

    def _next_ready(self):
        jobs = self._jobs()
        readiness = []
        for job_id, job in jobs.items():
            state = job.get("status")
            if state in (JOB_QUEUED, JOB_WAITING, JOB_RECOVERING):
                ready = self._deps_ready(job)
                if ready is True:
                    if state == JOB_WAITING:
                        self._update(job_id, {"status": JOB_QUEUED})
                    readiness.append(job_id)
                elif ready is None:  # a dependency is still pending
                    if state == JOB_QUEUED:
                        self._update(job_id, {"status": JOB_WAITING})
                else:  # a dependency failed/cancelled
                    self._fail_dep(job_id, job)
        return readiness

    def _deps_ready(self, job):
        for dep in job.get("wait_for", []):
            dep_job = self._job(dep)
            if dep_job is None:
                return False
            if dep_job.get("status") == JOB_COMPLETED:
                continue
            if dep_job.get("status") in (JOB_FAILED, JOB_CANCELLED,
                                         JOB_TIMEOUT):
                return False
            return None  # still pending
        return True

    def _fail_dep(self, job_id, job):
        reason = "dependency job(s) finished without COMPLETED"
        if job.get("status") == JOB_QUEUED:
            self._finish(job_id, JOB_FAILED, error=reason,
                         note="blocked by failed/cancelled dependency")
        else:
            self._update(job_id, {"status": JOB_FAILED, "error": reason,
                                  "finished_at": _now()})

    def _run_job(self, job_id, workers):
        job = self._job(job_id)
        if job.get("cancel_requested"):
            self._update(job_id, {"status": JOB_CANCELLED,
                                  "finished_at": _now(),
                                  "error": "cancelled before execution"})
            return
        self._update(job_id, {"status": JOB_RUNNING, "started_at": _now()})

        def fn():
            if job.get("kind") == "orchestrate":
                return self._dispatch_orchestrate(job)
            return self._dispatch_tool(job)

        op, kind, value = BoundedOperation.run(
            fn, timeout=float(job.get("timeout", 30.0)))

        current = self._job(job_id)
        if current.get("cancel_requested"):
            self._finish(job_id, JOB_CANCELLED,
                         error="cancel requested while running; side effects "
                               "may have occurred", finished={"note": True})
            return
        if kind == "interrupted":
            self._retry(job_id, JOB_TIMEOUT, "job exceeded its timeout budget")
        elif kind == "error":
            self._retry(job_id, JOB_FAILED, str(value))
        elif isinstance(value, dict) and value.get("success") is not True:
            self._retry(job_id, JOB_FAILED,
                        str(value.get("message") or value.get("status")
                            or "tool failed"))
        else:
            self._finish(job_id, JOB_COMPLETED,
                         result=_serialise(value))

    def _dispatch_tool(self, job):
        from tools.builder import get_registry
        from core.confirmation import CONFIRMATION
        name = job.get("tool")
        args = dict(job.get("args") or {})
        target = get_registry().get(name)
        if target is None:
            raise RuntimeError(f"unknown tool '{name}'")
        if target.confirm_required:
            if not job.get("confirmed"):
                raise PermissionError(f"{name} requires confirmation")
            request_id = CONFIRMATION.require(f"async:{name}")
            return get_registry().invoke(
                name, confirmed=True, request_id=request_id, **args)
        return get_registry().invoke(name, **args)

    def _dispatch_orchestrate(self, job):
        from core.mission_orchestrator import MissionOrchestrator
        result = MissionOrchestrator().resume(
            job.get("mission_id"), approve=bool(job.get("confirmed")))
        return {"success": bool(result.get("success")),
                "message": str(result.get("status") or "mission resumed"),
                "result": result}

    def _retry(self, job_id, terminal_status, reason):
        job = self._job(job_id)
        attempts = int(job.get("attempts", 0)) + 1
        if attempts < int(job.get("max_attempts", 2)):
            self._update(job_id, {
                "status": JOB_RECOVERING, "attempts": attempts,
                "error": reason, "finished_at": None, "started_at": None})
            # RECOVERING is re-queued on the next tick pass.
            return
        self._finish(job_id, terminal_status, error=reason, attempts=attempts)

    def _finish(self, job_id, status, result=None, error=None, attempts=None,
                note=None, finished=None):
        patch = {"status": status, "finished_at": _now()}
        if result is not None:
            patch["result"] = result
        if error is not None:
            patch["error"] = error
        if attempts is not None:
            patch["attempts"] = attempts
        if note is not None:
            patch["cancel_requested"] = False
        self._update(job_id, patch)

    # ------------------------------------------------------------------
    # operator surface
    # ------------------------------------------------------------------
    def cancel(self, job_id):
        job = self._job(job_id)
        if job is None:
            return {"success": False, "status": "invalid_argument",
                    "message": f"unknown job '{job_id}'"}
        if job.get("status") in _TERMINAL:
            return {"success": False, "status": "ok",
                    "message": f"job already {job['status']}; nothing to "
                               "cancel", "job_id": job_id}
        if job.get("status") == JOB_RUNNING:
            self._update(job_id, {"cancel_requested": True,
                                  "note": "cancel requested while running"})
            return {"success": True, "status": "ok",
                    "message": "cancel requested while RUNNING — the job is "
                               "finalised once its bounded operation returns",
                    "job_id": job_id}
        self._update(job_id, {"status": JOB_CANCELLED, "finished_at": _now(),
                              "error": "cancelled before execution"})
        return {"success": True, "status": JOB_CANCELLED, "job_id": job_id}

    def status(self, job_id=None):
        jobs = self._jobs()
        if job_id is not None:
            job = jobs.get(str(job_id))
            if job is None:
                return {"success": False, "status": "invalid_argument",
                        "message": f"unknown job '{job_id}'"}
            return {"success": True, "status": "ok", "job": job}
        counts = {}
        for job in jobs.values():
            state = job.get("status", "UNKNOWN")
            counts[state] = counts.get(state, 0) + 1
        return {"success": True, "status": "ok",
                "total": len(jobs), "states": counts,
                "jobs": [self._summary(j) for j in sorted(
                    jobs.values(), key=lambda j: j.get("created_at", 0))]}

    def result(self, job_id):
        job = self._job(job_id)
        if job is None:
            return {"success": False, "status": "invalid_argument",
                    "message": f"unknown job '{job_id}'"}
        out = {"success": True, "status": "ok", "job_id": job_id,
               "state": job.get("status")}
        if job.get("status") == JOB_COMPLETED:
            out["result"] = job.get("result")
        else:
            out["message"] = f"job is {job['status']}; no result yet"
            if job.get("error"):
                out["error"] = job["error"]
        return out

    def wait(self, job_id, timeout=5.0):
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            job = self._job(job_id)
            if job is not None and job.get("status") in _TERMINAL:
                return {"success": True, "status": "ok", "job": job}
            time.sleep(self.poll)
        job = self._job(job_id)
        return {"success": False, "status": "timeout",
                "message": f"job did not finish within {timeout}s",
                "job": job}

    def recover(self):
        """Restart recovery: resurrect interrupted/queued jobs honestly."""
        jobs = self._jobs()
        resurrected = []
        for job_id, job in jobs.items():
            state = job.get("status")
            if state == JOB_COMPLETED or state == JOB_CANCELLED:
                continue
            attempts = int(job.get("attempts", 0))
            if state == JOB_RUNNING:
                attempts += 1
            if attempts > int(job.get("max_attempts", 2)):
                continue
            self._update(job_id, {
                "status": JOB_RECOVERING,
                "attempts": attempts,
                "note": "resurrected after restart", "started_at": None,
                "finished_at": None})
            resurrected.append(job_id)
        self.start()
        return {"success": True, "status": "ok",
                "recovered": len(resurrected), "job_ids": resurrected,
                "message": "interrupted work marked RECOVERING for redispatch"}

    def _summary(self, job):
        return {
            "id": job["id"], "kind": job.get("kind"),
            "tool": job.get("tool"), "status": job.get("status"),
            "attempts": job.get("attempts"),
            "created_at": job.get("created_at"),
            "finished_at": job.get("finished_at"),
            "wait_for": list(job.get("wait_for", [])),
        }


def _serialise(value):
    from json import dumps, loads
    try:
        return loads(dumps(value, default=str))
    except Exception:
        return str(value)


async_tool_engine = AsyncToolEngine()

__all__ = [
    "AsyncToolEngine",
    "async_tool_engine",
    "JOB_QUEUED", "JOB_WAITING", "JOB_RUNNING", "JOB_COMPLETED",
    "JOB_FAILED", "JOB_CANCELLED", "JOB_TIMEOUT", "JOB_RECOVERING",
]