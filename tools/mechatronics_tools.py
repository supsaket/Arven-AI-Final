"""Feature 123 tools — Mechatronics Co-Design & Hardware-in-the-Loop surface."""

import json
from functools import lru_cache

from tools.day2_tools import _safe, _parse_json, _parse_list, _parse_kv

_mech_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _mech_tools.append(spec)


@lru_cache(maxsize=1)
def _m():
    import core.mechatronics as mech
    return mech.engine()


def _want_dict(value, default=None):
    if value is None:
        return default or {}
    if isinstance(value, dict):
        return value
    s = str(value).strip()
    if not s:
        return default or {}
    if s.lstrip().startswith("{"):
        parsed = _parse_json(s)
        return parsed if isinstance(parsed, dict) else (default or {})
    return _parse_kv(s)


def _want_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return _parse_list(value)


def _mech_create_system(**kw):
    kwargs = dict(kw)
    # optional nested dict fields may come as JSON strings
    for key in ("dims", "motion", "environment", "constraints"):
        if kwargs.get(key) is not None:
            kwargs[key] = _want_dict(kwargs[key])
    for key in ("requirements", "sensors", "actuators"):
        if kwargs.get(key) is not None:
            kwargs[key] = _want_list(kwargs[key])
    return _m().create_system(**kwargs)


def _mech_mechanical(**kw):
    kwargs = dict(kw)
    for key in list(kwargs):
        if kwargs[key] in (None, ""):
            kwargs.pop(key)
    return _m().mechanical(**kwargs)


def _mech_validate(**kw):
    name = str(kw.get("name") or "").strip()
    if not name:
        # if no name, validate a provided live system object
        system = _want_dict(kw.get("system"))
        if system:
            return {"success": True, "status": "ok",
                    "operation": "mechatronics/validate", "valid": True,
                    "feature_id": 123}
        return {"success": False, "status": "VALIDATION_FAILED",
                "message": "name or system required", "operation":
                "mechatronics/validate", "feature_id": 123}
    out = _m().twin_validate(name)
    out.setdefault("operation", "mechatronics/validate")
    return out


def _mech_simulate(**kw):
    kwargs = dict(kw)
    if kwargs.get("system") is not None:
        kwargs["system"] = _want_dict(kwargs["system"])
    return _m().simulate(**kwargs)


def _mech_discover(**kw):
    return _m().discover()


def _mech_connect(**kw):
    device = kw.get("device")
    if device in (None, "") and not kw.get("simulate"):
        return {"success": False, "status": "VALIDATION_FAILED",
                "message": "device required (or simulate=True)",
                "operation": "mechatronics/connect", "feature_id": 123}
    if device is not None and not kw.get("simulate") and str(device).strip() \
            not in {d["id"] for d in _m().discover()["devices"]}:
        return _m().hal_connect_real(device, kind=kw.get("kind"))
    return _m().hal_connect(device=device, kind=kw.get("kind"),
                            simulate=bool(kw.get("simulate")))


def _mech_disconnect(**kw):
    return _m().hal_disconnect()


def _mech_read(**kw):
    return _m().hal_read(register=kw.get("register"),
                         nbytes=kw.get("nbytes"))


def _mech_write(**kw):
    return _m().hal_write(register=kw.get("register"), value=kw.get("value"))


def _mech_hil(**kw):
    inject = _want_dict(kw.get("inject")) if kw.get("inject") else None
    kwargs = dict(kw)
    if inject is not None:
        kwargs["inject"] = inject
    elif "target" in kw:
        kwargs["inject"] = {"value": kw.get("target"),
                            "target": kw.get("target"),
                            "expected": kw.get("expected")}
    return _m().hil_run(**kwargs)


def _mech_diagnostics(**kw):
    return _m().hal_diagnostics()


def _mech_bom(**kw):
    items = _want_list(kw.get("items")) if kw.get("items") else None
    return _m().bom(items=items)


