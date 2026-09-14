"""Vehicle Management (feature 83).

Capabilities:
* ``vehicle_status``          - honest status: local vehicle store available;
  live OBD/telemetry is NOT_CONFIGURED.
* ``vehicle_registration``    - store make/model/reg + registration renewal
  date (user-entered, persisted; ``source: "user"``).
* ``vehicle_log_maintenance`` - append a maintenance log entry (odometer,
  service type, cost, date; ``source: "user"``).
* ``vehicle_reminders``       - computed next-service reminders via REAL
  datetime arithmetic (odometer interval + month interval). All values are
  user-entered; the result is marked ``source: "user"``.

No live telemetry is ever claimed — every figure comes from the user.
"""

import calendar
import time
from datetime import date, datetime

from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
)

_VEHICLES_KEY = "vehicle.vehicles"


def _parse_date(value, fallback=None):
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return fallback


def add_months(value, months):
    """Add whole months to a date with month-length clamping (REAL math)."""
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class VehicleStore:
    """Persisted vehicle + maintenance log over a shared kv store."""

    def __init__(self, kv):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("VehicleStore requires a core.kv.KeyValueStore")
        self._kv = kv

    def _load(self):
        return dict(self._kv.get(_VEHICLES_KEY, {}))

    def _save(self, vehicles):
        self._kv.set(_VEHICLES_KEY, vehicles)

    def upsert_vehicle(self, reg, make, model, renewal_date=None,
                       last_service_date=None, last_odometer=None):
        vehicles = self._load()
        vehicle = vehicles.get(str(reg), {
            "reg": str(reg), "make": str(make or ""), "model": str(model or ""),
            "maintenance": [], "source": "user",
        })
        vehicle["reg"] = str(reg)
        if make:
            vehicle["make"] = str(make)
        if model:
            vehicle["model"] = str(model)
        if renewal_date:
            vehicle["registration_renewal"] = str(renewal_date)
        if last_service_date:
            vehicle["last_service_date"] = str(last_service_date)
        if last_odometer is not None:
            vehicle["last_odometer"] = float(last_odometer)
        vehicles[str(reg)] = vehicle
        self._save(vehicles)
        return dict(vehicle)

    def get_vehicle(self, reg):
        return self._load().get(str(reg))

    def log_maintenance(self, reg, make, model, odometer=None, service_type=None,
                        cost=None, service_date=None):
        vehicle = self.upsert_vehicle(reg, make, model)
        entry = {
            "odometer": float(odometer) if odometer is not None else None,
            "service_type": str(service_type or "service"),
            "cost": float(cost) if cost is not None else None,
            "date": str(service_date or date.today().isoformat()),
            "source": "user",
            "logged_at": time.time(),
        }
        vehicle.setdefault("maintenance", []).append(entry)
        vehicle["last_service_date"] = entry["date"]
        if entry["odometer"] is not None:
            vehicle["last_odometer"] = entry["odometer"]
        vehicles = self._load()
        vehicles[str(reg)] = vehicle
        self._save(vehicles)
        return dict(vehicle)


class VehicleProvider(Provider):
    name = "vehicle"
    capabilities = (
        "vehicle_status",
        "vehicle_log_maintenance",
        "vehicle_reminders",
        "vehicle_registration",
    )
    category = "vehicles"
    requires_network = False
    confirm_capabilities = ()

    def __init__(self, settings=None, kv=None):
        super().__init__(settings)
        self.store = VehicleStore(
            kv if kv is not None else KeyValueStore("data/kv_vehicle.json"))
        self.set_status(STATUS_NOT_CONFIGURED, "vehicle store not probed")

    def check(self):
        count = len(self.store._load())
        return self.set_status(
            STATUS_AVAILABLE,
            f"vehicle store operational ({count} vehicle(s)); live OBD/"
            "telemetry connection is NOT_CONFIGURED — all values are "
            "user-entered",
            {"vehicles": count, "live_obd": False},
        )

    # ------------------------------------------------------------------
    def _cap_vehicle_status(self, **_kw):
        vehicles = self.store._load()
        return ok(
            "vehicle store available (user-entered data only)",
            {"vehicles": list(vehicles.values()), "live_obd": False,
             "source": "user"},
        )

    def _cap_vehicle_registration(self, reg=None, make=None, model=None,
                                  renewal_date=None, **_kw):
        if not reg:
            return reject(STATUS_FAILED, "vehicle_registration requires reg")
        vehicle = self.store.upsert_vehicle(
            reg, make, model, renewal_date=renewal_date)
        return ok("vehicle registration recorded",
                  {"vehicle": vehicle, "source": "user"})

    def _cap_vehicle_log_maintenance(self, reg=None, make=None, model=None,
                                     odometer=None, service_type=None,
                                     cost=None, service_date=None, **_kw):
        if not reg:
            return reject(STATUS_FAILED, "vehicle_log_maintenance requires reg")
        vehicle = self.store.log_maintenance(
            reg, make, model, odometer=odometer, service_type=service_type,
            cost=cost, service_date=service_date)
        return ok("maintenance entry logged (user-entered)",
                  {"vehicle": vehicle, "source": "user"})

    def _cap_vehicle_reminders(self, reg=None, interval_km=None,
                               interval_months=None, as_of=None, **_kw):
        if not reg:
            return reject(STATUS_FAILED, "vehicle_reminders requires reg")
        vehicle = self.store.get_vehicle(reg)
        if vehicle is None:
            return reject(STATUS_FAILED, f"no such vehicle '{reg}'")

        as_of_date = _parse_date(as_of, date.today())
        last_service_date = _parse_date(
            vehicle.get("last_service_date"), as_of_date)
        last_odometer = vehicle.get("last_odometer")
        interval_km = float(interval_km) if interval_km is not None else None
        interval_months = float(interval_months) if interval_months is not None\
            else None

        due_date = None
        due_km = None
        next_service_date = None
        next_service_km = None
        if interval_months:
            next_service_date = add_months(last_service_date, int(interval_months))
            due_date = next_service_date.isoformat()
        if interval_km is not None and last_odometer is not None:
            due_km = float(last_odometer) + interval_km
            next_service_km = due_km

        reminders = []
        if due_date:
            days_until = (next_service_date - as_of_date).days
            reminders.append({
                "kind": "time", "label": "next service by date",
                "value": due_date, "days_until": days_until,
                "due_soon": 0 <= days_until <= 30,
            })
        if next_service_km is not None:
            reminders.append({
                "kind": "odometer", "label": "next service by odometer",
                "value": next_service_km, "source": "user",
            })
        if vehicle.get("registration_renewal"):
            renewal = _parse_date(vehicle["registration_renewal"])
            if renewal and as_of_date:
                days_until = (renewal - as_of_date).days
                reminders.append({
                    "kind": "registration", "label": "registration renewal",
                    "value": renewal.isoformat(), "days_until": days_until,
                    "due_soon": 0 <= days_until <= 30,
                })

        return ok("maintenance/registration reminders computed (datetime math "
                  "over user-entered values)",
                  {"vehicle": {"reg": reg, "make": vehicle.get("make"),
                               "model": vehicle.get("model")},
                   "due_date": due_date, "due_km": due_km,
                   "reminders": reminders, "source": "user",
                   "estimate": True})


def register_vehicle():
    from core.providers.registry import providers_registry
    if not providers_registry.has("vehicle"):
        providers_registry.register(VehicleProvider())
    return providers_registry.get("vehicle")


__all__ = ["VehicleProvider", "VehicleStore", "add_months",
           "register_vehicle"]