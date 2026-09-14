"""Command Center / Admin (Day 2, feature 98).

Aggregates real operational data: provider statuses, capabilities,
tool registry, memory counts, scheduler summary, self-test result and
workspace health. Never fabricates. Worst-status rollup goes through the
provider status vocabulary.
"""

import shutil
from datetime import datetime

from core.kv import KeyValueStore

_STATUS_ORDER = ["AVAILABLE", "UNAVAILABLE", "OFFLINE", "REQUIRES_AUTH",
                 "REQUIRES_PERMISSION", "NOT_CONFIGURED", "FAILED"]


class CommandCenter:

    def __init__(self, kv=None, workspace_root=None):
        self.kv = kv or KeyValueStore("data/command_center.json")
        self.workspace_root = workspace_root

    # ------------------------------------------------------------------
    def _provider_statuses(self):
        from core.providers.registry import providers_registry
        rows = providers_registry.status_all()
        return [{"name": r.get("name"), "status": r.get("status"),
                 "capabilities": sorted(r.get("capabilities", []))}
                for r in rows]

    def _capabilities(self):
        from core.capabilities import capabilities
        return capabilities.structured()

    def _tools(self):
        from tools.builder import get_registry
        registry = get_registry()
        names = sorted(registry.names())
        return {"count": len(names), "names": names}

    def _memory(self):
        from memory.database import MemoryDatabase
        database = MemoryDatabase()
        rows = database.get_all()
        return {"count": len(rows)}

    def _scheduler(self):
        summary = {"status": "AVAILABLE", "tasks": 0}
        try:
            from core.scheduler import Scheduler
            scheduler = Scheduler()
            tasks = []
            if hasattr(scheduler, "list"):
                tasks = scheduler.list() or []
            summary["tasks"] = len(tasks)
        except Exception:
            summary["status"] = "NOT_CONFIGURED"
            summary["tasks"] = 0
        return summary

    def _selftest(self):
        from core.selftest import selftest
        try:
            result = selftest.run()
            return {
                "total": result.get("total", 0),
                "passed": result.get("passed", 0),
                "failed": result.get("failed", 0),
                "checks": result.get("checks", []),
            }
        except Exception as exc:
            return {"status": "FAILED", "message": repr(exc),
                    "total": 0, "passed": 0, "failed": 0, "checks": []}

    def _workspace(self):
        root = self.workspace_root
        info = {}
        if root is not None:
            try:
                disk = shutil.disk_usage(root)
                info["free_bytes"] = disk.free
                info["total_bytes"] = disk.total
                info["percent_free"] = round(100.0 * disk.free / disk.total, 1)
            except OSError as exc:
                info["error"] = str(exc)
        return info

    # ------------------------------------------------------------------
    def dashboard(self):
        providers = self._provider_statuses()
        capabilities = self._capabilities()
        tools = self._tools()
        memory = self._memory()
        scheduler = self._scheduler()
        selftest = self._selftest()
        workspace = self._workspace()
        flags = self.flags()
        return {
            "generated_at": datetime.now().isoformat(),
            "providers": providers,
            "provider_statuses": {p["name"]: p["status"] for p in providers},
            "capabilities": capabilities,
            "tools": tools,
            "memory": memory,
            "scheduler": scheduler,
            "selftest": selftest,
            "workspace": workspace,
            "flags": flags,
        }

    # ------------------------------------------------------------------
    def health_rollup(self):
        dashboard = self.dashboard()
        statuses = []
        for provider in dashboard["providers"]:
            status = provider["status"]
            if status in _STATUS_ORDER:
                statuses.append(status)
        for capability, entry in dashboard["capabilities"].items():
            status = _normalise_capability_status(entry["status"])
            if status is not None:
                statuses.append(status)
        if not statuses:
            return {"worst_status": "AVAILABLE", "rolled_up": True}
        worst = min(statuses, key=lambda s: _STATUS_ORDER.index(s))
        ranked = sorted(statuses, key=lambda s: _STATUS_ORDER.index(s),
                        reverse=True)
        return {"worst_status": worst, "rolled_up": True, "ranked": ranked}

    # ------------------------------------------------------------------
    def run_selftest(self):
        return self._selftest()

    # ------------------------------------------------------------------
    def flags(self):
        return self.kv.get("flags", {})

    def set_flag(self, name, value, by="command_center"):
        flags = self.flags()
        audit = self.kv.get("flag_audit", [])
        audit.append({
            "name": name, "value": value, "by": by,
            "at": datetime.now().isoformat(),
        })
        flags[str(name)] = value
        self.kv.set("flags", flags)
        self.kv.set("flag_audit", audit)
        return {"flag": str(name), "value": value, "audited": True}

    def flag_audit(self, name=None):
        entries = self.kv.get("flag_audit", [])
        if name:
            return [e for e in entries if e["name"] == name]
        return entries


def _normalise_capability_status(status):
    mapping = {
        "available": "AVAILABLE",
        "limited": "AVAILABLE",
        "not_configured": "NOT_CONFIGURED",
        "unavailable": "UNAVAILABLE",
        "offline": "OFFLINE",
    }
    return mapping.get(status)


__all__ = ["CommandCenter"]