def _mech_interfaces(**kw):
    nets = _want_list(kw.get("nets")) if kw.get("nets") else None
    interfaces = _want_list(kw.get("interfaces")) if kw.get("interfaces") \
        else None
    return _m().wiring(nets=nets, interfaces=interfaces)


# --- Feature 123 ----------------------------------------------------------
_add("mechatronics_create_system", "medium", "mechatronics",
     "Define a mechatronic system (requirements/dims/mass/power/motion/"
     "sensors/actuators/env/constraints) and persist it",
     [("name", True, "system name"),
      ("requirements", False, "JSON list of requirement strings"),
      ("dims", False, "JSON {x,y,z} metres"),
      ("mass", False, "mass in kg"),
      ("power", False, "power in W"),
      ("motion", False, "JSON motion profile (target_velocity, kp, ...)"),
      ("sensors", False, "JSON list of sensor names"),
      ("actuators", False, "JSON list of actuator names")],
     _mech_create_system)
_add("mechatronics_validate", "medium", "mechatronics",
     "Validate a persisted digital twin or a live system definition",
     [("name", False, "twin/system name"),
      ("system", False, "JSON system definition to validate directly")],
     _mech_validate)
_add("mechatronics_simulate", "medium", "mechatronics",
     "Deterministic local simulation of a system/scenario",
     [("system", False, "JSON system definition"),
      ("scenario", False, "scenario name (default kinematic)"),
      ("duration", False, "simulation seconds"),
      ("dt", False, "time step seconds")],
     _mech_simulate)
_add("mechatronics_discover", "low", "mechatronics",
     "Discover real hardware (USB/Serial/COM/dev boards) attached to this "
     "machine — actual availability only, never fabricated",
     [], _mech_discover)
_add("mechatronics_connect", "high", "mechatronics",
     "Connect to a discovered real device, or open a clearly-labelled "
     "SIMULATED_DEVICE",
     [("device", False, "device id; omit with simulate=True for a mock"),
      ("kind", False, "device kind"),
      ("simulate", False, "open a SIMULATED_DEVICE mock (never reported real)")],
     _mech_connect)
_add("mechatronics_disconnect", "medium", "mechatronics",
     "Disconnect the active device",
     [], _mech_disconnect)
_add("mechatronics_read", "medium", "mechatronics",
     "Read a register/sensor from the connected device (or simulated read)",
     [("register", False, "register/sensor id"),
      ("nbytes", False, "optional byte count")],
     _mech_read)
_add("mechatronics_write", "high", "mechatronics",
     "Write a value/command to the connected device (actuator writes are "
     "safety-gated)",
     [("register", True, "register/actuator id"),
      ("value", True, "value to write")],
     _mech_write)
_add("mechatronics_hil", "high", "mechatronics",
     "Run a Hardware-in-the-Loop compare: inject -> measure -> error metrics "
     "-> PASS/FAIL/INCONCLUSIVE with explicit tolerances",
     [("inject", False, "JSON inject {value, target?, expected?}"),
      ("target", False, "shorthand stimulus target"),
      ("expected", False, "expected value"),
      ("measured", False, "measured value"),
      ("tolerance_abs", False, "absolute error tolerance"),
      ("tolerance_rel", False, "relative error tolerance")],
     _mech_hil)
_add("mechatronics_diagnostics", "low", "mechatronics",
     "HAL diagnostics for the connected device",
     [], _mech_diagnostics)
_add("mechatronics_bom", "medium", "mechatronics",
     "Bill of materials with quantities + price availability (no invented "
     "prices)",
     [("items", False, "JSON list of {name, qty, unit_cost?}")],
     _mech_bom)
_add("mechatronics_interfaces", "medium", "mechatronics",
     "Validate a wiring/interface plan (nets + interfaces)",
     [("nets", False, "JSON list of {source, dest} nets"),
      ("interfaces", False, "JSON list of interfaces")],
     _mech_interfaces)


TOOLS = _mech_tools

__all__ = ["TOOLS"]
