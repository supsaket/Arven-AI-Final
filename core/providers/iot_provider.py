"""IoT & Home Automation (feature 44).

Capabilities:
* ``iot_status``     - honest state of the device registry + external backend
* ``iot_register``   - add a device to the persisted registry (REAL)
* ``iot_list``       - enumerate devices
* ``iot_set_state``  - update a device's persisted state. Simulated devices
  are updated locally (a REAL simulated device, clearly flagged
  ``simulated: True``). Non-simulated devices without an external bridge
  return NOT_CONFIGURED — we never fake live sensor/actuator VALUES.
* ``iot_remove``     - remove/forget a device (confirm-gated; destructive
  class -> needs confirmed + trusted + approved request_id)

``DeviceRegistry`` is the shared persisted device store (used by home
management too). It lives behind a ``core.kv.KeyValueStore``.
"""

import time

from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
)
from core.kv import KeyValueStore

_DEVICES_KEY = "iot.devices"

# Simulated-device kinds always act on the local store.
_LOCAL_KINDS = {"simulated", "virtual", "software", "routine"}


class DeviceRegistry:
    """Persisted device catalogue: ``{device_id: device}`` in the kv store."""

    def __init__(self, kv):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("DeviceRegistry requires a core.kv.KeyValueStore")
        self._kv = kv

    def _load(self):
        return dict(self._kv.get(_DEVICES_KEY, {}))

    def _save(self, devices):
        self._kv.set(_DEVICES_KEY, devices)

    def all(self):
        return list(self._load().values())

    def get(self, device_id):
        return self._load().get(str(device_id))

    def register(self, device_id=None, kind="simulated", name=None,
                 capabilities=None, state=None, simulated=True,
                 power_watts=None, hours_per_day=None):
        devices = self._load()
        device_id = str(device_id or f"dev_{time.time_ns()}")
        device = {
            "id": device_id,
            "kind": str(kind),
            "name": str(name or device_id),
            "capabilities": list(capabilities or []),
            "state": dict(state or {}),
            "status": "registered",
            "simulated": bool(simulated),
            "registered_at": time.time(),
            "power_watts": power_watts,
            "hours_per_day": hours_per_day,
        }
        devices[device_id] = device
        self._save(devices)
        return dict(device)

    def remove(self, device_id):
        devices = self._load()
        removed = devices.pop(str(device_id), None)
        if removed is not None:
            self._save(devices)
        return removed is not None

    def set_state(self, device_id, state):
        devices = self._load()
        device = devices.get(str(device_id))
        if device is None:
            return None
        merged = dict(device.get("state", {}))
        merged.update(state or {})
        device["state"] = merged
        device["status"] = "active"
        devices[device_id] = device
        self._save(devices)
        return dict(device)


class IoTProvider(Provider):
    name = "iot"
    capabilities = (
        "iot_status",
        "iot_register",
        "iot_set_state",
        "iot_list",
        "iot_remove",
    )
    category = "devices"
    requires_network = False
    confirm_capabilities = ("iot_remove",)

    def __init__(self, settings=None, kv=None):
        super().__init__(settings)
        self.registry = DeviceRegistry(kv if kv is not None else KeyValueStore("data/kv_iot.json"))
        self.set_status(STATUS_NOT_CONFIGURED, "iot registry not probed")

    def check(self):
        count = len(self.registry.all())
        return self.set_status(
            STATUS_AVAILABLE,
            f"device registry operational ({count} device(s)); "
            "no external smart-home bridge configured — live sensors/actuators "
            "over the network are NOT_CONFIGURED",
            {"devices": count, "external_bridge": False},
        )

    # ------------------------------------------------------------------
    def _cap_iot_status(self, **_kw):
        devices = self.registry.all()
        return ok(
            "iot device registry operational (simulated devices update "
            "real persisted state)",
            {
                "devices": devices,
                "count": len(devices),
                "simulated": sum(1 for d in devices if d.get("simulated")),
                "external_bridge": False,
                "live_sensor_values": False,
            },
        )

    def _cap_iot_register(self, device_id=None, kind="simulated", name=None,
                          capabilities=None, state=None, simulated=True,
                          power_watts=None, hours_per_day=None, **_kw):
        device = self.registry.register(
            device_id=device_id, kind=kind, name=name,
            capabilities=capabilities, state=state, simulated=simulated,
            power_watts=power_watts, hours_per_day=hours_per_day)
        return ok("device registered", {"device": device})

    def _cap_iot_list(self, **_kw):
        return ok("devices listed", {"devices": self.registry.all()})

    def _cap_iot_set_state(self, device_id=None, state=None, **_kw):
        if not device_id:
            return reject(STATUS_FAILED, "iot_set_state requires device_id")
        device = self.registry.get(device_id)
        if device is None:
            return reject(STATUS_FAILED, f"no such device '{device_id}'")
        if not device.get("simulated") and not device.get("kind") in _LOCAL_KINDS:
            return reject(
                STATUS_NOT_CONFIGURED,
                f"device '{device_id}' is a non-simulated external device and "
                "no smart-home bridge/backend is configured — cannot actuate",
                {"live_actuation": False, "requires_backend": True},
            )
        updated = self.registry.set_state(device_id, state or {})
        return ok(
            "state updated on simulated device (persisted locally)",
            {"device": updated, "simulated": True},
        )

    def _cap_iot_remove(self, device_id=None, **_kw):
        if not device_id:
            return reject(STATUS_FAILED, "iot_remove requires device_id")
        removed = self.registry.remove(device_id)
        if not removed:
            return reject(STATUS_FAILED, f"no such device '{device_id}'")
        return ok("device removed from registry", {"device_id": device_id})


def register_iot():
    from core.providers.registry import providers_registry
    if not providers_registry.has("iot"):
        providers_registry.register(IoTProvider())
    return providers_registry.get("iot")


__all__ = ["IoTProvider", "DeviceRegistry", "register_iot"]