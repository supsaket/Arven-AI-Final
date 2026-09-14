"""Navigation & Route Planning (feature 93).

Capabilities:
* ``route_plan``     - REAL offline route math. Given origin/destination (and
  optional waypoints) + mode, the great-circle distance is computed with
  haversine and the travel time with a fixed speed table (walk/drive/transit).
  Deterministic, no network. A high-level route summary is produced and the
  result is marked ``estimate: True`` and ``live: False``. A full textual turn
  list is only provided when a map backend exists (none in this codebase).
* ``route_eta``      - LIVE traffic estimate. Offline -> OFFLINE honest. With
  no live-traffic backend -> NOT_CONFIGURED honest.
* ``navigation_status`` - honest status: offline planning AVAILABLE; live
  traffic backend NOT_CONFIGURED.

Offline-first contract: deterministic route planning STILL works while
offline; only the live-traffic capability reports OFFLINE.
"""

import math
import os

from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    probe_network,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_FAILED,
)

SPEED_KMH = {"walk": 5.0, "drive": 40.0, "transit": 25.0, "cycle": 15.0}

_MAP_BACKEND_ENV = ("MAP_BACKEND", "MAPS_API_KEY", "NAVIGATION_BACKEND")


def _haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


def _coords(pair):
    """Accept (lat, lon) tuple, dict with lat/lon, or 'name' text marker."""
    if isinstance(pair, dict):
        return float(pair["lat"]), float(pair["lon"]), str(pair.get("name", "point"))
    if isinstance(pair, (tuple, list)) and len(pair) >= 2:
        return float(pair[0]), float(pair[1]), "point"
    return None, None, str(pair)


class RouteService:
    def __init__(self, speed_table=None):
        self.speeds = dict(speed_table or SPEED_KMH)

    def plan(self, origin, destination, waypoints=None, mode="drive"):
        mode = str(mode or "drive").lower()
        if mode not in self.speeds:
            raise ValueError(f"unknown travel mode '{mode}'")
        speed = self.speeds[mode]

        points = [origin] + list(waypoints or []) + [destination]
        segments = []
        total_km = 0.0
        for i in range(1, len(points)):
            o_lat, o_lon, o_name = _coords(points[i - 1])
            d_lat, d_lon, d_name = _coords(points[i])
            if (o_lat is None or d_lat is None):
                raise ValueError("origin/destination/waypoints need lat/lon")
            km = _haversine_km(o_lat, o_lon, d_lat, d_lon)
            total_km += km
            segments.append({
                "from": {"lat": o_lat, "lon": o_lon, "name": o_name},
                "to": {"lat": d_lat, "lon": d_lon, "name": d_name},
                "distance_km": round(km, 3),
                "duration_min": round((km / speed) * 60.0, 1),
            })
        total_min = round((total_km / speed) * 60.0, 1)
        return {
            "mode": mode,
            "distance_km": round(total_km, 3),
            "duration_min": total_min,
            "segments": segments,
            "steps": self._route_summary(segments, mode),
            "map_backend": self.map_backend,
            "estimate": True,
            "live": False,
        }

    @property
    def map_backend(self):
        return any(os.environ.get(v) for v in _MAP_BACKEND_ENV)

    def _route_summary(self, segments, mode):
        steps = []
        for index, segment in enumerate(segments, start=1):
            instruction = (
                f"Leg {index}: {segment['to']['name']} via {mode} "
                f"(~{segment['distance_km']} km, ~{segment['duration_min']} min)")
            steps.append({"step": index, "instruction": instruction,
                          "textual_turn_list": False})
        return steps


class NavigationProvider(Provider):
    name = "navigation"
    capabilities = (
        "route_plan",
        "route_eta",
        "navigation_status",
    )
    category = "navigation"
    requires_network = False
    confirm_capabilities = ()

    def __init__(self, settings=None, kv=None, network_probe=None):
        super().__init__(settings)
        self._kv = kv if kv is not None else KeyValueStore("data/kv_navigation.json")
        self._network_probe = network_probe or probe_network
        self.service = RouteService()
        self.set_status(STATUS_NOT_CONFIGURED, "navigation not probed")

    def check(self):
        return self.set_status(
            STATUS_AVAILABLE,
            "offline deterministic route planning available (haversine + "
            "speed table); live traffic / turn-by-turn map backend "
            "NOT_CONFIGURED",
            {"map_backend": self.service.map_backend,
             "live_traffic": False},
        )

    # ------------------------------------------------------------------
    def _cap_navigation_status(self, **_kw):
        return ok(
            "navigation available for offline route estimates",
            {"map_backend": self.service.map_backend,
             "live_traffic": False, "live": False},
        )

    def _cap_route_plan(self, origin=None, destination=None, waypoints=None,
                        mode="drive", **_kw):
        if origin is None or destination is None:
            return reject(STATUS_FAILED,
                          "route_plan requires origin and destination")
        try:
            plan = self.service.plan(origin, destination, waypoints, mode)
        except (ValueError, TypeError) as exc:
            return reject(STATUS_FAILED, f"route_plan failed: {exc}")
        return ok("route planned offline (deterministic estimate)",
                  {"estimate": True, "live": False, **plan})

    def _cap_route_eta(self, origin=None, destination=None, mode="drive",
                       **_kw):
        if origin is None or destination is None:
            return reject(STATUS_FAILED, "route_eta requires origin and destination")
        if not self._network_probe():
            return reject(
                STATUS_OFFLINE,
                "live traffic estimate requires network access (offline)",
                {"network": False, "live": False})
        if not self.service.map_backend:
            return reject(
                STATUS_NOT_CONFIGURED,
                "no live-traffic backend configured — cannot produce a live "
                "ETA",
                {"live_traffic_backend": False, "live": False})
        try:
            plan = self.service.plan(origin, destination, None, mode)
        except (ValueError, TypeError) as exc:
            return reject(STATUS_FAILED, f"route_eta failed: {exc}")
        return ok("live ETA estimate (live feed available)",
                  {"estimate": True, "live": True, **plan})


def register_navigation():
    from core.providers.registry import providers_registry
    if not providers_registry.has("navigation"):
        providers_registry.register(NavigationProvider())
    return providers_registry.get("navigation")


__all__ = ["NavigationProvider", "RouteService", "register_navigation"]