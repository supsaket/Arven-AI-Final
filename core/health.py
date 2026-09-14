"""Health monitor — component checks, overall state, and bounded timers.

Guidance (row 26):
* ``HealthState`` (and ``HealthStatus`` alias) enums:
  HEALTHY / DEGRADED / UNAVAILABLE / ERROR (values are lowercase strings).
* ``check(name, state, details)`` builds a normalized component dict.
* ``run_system_check(offline=False)`` -> components + overall + response.
* ``timed(function, timeout)`` returns value or an error report.
* ``format_system_check(check)`` -> human-readable text with OVERALL line.
"""

import platform
import time
from enum import Enum


class HealthState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class HealthStatus(Enum):
    OK = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


_STATE_RANK = {
    HealthState.ERROR: 4,
    HealthState.UNAVAILABLE: 3,
    HealthState.DEGRADED: 2,
    HealthState.HEALTHY: 1,
}


def _state(value):
    if isinstance(value, HealthState):
        return value
    if isinstance(value, HealthStatus):
        return HealthState(value.value)
    text = str(value).lower().strip()
    for candidate in HealthState:
        if candidate.value == text or candidate.name.lower() == text:
            return candidate
    return HealthState.HEALTHY


def check(name, state="healthy", details=None):
    """Normalize a single component check into a dict."""
    state = _state(state)
    available = state is not HealthState.UNAVAILABLE and state is not HealthState.ERROR
    return {
        "name": str(name),
        "state": state.value,
        "ok": available,
        "details": details or {},
    }


def _precedence(components):
    if not components:
        return HealthState.HEALTHY
    worst = max((_state(c["state"]) for c in components), key=lambda s: _STATE_RANK[s])
    return worst


def overall_state(components):
    return _precedence(components).value


def timed(function, timeout=2.0):
    """Run function with a wall-clock bound. Returns (kind, value) or error."""
    import threading

    result = {}
    def runner():
        try:
            result["value"] = function()
            result["ok"] = True
        except Exception as exc:
            result["ok"] = False
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout=float(timeout))
    if thread.is_alive():
        return "error", "timed out"
    if not result.get("ok"):
        return "error", repr(result["error"])
    return "ok", result["value"]


def run_system_check(offline=False):
    """Comprehensive system check with stable component list."""
    components = []

    try:
        comp = check("python", HealthState.HEALTHY,
                     {"version": platform.python_version()})
    except Exception as exc:
        comp = check("python", HealthState.ERROR, {"reason": str(exc)})
    components.append(comp)

    # config
    from config import get_settings
    try:
        settings = get_settings()
        components.append(check("config", HealthState.HEALTHY,
                                {"app": settings.APP_NAME,
                                 "model": settings.get("MODEL_NAME", "")}))
    except Exception as exc:
        components.append(check("config", HealthState.ERROR, {"reason": str(exc)}))

    # tools registry
    try:
        from tools.builder import get_registry
        reg = get_registry()
        components.append(check("tools", HealthState.HEALTHY,
                                {"count": len(reg.names())}))
    except Exception as exc:
        components.append(check("tools", HealthState.ERROR, {"reason": str(exc)}))

    # logs
    try:
        from core.logging import logger
        components.append(check("logs", HealthState.HEALTHY,
                                {"file": logger.rotation_config().get("path")}))
    except Exception as exc:
        components.append(check("logs", HealthState.UNAVAILABLE, {"reason": str(exc)}))

    # memory store
    try:
        from memory.database import MemoryDatabase
        probe = MemoryDatabase()
        count = len(probe.get_all())
        components.append(check("memory", HealthState.HEALTHY, {"stored": count}))
    except Exception as exc:
        components.append(check("memory", HealthState.UNAVAILABLE, {"reason": str(exc)}))

    # voice (microphone) when offline is reported, still attempted locally
    try:
        from voice.input import voice_input
        mic = bool(voice_input.microphone_available())
        components.append(check("voice", HealthState.HEALTHY if mic else HealthState.UNAVAILABLE,
                                {"microphone": mic}))
    except Exception as exc:
        components.append(check("voice", HealthState.UNAVAILABLE, {"reason": str(exc)}))

    if offline:
        for idx, comp in enumerate(components):
            if comp["state"] == HealthState.HEALTHY.value:
                components[idx] = check(comp["name"], HealthState.UNAVAILABLE,
                                        {**comp["details"], "offline": True})

    overall = overall_state(components)
    response = "all systems operational"
    if overall == HealthState.ERROR.value:
        response = "errors detected"
    elif overall == HealthState.UNAVAILABLE.value:
        response = "some components unavailable"
    elif overall == HealthState.DEGRADED.value:
        response = "degraded — check the details"

    return {
        "components": components,
        "overall": overall,
        "response": response,
    }


def check_failure_state_unavailable():
    """A failure while checking is reported as unavailable (never fake-healthy)."""
    return check("example_failure", HealthState.UNAVAILABLE, {"reason": "probe failed"})


def format_system_check(check_result):
    lines = []
    lines.append("===== ARVEN SYSTEM CHECK =====")
    for comp in check_result["components"]:
        state = comp["state"]
        mark = "OK" if state == "healthy" else state.upper()
        lines.append(f"{mark:>12}  {comp['name']}")
    lines.append("")
    overall = check_result["overall"]
    mark = "OK" if overall == "healthy" else overall.upper()
    lines.append(f"OVERALL:{mark}  ({check_result['response']})")
    return "\n".join(lines)


__all__ = [
    "HealthState", "HealthStatus", "check", "check_failure_state_unavailable",
    "timed", "run_system_check", "overall_state", "format_system_check",
]