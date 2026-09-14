"""Travel Planning (feature 80).

Capabilities:
* ``travel_plan``      - REAL day-by-day itinerary builder from user-supplied
  destinations, dates, budget and pace. Transport times are heuristic
  durations (haversine when coordinates are given, sensible defaults
  otherwise); budget/accommodation totals are real arithmetic over user
  inputs. The whole plan is marked ``estimate: True`` and persisted in kv.
* ``travel_itinerary`` - load a saved plan.
* ``travel_book``      - confirm-gated booking. Without an external travel
  provider it returns NOT_CONFIGURED honest and NEVER fakes a booking.

``travel_book`` is a confirm capability whose action is classified medium
risk by the shared safety engine — this provider therefore ships a strict
``execute()`` that requires an explicit confirmed + approved request_id.
"""

import math
import time

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
)

_TRIPS_KEY = "travel.trips"

_SPEED_KMH = {"car": 60.0, "train": 80.0, "flight": 500.0, "bus": 45.0}
_PACE_DAILY = {"relaxed": 1, "moderate": 2, "fast": 3}
_PACE_TIME = {"car": 90, "train": 120, "flight": 150, "bus": 75}


def _haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


class TripPlanner:
    """Persisted itinerary plans over a shared kv store."""

    def __init__(self, kv):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("TripPlanner requires a core.kv.KeyValueStore")
        self._kv = kv

    def save(self, trip):
        trips = dict(self._kv.get(_TRIPS_KEY, {}))
        trips[trip["trip_id"]] = trip
        self._kv.set(_TRIPS_KEY, trips)
        return trip

    def load(self, trip_id):
        return self._kv.get(_TRIPS_KEY, {}).get(str(trip_id))

    def list_trips(self):
        return list(self._kv.get(_TRIPS_KEY, {}).values())

    def build(self, destinations, dates=None, budget=None, pace="moderate",
              transport="car", trip_id=None):
        destinations = list(destinations or [])
        if not destinations:
            raise ValueError("at least one destination is required")
        days = len(dates) if dates else len(destinations)
        pace = str(pace or "moderate").lower()
        daily = _PACE_DAILY.get(pace, 2)
        transport = str(transport or "car").lower()
        speed = _SPEED_KMH.get(transport, 60.0)

        schedule = []
        for day_index in range(days):
            destination = destinations[day_index % len(destinations)]
            if isinstance(destination, dict):
                name = destination.get("name", f"stop {day_index + 1}")
                coord = (destination.get("lat"), destination.get("lon"))
            else:
                name = str(destination)
                coord = (None, None)
            date = (dates[day_index] if dates and day_index < len(dates)
                    else f"day-{day_index + 1}")
            entry = {"day": day_index + 1, "date": date, "destination": name}
            if day_index > 0:
                prev = schedule[-1]["coord"]
                if (prev and prev[0] is not None and coord[0] is not None
                        and prev[1] is not None and coord[1] is not None):
                    km = _haversine_km(prev[0], prev[1], coord[0], coord[1])
                    minutes = (km / speed) * 60.0
                    entry["leg_km"] = round(km, 1)
                    entry["leg_duration_min"] = round(minutes, 1)
                else:
                    entry["leg_km"] = None
                    entry["leg_duration_min"] = _PACE_TIME.get(transport, 90)
            entry["coord"] = list(coord) if coord[0] is not None else None
            entry["activities"] = max(1, daily)
            schedule.append(entry)

        # drop the internal coord field from serialised output but keep on the
        # entries for arithmetic above (coords are user-provided).
        for entry in schedule:
            entry.pop("coord", None)

        nights = max(days - 1, 1)
        budget = float(budget) if budget is not None else 1000.0
        accommodation = round(budget * 0.6 / nights, 2)
        transport_total = round(budget * 0.25, 2)
        meals = round(budget * 0.15, 2)
        totals = {
            "budget": budget,
            "nights": nights,
            "accommodation_per_night": accommodation,
            "accommodation_total": round(accommodation * nights, 2),
            "transport_total": transport_total,
            "meals_total": meals,
            "estimated_total": round(
                accommodation * nights + transport_total + meals, 2),
        }
        plan = {
            "trip_id": str(trip_id or f"trip_{time.time_ns()}"),
            "destinations": destinations,
            "dates": dates,
            "pace": pace,
            "transport": transport,
            "days": days,
            "schedule": schedule,
            "totals": totals,
            "estimate": True,
            "built_at": time.time(),
        }
        return plan

    def book(self, trip_id):
        trip = self.load(trip_id)
        if trip is None:
            return None
        return trip


