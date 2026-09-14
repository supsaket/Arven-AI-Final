"""Feature 120 tools — Template-Aware Professional Artifact Engine surface."""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_json

_art_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _art_tools.append(spec)


@lru_cache(maxsize=1)
def _art():
    import core.artifact_engine as engine
    return engine


def _art_status(**kw):
    detected = _art().detect_dependencies()
    return {"status_code": "OK", "success": True, "status": "ok",
            "libraries": detected,
            "kinds": sorted(_art()._SUPPORTED),
            "zero_dependency_kinds": ["md", "csv", "json", "docx", "xlsx",
                                      "pdf"],
            "message": "artifact engine readiness report"}


def _art_inspect(**kw):
    if kw.get("template_file"):
        return _art().inspect_template(kw["template_file"])
    return {"status_code": "OK", "success": True, "status": "ok",
            "kinds": sorted(_art()._SUPPORTED),
            "template_flow": ("template files may be .md text ({{field}} "
                              "placeholders) or .docx/.xlsx OOXML containers"),
            "message": "supported artifact kinds listed"}


def _art_generate(**kw):
    data = _parse_json(kw.get("data")) if kw.get("data") else {}
    rows = _parse_json(kw.get("rows")) if kw.get("rows") else None
    if not isinstance(data, dict):
        data = {"body": data}
    rendered = _art().generate(
        str(kw.get("kind") or "").strip(), data,
        name=str(kw.get("name") or "arven_artifact").strip(),
        template_file=kw.get("template_file") or None,
        out_dir=kw.get("out_dir") or None,
        attempt_install=(str(kw.get("attempt_install", "true")).lower()
                         in ("1", "true", "yes")),
        rows=rows)
    code = {"ok": "OK", "VALIDATION_FAILED": "VALIDATION_FAILED",
            "SOFTWARE_REQUIRED": None}.get(
                rendered.get("status"),
                rendered.get("status_code") or "ERROR")
    return {**rendered,
            "status_code": code if code else rendered.get("status") or "OK"}


def _art_validate(**kw):
    return _art().validate(kw.get("template_file"),
                           _parse_json(kw.get("data")) if kw.get("data")
                           else {})


def _art_ensure(**kw):
    return _art().ensure_tools(
        kw.get("modules") or None,
        timeout=int(_safe(kw.get("timeout", "20"))(kw) or 20))


# --- Feature 120 ----------------------------------------------------------
_add("art_status", "low", "artifact",
     "Artifact engine readiness: libraries present and supported kinds",
     [], _art_status)
_add("art_inspect", "low", "artifact",
     "Inspect an existing template (text or OOXML) read-only, or list kinds",
     [("template_file", False, "path to a template file")],
     _art_inspect)
_add("art_generate", "medium", "artifact",
     "Render a real artifact: LOAD->GENERATE->VALIDATE->COMPARE->FINALIZE "
     "(md/csv/json/docx/xlsx/pptx/pdf)",
     [("kind", True, "md|csv|json|docx|xlsx|pptx|pdf"),
      ("data", True, "JSON payload (title/body/rows)"),
      ("name", False, "artifact base name"),
      ("template_file", False, "optional template path"),
      ("rows", False, "JSON 2D row array"),
      ("out_dir", False, "output directory (default Output/artifacts)"),
      ("attempt_install", False, "allow short pip install of missing libs")],
     _art_generate)
_add("art_validate", "low", "artifact",
     "Validate a template: placeholders satisfied + OOXML reopens",
     [("template_file", True, "template path"),
      ("data", False, "JSON data used to fill placeholders")],
     _art_validate)
_add("art_ensure", "medium", "artifact",
     "Short, time-bounded install of artifact libraries (honest success "
     "report — only truly importable libs count)",
     [("modules", False, "comma-separated lib list; default all"),
      ("timeout", False, "seconds per attempt (default 20)")],
     _art_ensure)


TOOLS = _art_tools

__all__ = ["TOOLS"]