"""Feature 112 tools — asynchronous tool execution surface (terminal-first).

Submit a registered tool (or an orchestration resume) for background
execution, then inspect/wait/cancel/recover. Everything is persisted through
``core.async_tools_engine`` and routes gated tools through CONFIRMATION.
"""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_json, _parse_list

_async_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _async_tools.append(spec)


@lru_cache(maxsize=1)
def _engine():
    from core.async_tools_engine import AsyncToolEngine
    return AsyncToolEngine()


def _async_engine(**kw):
    return _engine()


def _async_submit(**kw):
    tool = str(kw.get("tool") or "").strip()
    kind = str(kw.get("kind") or "tool").strip()
    mission_id = kw.get("mission_id")
    args = _parse_json(kw.get("args")) if kw.get("args") is not None else {}
    args = dict(args or {})
    wait_for = kw.get("wait_for")
    if wait_for is not None:
        wait_for = _parse_list(wait_for)
    return _engine().submit(
        tool, args=args, wait_for=wait_for,
        timeout=float(kw.get("timeout", 30.0)),
        max_attempts=int(kw.get("max_attempts", 2)),
        kind=kind, mission_id=mission_id,
        confirmed=bool(kw.get("confirmed", False)),
        note=str(kw.get("note") or ""))


def _async_status(**kw):
    job_id = kw.get("job_id")
    return _engine().status(job_id=str(job_id).strip() if job_id else None)


def _async_result(**kw):
    job_id = str(kw.get("job_id") or "").strip()
    if not job_id:
        return {"success": False, "status": "invalid_argument",
                "message": "job_id is empty"}
    return _engine().result(job_id)


def _async_cancel(**kw):
    job_id = str(kw.get("job_id") or "").strip()
    if not job_id:
        return {"success": False, "status": "invalid_argument",
                "message": "job_id is empty"}
    return _engine().cancel(job_id)


def _async_wait(**kw):
    job_id = str(kw.get("job_id") or "").strip()
    if not job_id:
        return {"success": False, "status": "invalid_argument",
                "message": "job_id is empty"}
    return _engine().wait(job_id, timeout=float(kw.get("timeout", 10.0)))


def _async_recover(**kw):
    return _engine().recover()


# --- Feature 112 ----------------------------------------------------------
_add("async_engine", "low", "async",
     "Async engine summary: job states by type",
     [], _async_engine)
_add("async_submit", "high", "async",
     "Submit a registered tool (or orchestration resume) for background "
     "execution with a bounded retry/timeout policy",
     [("tool", False, "registered tool to run (kind=tool)"),
      ("args", False, "JSON object of tool arguments"),
      ("wait_for", False, "job id(s) this job waits for"),
      ("timeout", False, "per-attempt seconds"),
      ("max_attempts", False, "int retry budget"),
      ("kind", False, "tool | orchestrate"),
      ("mission_id", False, "mission id for kind=orchestrate"),
      ("confirmed", False, "bool — approve gated target execution"),
      ("note", False, "free-form note")],
     _async_submit)
_add("async_status", "low", "async",
     "Inspect one job or the full async engine state",
     [("job_id", False, "optional job id")], _async_status)
_add("async_result", "low", "async",
     "Fetch the result of a COMPLETED job",
     [("job_id", True, "job id")], _async_result)
_add("async_cancel", "medium", "async",
     "Cancel a queued/waiting job (running jobs finalise honestly)",
     [("job_id", True, "job id")], _async_cancel)
_add("async_wait", "low", "async",
     "Wait up to a bounded timeout for a job to reach a terminal state",
     [("job_id", True, "job id"), ("timeout", False, "seconds")],
     _async_wait)
_add("async_recover", "medium", "async",
     "Resurrect interrupted work after a restart (RECOVERING redispatch)",
     [], _async_recover)


TOOLS = _async_tools

__all__ = ["TOOLS"]