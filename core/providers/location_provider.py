"""Location Services (feature 84).

Capabilities:
* ``location_status`` - honest status: a manual location store (kv) works;
  live GPS / geocoding backend detection.
* ``location_set``    - store a user-provided place (REAL, persisted).
* ``location_get``    - read a stored place. REQUIRES_PERMISSION unless
  ``permissions.location_access == 'granted'``.
* ``location_geocode``- offline -> OFFLINE; no geocoding backend ->
  NOT_CONFIGURED honest.
* ``distance``        - REAL haversine math (km / miles) between two
  coordinate pairs — no network involved.
"""

import math
import time

from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    probe_network,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_PERMISSION,
)

_PLACES_KEY = "location.places"

_KM_PER_MILE = 1.609344


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres (REAL arithmetic)."""
    radius = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


def _check_coord(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


class LocationStore:
    """Manual, persisted place store over a shared kv store."""

    def __init__(self, kv):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("LocationStore requires a core.kv.KeyValueStore")
        self._kv = kv

    def set_place(self, name, lat, lon, label=None):
        places = dict(self._kv.get(_PLACES_KEY, {}))
        place = {
            "name": str(name),
            "lat": float(lat),
            "lon": float(lon),
            "label": str(label or name),
            "updated_at": time.time(),
        }
        places[str(name)] = place
        self._kv.set(_PLACES_KEY, places)
        return place

    def get_place(self, name):
        return self._kv.get(_PLACES_KEY, {}).get(str(name))

    def list_places(self):
        return list(self._kv.get(_PLACES_KEY, {}).values())


class LocationProvider(Provider):
    name = "location"
    capabilities = (
        "location_status",
        "location_set",
        "location_get",
        "location_geocode",
        "distance",
    )
    category = "location"
    requires_network = False
    confirm_capabilities = ()

    def __init__(self, settings=None, kv=None, permissions=None,
                 network_probe=None):
        super().__init__(settings)
        self.store = LocationStore(
            kv if kv is not None else KeyValueStore("data/kv_location.json"))
        self._permissions_override = permissions if permissions is not None else {}
        self._network_probe = network_probe or probe_network
        self.set_status(STATUS_NOT_CONFIGURED, "location store not probed")

    def _permission_granted(self):
        permissions = dict(self._permissions_override)
        configured = self.settings.get("PERMISSIONS", {})
        if isinstance(configured, dict):
            permissions.update(configured)
        return permissions.get("location_access") == "granted"

    def check(self):
        places = len(self.store.list_places())
        return self.set_status(
            STATUS_AVAILABLE,
            f"manual location store operational ({places} place(s)); no "
            "geocoding/live-GPS backend configured — geocode is honest "
            "NOT_CONFIGURED/OFFLINE",
            {"places": places, "geocode_backend": False,
             "gps_backend": False},
        )

    # ------------------------------------------------------------------
    def _cap_location_status(self, **_kw):
        places = self.store.list_places()
        return ok(
            "manual location store operational; geocoding backend absent",
            {"places": places, "geocode_backend": False, "gps_backend": False,
             "location_access": "granted" if self._permission_granted()
             else "not_granted"},
        )

    def _cap_location_set(self, name=None, lat=None, lon=None, label=None,
                          **_kw):
        if not name:
            return reject(STATUS_FAILED, "location_set requires a name")
        coord = _check_coord(lat, lon)
        if coord is None:
            return reject(STATUS_FAILED,
                          f"invalid coordinates lat={lat} lon={lon}")
        place = self.store.set_place(name, coord[0], coord[1], label=label)
        return ok("location stored", {"place": place, "source": "user"})

    def _cap_location_get(self, name=None, **_kw):
        if not self._permission_granted():
            return reject(
                STATUS_REQUIRES_PERMISSION,
                "location access not granted — refuse to read stored "
                "locations",
                {"permission": "location_access"},
            )
        if not name:
            return reject(STATUS_FAILED, "location_get requires a name")
        place = self.store.get_place(name)
        if place is None:
            return reject(STATUS_FAILED, f"no such place '{name}'")
        return ok("location read", {"place": place})

    def _cap_location_geocode(self, query=None, **_kw):
        if not self._network_probe():
            return reject(STATUS_OFFLINE,
                          "geocoding requires network access (offline)",
                          {"network": False})
        return reject(
            STATUS_NOT_CONFIGURED,
            "no geocoding backend configured (e.g. a local gazetteer or a "
            "configured provider) — cannot resolve addresses",
            {"geocode_backend": False},
        )

    def _cap_distance(self, lat1=None, lon1=None, lat2=None, lon2=None,
                      unit="km", **_kw):
        a = _check_coord(lat1, lon1)
        b = _check_coord(lat2, lon2)
        if a is None or b is None:
            return reject(STATUS_FAILED,
                          "distance requires four valid lat/lon coordinates")
        km = haversine_km(a[0], a[1], b[0], b[1])
        miles = km / _KM_PER_MILE
        if str(unit).lower() in ("miles", "mile", "mi"):
            value = miles
        else:
            value = km
        return ok("distance computed (haversine)",
                  {"km": round(km, 4), "miles": round(miles, 4),
                   "unit": str(unit).lower(), "distance": round(value, 4),
                   "estimate": False})


def register_location():
    from core.providers.registry import providers_registry
    if not providers_registry.has("location"):
        providers_registry.register(LocationProvider())
    return providers_registry.get("location")


__all__ = ["LocationProvider", "LocationStore", "haversine_km",
           "register_location"]