class TravelProvider(Provider):
    name = "travel"
    capabilities = (
        "travel_plan",
        "travel_book",
        "travel_itinerary",
    )
    category = "travel"
    requires_network = False
    confirm_capabilities = ("travel_book",)

    def __init__(self, settings=None, kv=None):
        super().__init__(settings)
        self.planner = TripPlanner(
            kv if kv is not None else KeyValueStore("data/kv_travel.json"))
        self.set_status(STATUS_NOT_CONFIGURED, "travel planner not probed")

    def check(self):
        return self.set_status(
            STATUS_AVAILABLE,
            "trip planning (local itinerary builder) available; no external "
            "booking provider configured — travel_book is NOT_CONFIGURED",
            {"booking_backend": False},
        )

    # ------------------------------------------------------------------
    def execute(self, capability, **kwargs):
        """Strict gate for ``travel_book`` (medium-classified risk)."""
        try:
            target = self.describe_capability(capability)
            method = getattr(self, f"_cap_{target.replace('-', '_')}", None)
            if self.needing_network():
                return self._honest(STATUS_OFFLINE,
                                    f"{self.name} requires network access")
            if method is None:
                return self._honest(
                    STATUS_NOT_CONFIGURED,
                    f"{self.name} does not implement capability '{capability}'")
            if target in self.confirm_capabilities:
                confirmed = bool(kwargs.get("confirmed", False))
                trusted = bool(kwargs.get("trusted", False))
                request_id = kwargs.get("request_id")
                allowed, _reason = CONFIRMATION.gate(
                    f"{self.name}.{target}",
                    confirmed=confirmed,
                    trusted=trusted,
                    request_id=request_id,
                )
                approved = bool(
                    allowed and confirmed and request_id
                    and CONFIRMATION.is_pending_ok(request_id))
                if not approved:
                    payload = self._honest(
                        STATUS_REQUIRES_AUTH, f"{target} requires confirmation")
                    payload["requires_confirmation"] = True
                    return payload
                kwargs["_cleared"] = True
                kwargs.pop("confirmed", None)
                kwargs.pop("trusted", None)
                kwargs.pop("request_id", None)
            return method(**kwargs)
        except Exception as exc:
            return self._honest(STATUS_FAILED, f"{self.name} error: {exc}")

    # ------------------------------------------------------------------
    def _cap_travel_plan(self, destinations=None, dates=None, budget=None,
                         pace="moderate", transport="car", trip_id=None,
                         **_kw):
        try:
            plan = self.planner.build(
                destinations=destinations, dates=dates, budget=budget,
                pace=pace, transport=transport, trip_id=trip_id)
        except ValueError as exc:
            return reject(STATUS_FAILED, str(exc))
        self.planner.save(plan)
        return ok("travel plan built (heuristic, estimate)",
                  {"estimate": True, "plan": plan})

    def _cap_travel_itinerary(self, trip_id=None, **_kw):
        if not trip_id:
            return reject(STATUS_FAILED, "travel_itinerary requires trip_id")
        trip = self.planner.load(trip_id)
        if trip is None:
            return reject(STATUS_FAILED, f"no such trip '{trip_id}'")
        return ok("itinerary loaded", {"itinerary": trip})

    def _cap_travel_book(self, trip_id=None, booking=None, **_kw):
        trip = self.planner.load(trip_id) if trip_id else None
        if not trip_id or trip is None:
            return reject(STATUS_FAILED,
                          "travel_book requires a saved trip_id")
        return reject(
            STATUS_NOT_CONFIGURED,
            "no external travel booking provider configured — the booking was "
            "NOT placed (honest)",
            {"trip_id": trip_id, "booked": False,
             "requires_confirmation": True},
        )


def register_travel():
    from core.providers.registry import providers_registry
    if not providers_registry.has("travel"):
        providers_registry.register(TravelProvider())
    return providers_registry.get("travel")


__all__ = ["TravelProvider", "TripPlanner", "register_travel"]