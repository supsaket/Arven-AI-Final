"""Service Orchestration — Feature 97.

``ServiceOrchestrator`` is a plain class (not a Provider) persisted on a
KeyValueStore. It models a registry of services and their dependencies, and
performs REAL orchestration bookkeeping:

- ``register_service`` / ``list_services`` / ``unregister_service``
- ``dependency_order`` — real topological sort with cycle detection
- ``start_service`` / ``stop_service`` — honest state machine; starting a
  service with declared external side effects requires explicit
  confirmation and is refused without the gate. No unrelated system
  service is ever genuinely launched — state is tracked only.
- ``health_rollup`` — worst honest status over deps + own
- ``degraded_detection`` — services whose deps are not available
- ``bottleneck_report`` — non-running services that block dependents

All responses use the honest status vocabulary from
``core.providers.base``.
"""

from datetime import datetime

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.providers.base import (
    STATUS_AVAILABLE,
    STATUS_UNAVAILABLE,
    STATUS_OFFLINE,
    STATUS_REQUIRES_PERMISSION,
    STATUS_NOT_CONFIGURED,
    STATUS_FAILED,
    ok,
    reject,
)

STATE_STOPPED = "stopped"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_STOPPING = "stopping"
STATE_DEGRADED = "degraded"

# service state -> honest contract status
_STATE_STATUS = {
    STATE_RUNNING: STATUS_AVAILABLE,
    STATE_DEGRADED: STATUS_UNAVAILABLE,
    STATE_STARTING: STATUS_REQUIRES_PERMISSION,
    STATE_STOPPING: STATUS_REQUIRES_PERMISSION,
    STATE_STOPPED: STATUS_OFFLINE,
}

_STATUS_RANK = {
    STATUS_AVAILABLE: 0,
    STATUS_REQUIRES_PERMISSION: 1,
    STATUS_UNAVAILABLE: 2,
    STATUS_OFFLINE: 3,
    STATUS_NOT_CONFIGURED: 4,
    STATUS_FAILED: 5,
}


def _confirm_gate(confirmed, trusted=False, request_id=None, destructive=False):
    """Honest explicit-confirmation gate (contract shared across Day 2)."""
    if not confirmed:
        return False, "requires confirmation"
    if destructive:
        if not (trusted and request_id):
            return False, "destructive action requires a trusted, confirmed request id"
        if not CONFIRMATION.is_pending_ok(request_id):
            return False, "confirmation request is not pending (unknown or expired)"
        return True, "confirmed"
    if trusted:
        return True, "trusted and confirmed"
    if request_id:
        if not CONFIRMATION.is_pending_ok(request_id):
            return False, "confirmation request is not pending (unknown or expired)"
        return True, "confirmed"
    return True, "confirmed"


