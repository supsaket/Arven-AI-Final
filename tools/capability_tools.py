"""Feature 109 + registry tools — capability awareness surface (terminal-first).

Every tool returns an honest structured dict: probes report what is actually
detected; nothing is invented. ``feature_status`` reconciles the catalog
against the live registry (the single source of truth). 
"""

from functools import lru_cache

from tools.day2_tools import _safe

_cap_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _cap_tools.append(spec)


@lru_cache(maxsize=1)
def _engine_cap():
    from core.capability_awareness import CapabilityAwareness
    return CapabilityAwareness()


def _snapshot(force=False):
    return _engine_cap().probe(force=force)


def _cap_probe(**kw):
    engine = _engine_cap()
    capability = kw.get("capability")
    if capability:
        from core.capabilities import Capabilities
        status = Capabilities().resolve(str(capability)).value
        return {"success": True, "status": "ok", "capability": capability,
                "resolved": status}
    snapshot = _snapshot()
    return {"success": True, "status": "ok",
            "message": "capability status (offline=false)",
            "data": {"capabilities": snapshot.get("capabilities", {})},
            "summary": _cap_summary(snapshot.get("capabilities", {}))}


def _cap_profile(**kw):
    snapshot = _snapshot()
    data = {k: snapshot[k] for k in
            ("hardware", "software", "providers", "permissions",
             "capabilities")}
    return {"success": True, "status": "ok",
            "message": "full capability profile",
            "generated_at": snapshot.get("generated_at"),
            "data": data}


def _cap_software(**kw):
    snapshot = _snapshot()
    software = snapshot.get("software", {})
    return {"success": True, "status": "ok", "message": "software inventory",
            "data": {"software": software,
                     "available": sorted(n for n, v in software.items()
                                         if v.get("available")),
                     "missing": sorted(n for n, v in software.items()
                                       if not v.get("available"))}}


def _cap_permissions(**kw):
    snapshot = _snapshot()
    perms = snapshot.get("permissions", {})
    return {"success": True, "status": "ok",
            "message": "permission snapshot (read-only)",
            "data": perms}


def _cap_graph(**kw):
    engine = _engine_cap()
    question = kw.get("question")
    graph = engine.graph(question=question or kw.get("query"))
    return {"success": True, "status": "ok", "message": "capability graph",
            "data": graph}


def _cap_dependencies(**kw):
    engine = _engine_cap()
    feature_id = kw.get("feature_id")
    deps = engine.dependencies(
        int(feature_id) if str(feature_id or "").strip().isdigit()
        else None)
    return {"success": True, "status": "ok",
            "message": "dependency map",
            "data": deps}


def _cap_refresh(**kw):
    engine = _engine_cap()
    snapshot = engine.refresh()
    return {"success": True, "status": "ok",
            "message": "capability snapshot refreshed (fresh, not cached)",
            "generated_at": snapshot.get("generated_at"),
            "data": snapshot.get("capabilities", {})}


def _cap_summary(caps):
    from collections import Counter
    return dict(Counter(str(v) for v in caps.values()))


def _feature_status(**kw):
    from core.features import feature, is_framework_feature
    raw = str(kw.get("feature_id") or "").strip()
    if not raw.isdigit():
        return {"success": False, "status": "invalid_argument",
                "message": "feature_id must be an integer (1..122)",
                "feature_id": raw}
    fid = int(raw)
    row = feature(fid)
    if row is None:
        return {"success": False, "status": "invalid_argument",
                "message": f"unknown feature id {fid}",
                "feature_id": fid}
    from tools.builder import get_registry
    registry = get_registry()
    tool_rows = []
    missing = []
    for name in row["tools"]:
        tool = registry.get(name)
        if tool is None:
            missing.append(name)
            tool_rows.append({"name": name, "registered": False})
        else:
            tool_rows.append({
                "name": name, "registered": True,
                "available": tool.available,
                "risk": tool.risk,
                "confirm_required": tool.confirm_required,
            })
    return {
        "success": True, "status": "ok", "feature_id": fid,
        "name": row["name"],
        "kind": "framework" if is_framework_feature(fid) else "tool-backed",
        "tools_registered": len(tool_rows) - len(missing),
        "tools_missing": missing,
        "tools": tool_rows,
        "entrypoints": list(row["entrypoints"]),
        "offline": row["offline"],
        "risk": row["risk"],
        "dependency": row["dependency"],
        "persistence": row["persistence"],
        "recovery": row["recovery"],
        "artifacts": row["artifacts"],
        "message": ("feature fully registered"
                    if not missing else
                    f"feature has {len(missing)} unregistered tool(s): "
                    f"{missing}"),
    }


# --- Feature 109: capability awareness -----------------------------------
_add("capability_probe", "low", "capabilities",
     "Resolve the honest status of one capability (or all)",
     [("capability", False, "optional capability id")], _cap_probe)
_add("capability_profile", "low", "capabilities",
     "Full profile: hardware, software, providers, permissions, capabilities",
     [], _cap_profile)
_add("capability_software", "low", "capabilities",
     "Key software present/absent on this machine",
     [], _cap_software)
_add("capability_permissions", "low", "capabilities",
     "Read-only access-grant snapshot",
     [], _cap_permissions)
_add("capability_graph", "low", "capabilities",
     "Self-answering capability graph (9 questions)",
     [("question", False, "e.g. what_exists | what_is_available")],
     _cap_graph)
_add("capability_dependencies", "low", "capabilities",
     "Dependency map for a feature id (or the whole catalog)",
     [("feature_id", False, "int 1-122; omit for catalog-wide")],
     _cap_dependencies)
_add("capability_refresh", "low", "capabilities",
     "Force a fresh capability probe (bypasses the TTL cache)",
     [], _cap_refresh)

# --- Feature 23: registry / feature status --------------------------------
_add("feature_status", "low", "features",
     "Reconcile one feature against the live registry",
     [("feature_id", True, "int 1-122")], _feature_status)


TOOLS = _cap_tools

__all__ = ["TOOLS"]