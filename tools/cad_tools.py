"""Feature 116 tools — CAD & 3D reconstruction surface (terminal-first)."""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_kv, _parse_json
import json

_cad_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _cad_tools.append(spec)


@lru_cache(maxsize=1)
def _cad():
    import core.cad_3d as cad
    return cad


def _cad_detect(**kw):
    return _cad().detect()


def _cad_make(**kw):
    params = _parse_kv(kw.get("params")) if kw.get("params") else {}
    return _cad().make(str(kw.get("kind") or "box").strip(),
                       str(kw.get("name") or "arven_cad").strip(), **params)


def _cad_inspect(**kw):
    return _cad().inspect(str(kw.get("path")))


def _cad_validate(**kw):
    requested = None
    dims = kw.get("dims")
    if dims:
        parsed = _parse_json(dims) if str(dims).strip().lstrip() == "{" \
            else _parse_kv(dims)
        if isinstance(parsed, dict):
            requested = {k: float(v) for k, v in parsed.items()
                         if k in ("x", "y", "z")}
    return _cad().validate(str(kw.get("path")), requested=requested,
                           tolerance=float(kw.get("tolerance", 0.05)))


def _cad_export(**kw):
    return _cad().export_object(str(kw.get("source")),
                                str(kw.get("target")) if kw.get("target") else None)


def _cad_reconstruct(**kw):
    return _cad().reconstruct(
        str(kw.get("mode") or "photogrammetry").strip(),
        source=str(kw.get("source")) if kw.get("source") else None,
        name=str(kw.get("name") or "arven_recon").strip())


# --- Feature 116 ----------------------------------------------------------
_add("cad_detect", "low", "cad_3d",
     "Report real CAD/3D backends present on this machine",
     [], _cad_detect)
_add("cad_make", "low", "cad_3d",
     "Generate a real STL mesh (box/sphere/cylinder) with analytic volume",
     [("kind", True, "box | sphere | cylinder"),
      ("params", False, "width/height/depth | radius | radius/height/segments"),
      ("name", False, "artifact name")],
     _cad_make)
_add("cad_inspect", "low", "cad_3d",
     "Parse STL/OBJ into facets + bounds + watertightness",
     [("path", True, "stl or obj file")], _cad_inspect)
_add("cad_validate", "low", "cad_3d",
     "Real geometric validation: watertightness, dims, topology, round-trip",
     [("path", True, "stl or obj file"),
      ("dims", False, "requested extents, e.g. 1x1x1 or JSON"),
      ("tolerance", False, "fractional tolerance (default 0.05)")],
     _cad_validate)
_add("cad_export", "low", "cad_3d",
     "Convert a real mesh between STL and OBJ with round-trip honesty",
     [("source", True, "input mesh file"),
      ("target", False, "output path (default: sibling)")],
     _cad_export)
_add("cad_reconstruct", "low", "cad_3d",
     "3D reconstruction: hull (real convex hull of a point cloud) or "
     "photogrammetry (honest capability check)",
     [("mode", False, "photogrammetry | hull"),
      ("source", False, "CSV/JSON point cloud for hull mode"),
      ("name", False, "artifact name")],
     _cad_reconstruct)


TOOLS = _cad_tools

__all__ = ["TOOLS"]