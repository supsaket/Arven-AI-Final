"""Diagnostics & System Health (feature 63, Day 2).

Diagnostics.run() returns a structured system snapshot: disk usage, memory,
cpu, python version, network probe, core module health, provider statuses and
a selftest report when available. Every failure is reported honestly — nothing
is assumed healthy.

report() writes a Markdown summary to Output/Diagnostics.
"""

import importlib
import platform
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from core.output import output_manager

# Modules expected to import cleanly.
CORE_MODULES = [
    "core.kv",
    "core.output",
    "core.selftest",
    "core.health",
    "core.safety",
    "core.confirmation",
    "core.security",
    "core.recovery",
]


class Diagnostics:

    def __init__(self, workspace_root=None):
        self.workspace = Path(workspace_root) if workspace_root else Path.cwd()
        self.diag_root = self.workspace / "Output" / "Diagnostics"

    # ------------------------------------------------------------------
    def _disk(self, path):
        try:
            usage = shutil.disk_usage(path)
            return {
                "path": str(path),
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent_used": round(usage.used / usage.total * 100, 1) if usage.total else None,
            }
        except Exception as exc:
            return {"path": str(path), "status": "FAILED", "error": repr(exc)}

    def _network(self):
        try:
            from core.providers.base import probe_network
            return {"online": bool(probe_network()), "method": "core.providers.base.probe_network"}
        except Exception as exc:
            return {"status": "FAILED", "error": repr(exc)}

    def _core_health(self):
        results = {}
        for module in CORE_MODULES:
            try:
                imported = importlib.import_module(module)
                results[module] = {
                    "status": "AVAILABLE",
                    "ok": True,
                    "loaded": imported is not None,
                }
            except Exception as exc:
                results[module] = {"status": "FAILED", "ok": False, "error": repr(exc)}
        return results

    def _provider_statuses(self):
        try:
            from core.providers.registry import providers_registry
            return {"status": "AVAILABLE", "providers": providers_registry.status_all()}
        except Exception as exc:
            return {"status": "FAILED", "error": repr(exc)}

    def _health_check(self):
        try:
            from core.health import run_system_check
            if not hasattr(run_system_check, "__call__"):
                return {"status": "UNAVAILABLE", "note": "run_system_check not callable"}
            report = run_system_check()
            return {"status": "AVAILABLE", "overall": report.get("overall"),
                    "components": report.get("components", [])}
        except Exception as exc:
            return {"status": "FAILED", "error": repr(exc)}

    def _selftest(self):
        try:
            from core.selftest import selftest as runner
            if not hasattr(runner, "run"):
                return {"status": "UNAVAILABLE", "note": "selftest runner has no run()"}
            report = runner.run()
            return {"status": "AVAILABLE",
                    "total": report.get("total"), "passed": report.get("passed"),
                    "failed": report.get("failed")}
        except Exception as exc:
            return {"status": "FAILED", "error": repr(exc)}

    # ------------------------------------------------------------------
    def run(self):
        import psutil

        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "python_exe": sys.executable,
            "disk": {
                "workspace": self._disk(self.workspace),
                "temp": self._disk(str(Path(sys.executable).drive + "\\") if Path(sys.executable).drive else str(Path.home())),
            },
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "percent": memory.percent,
            },
            "cpu": {
                "percent": cpu,
                "count": cpu_count,
            },
            "network": self._network(),
            "core_health": self._core_health(),
            "providers": self._provider_statuses(),
            "system_check": self._health_check(),
            "selftest": self._selftest(),
        }
        return snapshot

    # ------------------------------------------------------------------
    def report(self, filename="diagnostics"):
        """Write Markdown report to Output/Diagnostics and return its path."""
        snapshot = self.run()
        lines = []
        lines.append("# ARVEN Diagnostics")
        lines.append("")
        lines.append(f"- Generated: {snapshot['timestamp']}")
        lines.append(f"- Platform: {snapshot['platform']}")
        lines.append(f"- Python: {snapshot['python']}")
        lines.append("")

        lines.append("## Disk")
        for key, value in snapshot.get("disk", {}).items():
            lines.append(f"- **{key}**: {value.get('status', 'AVAILABLE')} "
                         f"free={value.get('free')} used={value.get('used')}")
        lines.append("")

        lines.append("## Memory / CPU")
        mem = snapshot.get("memory", {})
        lines.append(f"- Memory: {mem.get('percent')}% used ({mem.get('available')} free)")
        cpu = snapshot.get("cpu", {})
        lines.append(f"- CPU: {cpu.get('percent')}% across {cpu.get('count')} cores")
        lines.append("")

        lines.append("## Network")
        net = snapshot.get("network", {})
        lines.append(f"- Online: {net.get('online', net.get('status', 'UNKNOWN'))}")
        lines.append("")

        lines.append("## Core Module Health")
        for module, value in snapshot.get("core_health", {}).items():
            lines.append(f"- {module}: {value.get('status')}")
        lines.append("")

        lines.append("## Providers")
        providers = snapshot.get("providers", {})
        for p in providers.get("providers", []):
            lines.append(f"- {p.get('name')}: {p.get('status')} ({p.get('reason', '')})")
        lines.append("")

        lines.append("## System Check")
        syscheck = snapshot.get("system_check", {})
        lines.append(f"- Overall: {syscheck.get('overall', syscheck.get('status'))}")
        lines.append("")

        lines.append("## Selftest")
        st = snapshot.get("selftest", {})
        lines.append(f"- total={st.get('total')} passed={st.get('passed')} "
                     f"failed={st.get('failed')} status={st.get('status')}")

        markdown = "\n".join(lines)
        self.diag_root.mkdir(parents=True, exist_ok=True)
        safe = output_manager.safe_filename(filename)
        out_path = output_manager.next_rw_path(self.diag_root, safe, ".md")
        out_path.write_text(markdown, encoding="utf-8")
        output_manager.metadata_sidecar(out_path, {"kind": "diagnostics_report",
                                                   "generated_at": snapshot["timestamp"]})
        return {"path": str(out_path), "snapshot": snapshot, "markdown": markdown}


__all__ = ["Diagnostics"]
