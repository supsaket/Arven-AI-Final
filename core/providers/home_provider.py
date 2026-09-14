"""Home Management (feature 82).

Capabilities:
* ``home_status``          - honest status: local routines + simulated device
  control available; NO external smart-home integration (stated in reason)
* ``home_routine``         - run a named routine (persisted in kv). Routines
  hold ordered device actions (target states). Only SIMULATED devices are
  executed (flagged); non-simulated devices are skipped with a notice.
* ``home_energy_estimate`` - explicit heuristic estimate from user-entered
  device power ratings -> REAL arithmetic, result marked ``estimate: True``.
* ``home_commands``        - the supported command catalogue (routine names +
  static local commands).

Leverages the IoT device registry (``core.providers.iot_provider``) so home
routines can drive the same persisted simulated devices.
"""

from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
)
from core.providers.iot_provider import DeviceRegistry

_ROUTINES_KEY = "home.routines"

_DEFAULT_ROUTINES = {}


class HomeManager:
    """Routine library + energy heuristics over the shared device registry."""

    def __init__(self, kv, registry=None):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("HomeManager requires a core.kv.KeyValueStore")
        self._kv = kv
        self.registry = registry if registry is not None else DeviceRegistry(kv)

    def _load(self):
        return dict(self._kv.get(_ROUTINES_KEY, _DEFAULT_ROUTINES))

    def _save(self, routines):
        self._kv.set(_ROUTINES_KEY, routines)

    def add_routine(self, name, description="", steps=None):
        """``steps`` = ordered list of {device_id, target_state, power_watts, minutes}."""
        routines = self._load()
        routine = {
            "name": str(name),
            "description": str(description),
            "steps": [dict(s) for s in (steps or [])],
        }
        routines[str(name)] = routine
        self._save(routines)
        return dict(routine)

    def get_routine(self, name):
        return self._load().get(str(name))

    def list_routines(self):
        return list(self._load().values())

    def run_routine(self, name):
        routine = self.get_routine(name)
        if routine is None:
            return None
        executed = []
        skipped = []
        for step in routine["steps"]:
            device = self.registry.get(step.get("device_id"))
            if device is None:
                skipped.append({"device_id": step.get("device_id"),
                                "reason": "unknown device"})
                continue
            if not device.get("simulated") and device.get("kind") not in (
                    "simulated", "virtual"):
                skipped.append({"device_id": device["id"],
                                "reason": "non-simulated external device "
                                          "requires a smart-home bridge"})
                continue
            updated = self.registry.set_state(
                device["id"], step.get("target_state", {}))
            executed.append({
                "device_id": device["id"],
                "name": device["name"],
                "target_state": step.get("target_state", {}),
                "simulated": True,
            })
        return {"routine": dict(routine), "executed": executed, "skipped": skipped}

    def energy_estimate(self, items=None):
        """Real kWh arithmetic from user-entered power ratings.

        ``items`` = [{watts, hours}] explicit usage; when provided it fully
        supersedes the device-derived estimate. Otherwise the registered
        devices' power_watts/hours_per_day fields are summed. Always an
        estimate derived from user inputs. Returns (kwh, breakdown).
        """
        breakdown = []
        if items is not None:
            for item in items:
                watts = float(item.get("watts", 0))
                hours = float(item.get("hours", 0))
                breakdown.append({"name": item.get("name", "item"),
                                  "watts": watts, "hours": hours,
                                  "kwh": (watts * hours) / 1000.0})
        else:
            devices = self.registry.all()
            for device in devices:
                watts = device.get("power_watts")
                hours = device.get("hours_per_day")
                if watts is None or hours is None:
                    continue
                kwh = (float(watts) * float(hours)) / 1000.0
                breakdown.append({"device_id": device["id"],
                                  "name": device["name"],
                                  "watts": watts, "hours": hours,
                                  "kwh": kwh})
        total_kwh = round(sum(b["kwh"] for b in breakdown), 4)
        return total_kwh, breakdown


class HomeProvider(Provider):
    name = "home"
    capabilities = (
        "home_status",
        "home_routine",
        "home_energy_estimate",
        "home_commands",
    )
    category = "home"
    requires_network = False
    confirm_capabilities = ()

    def __init__(self, settings=None, kv=None):
        super().__init__(settings)
        kv = kv if kv is not None else KeyValueStore("data/kv_home.json")
        self.registry = DeviceRegistry(kv)
        self.manager = HomeManager(kv, registry=self.registry)
        self.set_status(STATUS_NOT_CONFIGURED, "home manager not probed")

    def check(self):
        routines = len(self.manager.list_routines())
        devices = len(self.registry.all())
        return self.set_status(
            STATUS_AVAILABLE,
            f"home routines ({routines}) + simulated device control ({devices} "
            "device(s)) are available locally; no external smart-home "
            "integration is configured (honest)",
            {"routines": routines, "devices": devices,
             "external_smart_home": False},
        )

    # ------------------------------------------------------------------
    def _cap_home_status(self, **_kw):
        routines = self.manager.list_routines()
        return ok(
            "home management available for local routines + simulated devices",
            {"routines": routines, "devices": self.registry.all(),
             "external_smart_home": False},
        )

    def _cap_home_routine(self, routine_name=None, **_kw):
        if not routine_name:
            return reject(STATUS_FAILED, "home_routine requires routine_name")
        result = self.manager.run_routine(routine_name)
        if result is None:
            return reject(STATUS_FAILED, f"no such routine '{routine_name}'")
        simulated_count = len(result["executed"])
        return ok(
            f"routine '{routine_name}' run on simulated devices "
            f"({simulated_count} executed)",
            result,
        )

    def _cap_home_energy_estimate(self, items=None, **_kw):
        total_kwh, breakdown = self.manager.energy_estimate(items=items)
        return ok(
            "energy estimate computed from user-entered device power ratings "
            "(heuristic, not a live meter)",
            {"total_kwh": total_kwh, "breakdown": breakdown,
             "estimate": True, "live_meter": False},
        )

    def _cap_home_commands(self, **_kw):
        routines = [r["name"] for r in self.manager.list_routines()]
        commands = {
            "run_routine": "home_routine(routine_name=...)  — runs a routine "
                           "on simulated devices",
            "energy_estimate": "home_energy_estimate(items=...) — heuristic kWh",
            "list_recipes": "home_commands()",
            "registered_routines": routines,
        }
        return ok("home command catalogue", {"commands": commands})


def register_home():
    from core.providers.registry import providers_registry
    if not providers_registry.has("home"):
        providers_registry.register(HomeProvider())
    return providers_registry.get("home")


__all__ = ["HomeProvider", "HomeManager", "register_home"]