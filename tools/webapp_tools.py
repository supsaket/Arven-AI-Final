"""Feature 118 tools — autonomous web/app/game creation & QA surface."""

from functools import lru_cache

from tools.day2_tools import _safe, _parse_list

_webapp_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _webapp_tools.append(spec)


@lru_cache(maxsize=1)
def _engine():
    from core.web_app_engine import WebAppEngine
    return WebAppEngine()


def _webapp_status(**kw):
    from core.web_app_engine import _TEMPLATES, _plan
    return {
        "success": True, "status": "ok",
        "status_code": "AVAILABLE",
        "templates": sorted(_TEMPLATES),
        "loop": ["REQUIREMENTS", "PLAN", "IMPLEMENT", "BUILD", "RUN",
                 "INSPECT", "TEST", "DETECT_FAILURE", "FIX", "REBUILD",
                 "RETEST", "FINAL_VERIFY"],
        "note": "stdio-only: real compile (py_compile), real subprocess run, "
                "real pytest; failures are never masked",
    }


def _webapp_create(**kw):
    workspace = str(kw.get("workspace_dir") or "Output/webapps")
    return _engine().create(
        kw.get("requirement"), str(kw.get("name") or "generated_project"),
        workspace,
        iterations=int(kw.get("iterations", 3)),
        kind=str(kw.get("kind") or "").strip() or None,
        run_port=int(kw.get("run_port", 8123)))


def _webapp_build(**kw):
    return _engine().build_project(
        str(kw.get("name") or "project"),
        str(kw.get("workspace_dir") or "Output/webapps"))


def _webapp_inspect(**kw):
    return _engine().inspect_project(
        str(kw.get("name") or "project"),
        str(kw.get("workspace_dir") or "Output/webapps"))


def _webapp_qa(**kw):
    return _engine().qa_report(
        str(kw.get("name") or "project"),
        str(kw.get("workspace_dir") or "Output/webapps"))


# --- Feature 118 ----------------------------------------------------------
_add("webapp_status", "low", "web_app",
     "Web/app/game engine status: templates + loop stages",
     [], _webapp_status)
_add("webapp_create", "high", "web_app",
     "Autonomous create+QA loop for a web/app/game from a requirement; "
     "FINAL_VERIFY requires a real build+run+test pass",
     [("requirement", True, "what to build"),
      ("name", False, "project name"),
      ("workspace_dir", False, "output directory"),
      ("iterations", False, "1-3 bounded attempts"),
      ("kind", False, "web | game | app (auto if omitted)"),
      ("run_port", False, "port for the run probe")],
     _webapp_create)
_add("webapp_build", "low", "web_app",
     "Run real build + pytest against an existing generated project",
     [("name", False, "project name"),
      ("workspace_dir", False, "project directory")],
     _webapp_build)
_add("webapp_inspect", "low", "web_app",
     "Show the generated project sources and tree",
     [("name", False, "project name"),
      ("workspace_dir", False, "project directory")],
     _webapp_inspect)
_add("webapp_qa", "low", "web_app",
     "QA report: fresh build + pytest verdict for an existing project",
     [("name", False, "project name"),
      ("workspace_dir", False, "project directory")],
     _webapp_qa)


TOOLS = _webapp_tools

__all__ = ["TOOLS"]