class ServiceOrchestrator:
    """KV-persisted service registry + honest orchestration state machine."""

    name = "services"
    category = "orchestration"

    def __init__(self, path=None):
        self._kv = KeyValueStore(path or "data/services.json")

    # ------------------------------------------------------------------
    # KV helpers
    # ------------------------------------------------------------------
    def _services(self):
        raw = self._kv.get("services", {})
        return raw if isinstance(raw, dict) else {}

    def _save_services(self, services):
        self._kv.set("services", services)

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------
    def register_service(self, service_id, display_name=None, version="1.0",
                         deps=None, health_check=None, side_effects=False):
        service_id = str(service_id or "").strip().lower()
        if not service_id:
            return reject(STATUS_FAILED, "service_id is required")
        services = self._services()
        if service_id in services:
            return reject(STATUS_UNAVAILABLE,
                          f"service already registered: {service_id}")
        entry = {
            "id": service_id,
            "display_name": str(display_name or service_id),
            "version": str(version or "1.0"),
            "status": STATE_STOPPED,
            "deps": sorted({str(d).strip().lower() for d in (deps or [])}),
            "health_check": health_check,
            "side_effects": bool(side_effects),
            "registered_at": datetime.now().isoformat(),
        }
        services[service_id] = entry
        self._save_services(services)
        return ok("service registered", data={"service": entry})

    def list_services(self):
        services = self._services()
        return ok("services",
                  data={"services": [services[s] for s in sorted(services)],
                        "service_count": len(services)})

    def get_service(self, service_id):
        service_id = str(service_id or "").strip().lower()
        services = self._services()
        if service_id not in services:
            return reject(STATUS_NOT_CONFIGURED,
                          f"service not registered: {service_id}")
        return ok("service", data={"service": services[service_id]})

    def unregister_service(self, service_id, confirmed=False, trusted=False,
                           request_id=None):
        service_id = str(service_id or "").strip().lower()
        allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                        destructive=True)
        if not allowed:
            return reject(
                STATUS_REQUIRES_PERMISSION,
                f"unregistering a service requires confirmation: {reason}",
                data={"service_id": service_id},
                requires_confirmation=True,
            )
        services = self._services()
        if service_id not in services:
            return reject(STATUS_NOT_CONFIGURED,
                          f"service not registered: {service_id}")
        del services[service_id]
        self._save_services(services)
        return ok("service unregistered", data={"service_id": service_id})

    # ------------------------------------------------------------------
    # Topological order
    # ------------------------------------------------------------------
    def _find_cycle(self, services):
        white, gray, black = 0, 1, 2
        color = {sid: white for sid in services}

        def visit(node, stack):
            color[node] = gray
            stack.append(node)
            for dep in services[node].get("deps", []):
                if dep not in services:
                    continue
                if color[dep] == gray:
                    return stack[stack.index(dep):] + [dep]
                if color[dep] == white:
                    cycle = visit(dep, list(stack))
                    if cycle:
                        return cycle
            color[node] = black
            return None

        for sid in services:
            if color[sid] == white:
                cycle = visit(sid, [])
                if cycle:
                    return cycle
        return None

    def dependency_order(self, root=None):
        """Kahn topological sort over the dependency graph. A service comes
        after all of its dependencies. Cycles are detected and reported."""
        services = self._services()
        if not services:
            return reject(STATUS_NOT_CONFIGURED, "no services registered",
                          data={"order": [], "cycle": None})

        relevant = set(services)
        if root:
            root = str(root).strip().lower()
            if root not in services:
                return reject(STATUS_NOT_CONFIGURED,
                              f"service not registered: {root}",
                              data={"order": [], "cycle": None})
            stack = [root]
            relevant = set()
            while stack:
                node = stack.pop()
                if node in relevant:
                    continue
                relevant.add(node)
                for dep in services[node].get("deps", []):
                    if dep in services:
                        stack.append(dep)

        cycle = self._find_cycle({s: services[s] for s in relevant})
        if cycle:
            return reject(STATUS_FAILED, "dependency cycle detected",
                          data={"order": [], "cycle": cycle})

        remaining_deps = {sid: 0 for sid in relevant}
        for sid in relevant:
            for dep in services[sid].get("deps", []):
                if dep in relevant:
                    remaining_deps[sid] += 1

        ready = sorted(sid for sid, count in remaining_deps.items() if count == 0)
        order = []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for sid in relevant:
                if node in services[sid].get("deps", []):
                    remaining_deps[sid] -= 1
                    if remaining_deps[sid] == 0:
                        ready.append(sid)
            ready.sort()

        if len(order) != len(relevant):
            return reject(STATUS_FAILED, "dependency cycle detected",
                          data={"order": order, "cycle": self._find_cycle(
                              {s: services[s] for s in relevant})})
        return ok("dependency order",
                  data={"order": order, "root": root, "cycle": None})

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------
    def _missing_deps(self, services, entry):
        return [d for d in entry.get("deps", [])
                if d not in services or services[d].get("status") != STATE_RUNNING]

    def start_service(self, service_id, confirmed=False, trusted=False,
                      request_id=None):
        service_id = str(service_id or "").strip().lower()
        services = self._services()
        if service_id not in services:
            return reject(STATUS_NOT_CONFIGURED,
                          f"service not registered: {service_id}")
        entry = services[service_id]

        if entry.get("side_effects"):
            allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                            destructive=False)
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"starting '{service_id}' has external side effects and "
                    f"requires confirmation: {reason}",
                    data={"service": entry,
                          "side_effect_firewalled": True,
                          "started": False},
                    requires_confirmation=True,
                )

        missing = self._missing_deps(services, entry)
        if missing:
            entry["status"] = STATE_DEGRADED
            self._save_services(services)
            return reject(
                STATUS_UNAVAILABLE,
                f"cannot start '{service_id}': dependencies not available",
                data={"service": entry, "missing_deps": missing,
                      "started": False, "hint": "start dependencies first"},
            )

        entry["status"] = STATE_RUNNING
        entry["started_at"] = datetime.now().isoformat()
        self._save_services(services)
        return ok(
            f"service '{service_id}' started",
            data={
                "service": entry,
                "started": True,
                "side_effects": bool(entry.get("side_effects")),
                "external_side_effect_note": (
                    "declared external side effect is tracked in the state "
                    "machine only; no unrelated system service was touched"),
            },
        )

    def stop_service(self, service_id, confirmed=False, trusted=False,
                     request_id=None):
        service_id = str(service_id or "").strip().lower()
        services = self._services()
        if service_id not in services:
            return reject(STATUS_NOT_CONFIGURED,
                          f"service not registered: {service_id}")
        entry = services[service_id]
        if entry.get("side_effects"):
            allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                            destructive=False)
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"stopping '{service_id}' has external side effects and "
                    f"requires confirmation: {reason}",
                    data={"service": entry, "stopped": False},
                    requires_confirmation=True,
                )
        entry["status"] = STATE_STOPPED
        entry["stopped_at"] = datetime.now().isoformat()
        self._save_services(services)
        return ok(f"service '{service_id}' stopped",
                  data={"service": entry, "stopped": True})

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    @staticmethod
    def _state_status(state):
        return _STATE_STATUS.get(state, STATUS_NOT_CONFIGURED)

    def _deps_closure(self, services, service_id):
        seen = set()
        stack = list(services[service_id].get("deps", []))
        while stack:
            dep = stack.pop()
            if dep in seen or dep not in services:
                continue
            seen.add(dep)
            stack.extend(services[dep].get("deps", []))
        return seen

    def health_rollup(self, service_id):
        service_id = str(service_id or "").strip().lower()
        services = self._services()
        if service_id not in services:
            return reject(STATUS_NOT_CONFIGURED,
                          f"service not registered: {service_id}")
        closure = self._deps_closure(services, service_id)
        deps_status = {}
        worst = self._state_status(services[service_id].get("status"))
        for dep in sorted(closure):
            status = self._state_status(services[dep].get("status"))
            deps_status[dep] = {
                "state": services[dep].get("status"),
                "health": status,
            }
            if _STATUS_RANK.get(status, 6) > _STATUS_RANK.get(worst, 6):
                worst = status
        return ok("health rollup",
                  data={
                      "service": service_id,
                      "state": services[service_id].get("status"),
                      "own_status": self._state_status(services[service_id].get("status")),
                      "deps_status": deps_status,
                      "worst": worst,
                  })

    def degraded_detection(self):
        services = self._services()
        degraded = []
        for sid in sorted(services):
            missing = self._missing_deps(services, services[sid])
            if missing:
                degraded.append({
                    "service": sid,
                    "status": services[sid].get("status"),
                    "missing_deps": missing,
                })
        return ok("degraded detection",
                  data={"degraded": degraded, "degraded_count": len(degraded)})

    # ------------------------------------------------------------------
    # Bottlenecks
    # ------------------------------------------------------------------
    def _reverse_deps(self, services):
        reverse = {sid: [] for sid in services}
        for sid, entry in services.items():
            for dep in entry.get("deps", []):
                if dep in services:
                    reverse.setdefault(dep, []).append(sid)
        return reverse

    def _blocked_count(self, services, reverse, node):
        """Services that transitively depend on ``node`` (all of them are
        blocked when the node is not running)."""
        seen = set()
        stack = list(reverse.get(node, []))
        while stack:
            dep = stack.pop()
            if dep in seen:
                continue
            seen.add(dep)
            stack.extend(reverse.get(dep, []))
        return len(seen)

    def bottleneck_report(self):
        services = self._services()
        reverse = self._reverse_deps(services)
        bottlenecks = []
        for sid in sorted(services):
            if services[sid].get("status") == STATE_RUNNING:
                continue
            blocked = self._blocked_count(services, reverse, sid)
            if blocked == 0:
                continue
            bottlenecks.append({
                "service": sid,
                "status": services[sid].get("status"),
                "missing_or_down": services[sid].get("deps", []),
                "blocked_dependents": blocked,
                "blocked_services": sorted(self._blocked_services(services, reverse, sid)),
            })
        bottlenecks.sort(key=lambda b: (-b["blocked_dependents"], b["service"]))
        return ok("bottleneck report",
                  data={"bottlenecks": bottlenecks,
                        "bottleneck_count": len(bottlenecks)})

    def _blocked_services(self, services, reverse, node):
        seen = set()
        stack = list(reverse.get(node, []))
        while stack:
            dep = stack.pop()
            if dep in seen:
                continue
            seen.add(dep)
            stack.extend(reverse.get(dep, []))
        return seen

    # ------------------------------------------------------------------
    def status_report(self):
        services = self._services()
        rows = []
        for sid in sorted(services):
            entry = services[sid]
            reverse = self._reverse_deps(services)
            rows.append({
                "id": sid,
                "display_name": entry.get("display_name"),
                "version": entry.get("version"),
                "state": entry.get("status"),
                "health": self._state_status(entry.get("status")),
                "deps": entry.get("deps", []),
                "side_effects": bool(entry.get("side_effects")),
                "blocked_dependents": self._blocked_count(services, reverse, sid) if entry.get("status") != STATE_RUNNING else 0,
            })
        return ok("service status report",
                  data={"services": rows, "service_count": len(rows)})

    def status(self):
        services = self._services()
        running = sum(1 for s in services.values() if s.get("status") == STATE_RUNNING)
        return ok("orchestrator status",
                  data={"service_count": len(services),
                        "running": running,
                        "stopped": sum(1 for s in services.values() if s.get("status") == STATE_STOPPED),
                        "degraded": self.degraded_detection()["data"]["degraded_count"],
                        "external_services_untouched": True})


# Module-level singleton (lazy — never touches disk until written).
service_orchestrator = ServiceOrchestrator()

__all__ = [
    "ServiceOrchestrator",
    "service_orchestrator",
    "STATE_STOPPED",
    "STATE_STARTING",
    "STATE_RUNNING",
    "STATE_STOPPING",
    "STATE_DEGRADED",
]