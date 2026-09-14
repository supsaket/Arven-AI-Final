"""Feature 110 tools — engineering workflow surface (terminal-first).

Real artefacts only: safe-calculator results, persisted BOM rows, markdown
documents, ASCII STL geometry and a bounded pytest build loop. Honesty rule:
a build loop that never passes reports FAILED — never a fabricated pass.
"""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_list, _parse_json

_eng_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _eng_tools.append(spec)


@lru_cache(maxsize=1)
def _engine_eng():
    from core.engineering_autonomy import EngineeringAutonomy
    return EngineeringAutonomy()


def _eng_analyze(**kw):
    import re
    requirement = str(kw.get("requirement") or "").strip()
    if not requirement:
        return {"success": False, "status": "invalid_argument",
                "message": "requirement is empty"}
    sentences = [s.strip() for s in re.split(r"[.;!]+", requirement)
                 if s.strip()]
    reqs = [f"REQ{i + 1}: {s}" for i, s in enumerate(sentences)]
    lowered = requirement.lower()
    constraints = []
    if any(w in lowered for w in ("safe", "safety", "guard", "protected")):
        constraints.append(
            "safety-first: confirmations and guards are honoured")
    if any(w in lowered for w in ("offline", "local", "no network")):
        constraints.append("must work offline / local-only")
    if any(w in lowered for w in ("resource", "memory", "bounded", "budget")):
        constraints.append("respect resource/budget bounds")
    return {
        "success": True, "status": "ok", "requirement": requirement,
        "requirements": reqs,
        "constraints": constraints,
        "suggested_steps": ["lock requirements",
                            "define interfaces/schema",
                            "build prototype",
                            "test and evidence results"],
        "note": "deterministic heuristic decomposition — review before build",
    }


def _eng_calculate(**kw):
    from core.engineering_autonomy import calculate
    return calculate(kw.get("expression"))


def _eng_bom(**kw):
    items = kw.get("items")
    engine = _engine_eng()
    if isinstance(items, str):
        return engine.bom(items)
    return engine.bom(_parse_list(items))


def _eng_document(**kw):
    engine = _engine_eng()
    return engine.document(
        str(kw.get("title") or "untitled"),
        str(kw.get("content") or ""),
        name=kw.get("name"))


def _eng_geometry(**kw):
    from core.engineering_autonomy import geometry
    kind = str(kw.get("kind") or "").strip().lower()
    params = {k: kw[k] for k in
              ("width", "height", "depth", "radius", "segments")
              if kw.get(k) is not None}
    name = str(kw.get("name") or "arven_geometry").strip()
    return geometry(kind, name=name, **params)


def _eng_build_loop(**kw):
    engine = _engine_eng()
    name = str(kw.get("name") or "build").strip()
    manifest = kw.get("manifest")
    files = _parse_json(manifest) if isinstance(manifest, str) else manifest
    if not isinstance(files, dict):
        return {"success": False, "status": "invalid_argument",
                "message": "manifest must be a JSON object "
                           "{\"file.py\": \"content\", ...}"}
    from core.output import output_manager
    safe = output_manager.safe_filename(name)
    workspace = f"Output/engineering/builds/{safe}"
    return engine.build_loop(
        name, files, workspace,
        run_tests=bool(kw.get("run_tests", True)),
        iterations=kw.get("iterations"))


def _eng_report(**kw):
    engine = _engine_eng()
    title = str(kw.get("title") or "Engineering Report")
    sections = kw.get("sections")
    if isinstance(sections, str):
        sections = _parse_json(sections) or []
    if isinstance(sections, (list, tuple)):
        sections = list(sections)
    else:
        sections = [{"heading": "Notes", "body": str(sections or "")}]
    return engine.report(title, sections)


# --- Feature 110 ----------------------------------------------------------
_add("eng_analyze", "low", "engineering",
     "Decompose a requirement into REQ statements, constraints and steps",
     [("requirement", True, "free-text requirement")], _eng_analyze)
_add("eng_calculate", "low", "engineering",
     "Safe arithmetic calculator (allow-listed AST, no code execution)",
     [("expression", True, "e.g. 2+3*4 or sqrt(144)")], _eng_calculate)
_add("eng_bom", "low", "engineering",
     "Record and total a bill of materials",
     [("items", True, "list or '3x bolts @0.10; ...'")], _eng_bom)
_add("eng_document", "low", "engineering",
     "Write an engineering markdown document (collision-free)",
     [("title", True, ""), ("content", False, "markdown body"),
      ("name", False, "filename base (optional)")], _eng_document)
_add("eng_geometry", "low", "engineering",
     "Build a real ASCII STL + JSON mesh (box|sphere|cylinder|vertices)",
     [("kind", True, "box|sphere|cylinder|vertices"), ("name", False, ""),
      ("width", False, "float"), ("height", False, "float"),
      ("depth", False, "float"), ("radius", False, "float"),
      ("segments", False, "int")], _eng_geometry)
_add("eng_build_loop", "medium", "engineering",
     "Scaffold a python project from a manifest and run pytest (bounded)",
     [("name", True, "project name"),
      ("manifest", True, "JSON {\"file.py\": \"content\", ...}"),
      ("run_tests", False, "bool"), ("iterations", False, "int 1-5")],
     _eng_build_loop)
_add("eng_report", "low", "engineering",
     "Compose + export an engineering markdown report",
     [("title", False, ""), ("sections", False, "JSON list of sections")],
     _eng_report)


TOOLS = _eng_tools

__all__ = ["TOOLS"]