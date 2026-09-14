"""Feature 117 tools — PCB design & EDA automation surface (terminal-first)."""

from functools import lru_cache
import json

from tools.day2_tools import _safe, _parse_kv

_pcb_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _pcb_tools.append(spec)


@lru_cache(maxsize=1)
def _pcb():
    import core.pcb_eda as pcb
    return pcb


def _pcb_status(**kw):
    return _pcb().detect()


def _pcb_board(**kw):
    return _pcb().create_board(
        kind=str(kw.get("kind") or "auto").strip(),
        source=str(kw.get("source")) if kw.get("source") else None,
        name=str(kw.get("name") or "arven_board").strip(),
        **(_parse_kv(kw.get("params")) if kw.get("params") else {}))


def _pcb_drc(**kw):
    return _pcb().drc(str(kw.get("board")),
                      clearance=kw.get("clearance"))


def _pcb_export(**kw):
    return _pcb().export_outputs(
        str(kw.get("board")), include_fab=bool(kw.get("include_fab", False)))


def _pcb_fabrication_check(**kw):
    return _pcb().fabrication_check(
        str(kw.get("board")),
        fab_dir=str(kw.get("fab_dir")) if kw.get("fab_dir") else None)


# --- Feature 117 ----------------------------------------------------------
_add("pcb_status", "low", "pcb_eda",
     "Probe real EDA backends (KiCad/gerbv) — honest capability report",
     [], _pcb_status)
_add("pcb_board", "medium", "pcb_eda",
     "Create a PCB board model (template or netlist import) as a real artifact",
     [("kind", False, "blink | sensor | auto"),
      ("source", False, "import .json/.csv netlist"),
      ("name", False, "board name"),
      ("params", False, "template params (key:value,...)")],
     _pcb_board)
_add("pcb_drc", "medium", "pcb_eda",
     "Geometric design-rule check: overlap, spacing, keepout, unrouted nets",
     [("board", True, "board id or path"),
      ("clearance", False, "min conductor clearance mm")],
     _pcb_drc)
_add("pcb_export", "medium", "pcb_eda",
     "Export netlist + BOM + placement with round-trip verification",
     [("board", True, "board id or path"),
      ("include_fab", False, "attempt fabrication via real EDA backend")],
     _pcb_export)
_add("pcb_fabrication_check", "medium", "pcb_eda",
     "Verify required Gerber/Drill files exist — honest manufacturability",
     [("board", True, "board id or path"),
      ("fab_dir", False, "directory holding fabrication files")],
     _pcb_fabrication_check)


TOOLS = _pcb_tools

__all__ = ["TOOLS"]