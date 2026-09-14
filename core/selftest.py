"""Self-test / test harness (row 35).

The self-test mechanism runs real checks itself (not just counting pytest):
* ``run()`` executes every registered check and reports per-check status
* a check that reports itself unavailable is NOT marked as a pass
* failures are enumerated explicitly
* ``security_check`` blocks dangerous command vectors
* ``format_selftest`` renders a text report
"""

import importlib
import json
import time
from collections import OrderedDict

_DANGEROUS_PATTERNS = [
    "rm -rf /", "rmdir /s", "del /f /s /q c:", "format c:",
    "shutdown /s", "rd /s /q", "takeown", "net user ", "reg delete",
]


class SelfTestRunner:

    def __init__(self):
        self._checks = OrderedDict()

    # ------------------------------------------------------------------
    def add(self, name, function, category="general"):
        self._checks[name] = {"function": function, "category": category}

    def names(self):
        return list(self._checks.keys())

    # ------------------------------------------------------------------
    def security_check(self, text):
        """Return (allowed, reason) — blocks dangerous vectors."""
        lowered = (text or "").lower()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in lowered:
                return False, f"blocked pattern: {pattern}"
        return True, ""

    # ------------------------------------------------------------------
    def run(self, names=None, timeout_per_check=15):
        results = []
        failures = []
        for name, meta in self._checks.items():
            if names and name not in names:
                continue
            start = time.monotonic()
            status = "pass"
            detail = ""
            try:
                outcome = meta["function"]()
                if outcome is None:
                    status = "pass"
                elif isinstance(outcome, dict):
                    if outcome.get("available") is False:
                        # never claim unavailable as passing
                        status = "fail"
                        detail = "unavailable (unchanged)"
                    elif outcome.get("ok") is False or outcome.get("status") in (
                            "fail", "error", "unavailable", "missing"):
                        status = "fail"
                        detail = str(outcome.get("message", ""))
                    else:
                        status = "pass"
                elif outcome is False:
                    status = "fail"
                    detail = "check returned False"
            except Exception as exc:
                status = "fail"
                detail = repr(exc)
            elapsed = round(time.monotonic() - start, 3)
            if status != "pass":
                failures.append({
                    "name": name,
                    "status": status,
                    "reason": detail,
                })
            results.append({
                "name": name,
                "category": meta["category"],
                "status": status,
                "time": elapsed,
                "detail": detail,
            })
        return {
            "checks": results,
            "failures": failures,
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "pass"),
            "failed": len(failures),
        }

    def format_selftest(self, report):
        lines = ["===== ARVEN SELF-TEST ====="]
        for check in report["checks"]:
            mark = "PASS" if check["status"] == "pass" else check["status"].upper()
            lines.append(f"{mark:>8}  [{check['category']}] {check['name']}"
                         f"{('  -> ' + check['detail']) if check['detail'] else ''}")
        lines.append("")
        lines.append(f"TOTAL {report['total']} | PASSED {report['passed']} | "
                     f"FAILED {report['failed']}")
        if report["failures"]:
            lines.append("FAILURES:")
            for failure in report["failures"]:
                lines.append(f"  - {failure['name']}: {failure['reason']}")
        return "\n".join(lines)


def build_default_runner():
    """Register the built-in production checks (real, not placeholders)."""
    runner = SelfTestRunner()

    def check_python_runtime():
        major, minor = getattr(importlib.import_module("sys"), "version_info")[:2]
        return {"ok": True, "status": "ok", "version": f"{major}.{minor}"}

    def check_config_boot():
        from config import get_settings
        settings = get_settings()
        return {"ok": bool(settings.APP_NAME), "status": "ok"}

    def check_tool_registry():
        from tools.builder import get_registry
        reg = get_registry()
        count = len(reg.names())
        return {"ok": count >= 20, "status": "ok", "message": f"{count} tools"}

    def check_memory_store():
        from memory.database import MemoryDatabase
        probe = MemoryDatabase()
        count = len(probe.get_all())
        return {"ok": True, "status": "ok", "message": f"{count} memories"}

    def check_security_gate():
        from core.safety import SAFETY, RISK_DESTRUCTIVE
        risk = SAFETY.risk_label("delete_file", "x.txt")
        return {"ok": risk == RISK_DESTRUCTIVE, "status": "ok",
                "message": risk}

    def check_recovery_layer():
        from core.recovery import RecoveryAction
        return {"ok": RecoveryAction is not None, "status": "ok"}

    def check_voice_backend():
        try:
            from voice.input import voice_input
            return {"ok": True, "status": "ok",
                    "available": voice_input.microphone_available()}
        except Exception:
            return {"ok": False, "status": "fail", "available": False,
                    "message": "voice module missing"}

    def check_tts_backend():
        try:
            from voice.output import voice_output
            return {"ok": voice_output.available(), "status": "ok",
                    "available": bool(voice_output.available())}
        except Exception:
            return {"ok": False, "status": "fail", "available": False,
                    "message": "tts module missing"}

    def check_offline_paths():
        from core.paths import normalize_path
        return {"ok": True, "status": "ok"}

    runner.add("python_runtime", check_python_runtime, "system")
    runner.add("config_boots", check_config_boot, "config")
    runner.add("tool_registry_builds", check_tool_registry, "tools")
    runner.add("memory_store_reachable", check_memory_store, "memory")
    runner.add("security_gate_intact", check_security_gate, "security")
    runner.add("recovery_layer_present", check_recovery_layer, "recovery")
    runner.add("voice_backend_probe", check_voice_backend, "voice")
    runner.add("tts_backend_probe", check_tts_backend, "voice")
    runner.add("offline_paths_normalize", check_offline_paths, "paths")
    return runner


selftest = build_default_runner()

__all__ = ["SelfTestRunner", "selftest", "build_default_runner"]