"""Feature 119 tools — scientific software & computational workflows surface."""

from functools import lru_cache
import json

from tools.day2_tools import _safe, _parse_list, _parse_json

_sci_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _sci_tools.append(spec)


@lru_cache(maxsize=1)
def _sci():
    import core.scientific as sci
    return sci


def _normalise(data):
    if data is None:
        return None
    parsed = _parse_json(data)
    return parsed if isinstance(parsed, list) and parsed else None


def _sci_detect(**kw):
    return _sci().detect()


def _sci_compute(**kw):
    return _sci().compute(
        str(kw.get("method") or "").strip(),
        data=_normalise(kw.get("data")),
        params=_parse_json(kw.get("params")) if kw.get("params") else {})


def _sci_validate(**kw):
    return _sci().validate(
        str(kw.get("method") or "").strip(),
        spec=_parse_json(kw.get("spec")) if kw.get("spec") else {},
        tolerance=kw.get("tolerance"))


def _sci_analyze(**kw):
    return _sci().analyze(str(kw.get("topic") or "").strip(),
                          note=kw.get("note"))


def _sci_workflow(**kw):
    return _sci().workflow(
        str(kw.get("requirement") or "").strip(),
        dataset=_normalise(kw.get("dataset")),
        params=_parse_json(kw.get("params")) if kw.get("params") else {})


def _sci_report(**kw):
    detected = _sci().detect()
    return _sci().generate_report(
        str(kw.get("topic") or "scientific"), str(kw.get("method") or "mean"),
        {"success": True, "status": "ok", "method": kw.get("method"),
         "tool_versions": _sci()._versions()},
        None, detected)


def _sci_methods(**kw):
    return {
        "success": True, "status": "ok",
        "stdlib": list(_sci()._STDLIB_METHODS),
        "numpy": list(_sci()._NUMPY_METHODS),
        "detection": _sci().detect(),
    }


# --- Feature 119 ----------------------------------------------------------
_add("sci_detect", "low", "scientific",
     "Scientific dependency probe (numpy/scipy/pandas/matplotlib/sympy)",
     [], _sci_detect)
_add("sci_compute", "low", "scientific",
     "Real numeric computation; numpy methods report DEPENDENCY_MISSING "
     "honestly when numpy is absent",
     [("method", True, "mean|variance|stdev|median|correlation|"
                       "linear_regression|dft_magnitudes|"
                       "simpson_integral|normal_pdf|histogram|bayes_update|"
                       "fft|matrix_inverse|eigvals"),
      ("data", False, "numeric array (JSON)"),
      ("params", False, "JSON params (y, h, sigma, matrix, ...)")],
     _sci_compute)
_add("sci_validate", "low", "scientific",
     "Analytic-vs-numeric validation with a real tolerance (PASS/FAIL)",
     [("method", True, "simpson_integral|normal_pdf|linear_regression|"
                       "dft_magnitudes"),
      ("spec", False, "JSON spec (freq, steps, slope, ...)"),
      ("tolerance", False, "error tolerance")],
     _sci_validate)
_add("sci_analyze", "low", "scientific",
     "Create a persisted scientific review record",
     [("topic", True, "research topic"),
      ("note", False, "free-form note")],
     _sci_analyze)
_add("sci_workflow", "low", "scientific",
     "End-to-end workflow: REQUIREMENTS->METHOD->COMPUTE->VALIDATE->REPORT",
     [("requirement", True, "scientific task"),
      ("dataset", False, "optional JSON dataset"),
      ("params", False, "JSON method params / validity overrides")],
     _sci_workflow)
_add("sci_report", "low", "scientific",
     "Write a markdown scientific report artifact",
     [("topic", True, "report title"),
      ("method", False, "method name")],
     _sci_report)
_add("sci_methods", "low", "scientific",
     "List runnable stdlib vs numpy-gated methods",
     [], _sci_methods)


TOOLS = _sci_tools

__all__ = ["TOOLS"]