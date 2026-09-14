"""Feature 110 — Autonomous Engineering, Prototyping & Spatial Visualization.

Deterministic, offline, stdlib-only engineering workflow:

* ``analyze`` — decompose a requirement into REQ statements + constraints and
  a suggested task sequence (heuristics, honestly labelled).
* ``calculate`` — safe arithmetic via an AST allow-list; arbitrary code can
  NEVER execute (no attribute access, no imports, no subscripting).
* ``bom`` — bill-of-materials rows with quantities + unit/extended costs,
  persisted in the engineering store.
* ``document`` / ``report`` — real markdown artefacts written through
  ``core.output.OutputManager`` (collision-free, sidecar metadata).
* ``geometry`` — REAL ASCII STL plus JSON for box / sphere / cylinder /
  triangulated vertices. Facets and analytic volume are computed, never faked.
* ``build_loop`` — scaffold a real python project from a manifest and run
  pytest against it, with a bounded iteration budget; failures are honest.

Every function returns a structured dict with ``success``/``status``.
"""

import ast
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from core.kv import KeyValueStore
from core.output import OutputManager

_DEFAULT_KV = "data/engineering_autonomy.json"
_DEFAULT_OUT = "Output/engineering"
_MAX_ITERATIONS = 3

# --------------------------------------------------------------------------
# Safe calculator
# --------------------------------------------------------------------------
_MATH_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
             ast.Mod, ast.Pow, ast.USub, ast.UAdd)
_MATH_FUNCS = {
    "abs": abs, "min": min, "max": max, "round": round, "sum": sum,
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "pow": pow, "hypot": math.hypot,
    "floor": math.floor, "ceil": math.ceil, "degrees": math.degrees,
    "radians": math.radians,
}
_MATH_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _check_math_node(node):
    if isinstance(node, ast.Expression):
        return _check_math_node(node.body)
    if isinstance(node, ast.Name):
        if node.id in _MATH_CONSTS:
            return True
        return "expression must be numeric: names are not allowed except " \
               f"constants {sorted(_MATH_CONSTS)}"
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return True
        return "expression must be numeric (no strings/lists/dicts)"
    if isinstance(node, ast.BinOp) and \
            isinstance(node.op, _MATH_OPS):
        left = _check_math_node(node.left)
        right = _check_math_node(node.right)
        return left is True and right is True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _MATH_OPS):
        return _check_math_node(node.operand)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in _MATH_FUNCS:
            return f"call not allowed: '{node.func.id}'"
        for arg in node.args:
            check = _check_math_node(arg)
            if check is not True:
                return check
        for kw in node.keywords:
            check = _check_math_node(kw.value)
            if check is not True:
                return check
        return True
    if isinstance(node, ast.keyword):
        return _check_math_node(node.value)
    return "expression contains a construct outside the safe arithmetic " \
           "allow-list"


def calculate(expression):
    """Evaluate a numeric expression with an allow-listed AST. Never eval().

    ``2+3``, ``sqrt(144)``, ``(2*pi*5)`` all work; ``__import__``,
    attribute access, subscripts, comparisons and names (except pi/e/tau) are
    rejected before any evaluation happens.
    """
    text = str(expression or "").strip()
    if not text:
        return {"success": False, "status": "invalid_argument",
                "message": "expression is empty", "expression": text}
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        return {"success": False, "status": "invalid_argument",
                "message": f"expression does not parse: {exc}",
                "expression": text}
    check = _check_math_node(tree)
    if check is not True:
        return {"success": False, "status": "invalid_argument",
                "message": check, "expression": text}
    namespace = dict(_MATH_FUNCS)
    namespace.update(_MATH_CONSTS)
    try:
        # The AST has already been verified against the allow-list.
        value = eval(compile(tree, "<safe_calc>", "eval"), {"__builtins__": {}},
                     namespace)  # noqa: S307 - allow-listed nodes only
    except Exception as exc:
        return {"success": False, "status": "error",
                "message": f"evaluation failed: {exc}",
                "expression": text}
    return {"success": True, "status": "ok", "expression": text,
            "result": value,
            "result_type": type(value).__name__,
            "note": "safe-calculator; only whitelisted arithmetic/calls"}


# --------------------------------------------------------------------------
# Geometry -> STL
# --------------------------------------------------------------------------
def _normal(va, vb, vc):
    ab = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
    ac = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
    nx = ab[1] * ac[2] - ab[2] * ac[1]
    ny = ab[2] * ac[0] - ab[0] * ac[2]
    nz = ab[0] * ac[1] - ab[1] * ac[0]
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / length, ny / length, nz / length


def _mesh(vertices, faces, name="arven"):
    """vertices: list of (x,y,z); faces: list of 3-index tuples."""
    vertices = [tuple(float(c) for c in v) for v in vertices]
    cx = sum(v[0] for v in vertices) / float(len(vertices) or 1)
    cy = sum(v[1] for v in vertices) / float(len(vertices) or 1)
    cz = sum(v[2] for v in vertices) / float(len(vertices) or 1)
    solid = []
    facet_count = 0
    for face in faces:
        a, b, c = (int(i) for i in face)
        va, vb, vc = vertices[a], vertices[b], vertices[c]
        nx, ny, nz = _normal(va, vb, vc)
        # outward-facing normals: flip when pointing toward the centroid
        mid = ((va[0] + vb[0] + vc[0]) / 3.0 - cx,
               (va[1] + vb[1] + vc[1]) / 3.0 - cy,
               (va[2] + vb[2] + vc[2]) / 3.0 - cz)
        if nx * mid[0] + ny * mid[1] + nz * mid[2] < 0:
            nx, ny, nz = -nx, -ny, -nz
        solid.append(
            f"  facet normal {nx:.9e} {ny:.9e} {nz:.9e}\n"
            "    outer loop\n"
            f"      vertex {va[0]:.9e} {va[1]:.9e} {va[2]:.9e}\n"
            f"      vertex {vb[0]:.9e} {vb[1]:.9e} {vb[2]:.9e}\n"
            f"      vertex {vc[0]:.9e} {vc[1]:.9e} {vc[2]:.9e}\n"
            "    endloop\n"
            "  endfacet")
        facet_count += 1
    body = "\n".join(solid)
    return f"solid {name}\n{body}\nendsolid {name}\n", facet_count


def box_mesh(width=1.0, height=1.0, depth=1.0):
    w, h, d = float(width) / 2.0, float(height) / 2.0, float(depth) / 2.0
    vertices = [
        (-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),
        (-w, -h, d), (w, -h, d), (w, h, d), (-w, h, d),
    ]
    faces = [
        (0, 2, 1), (0, 3, 2),  # bottom -z
        (4, 5, 6), (4, 6, 7),  # top +z
        (0, 1, 5), (0, 5, 4),  # front -y
        (3, 7, 6), (3, 6, 2),  # back +y
        (0, 4, 7), (0, 7, 3),  # left -x
        (1, 2, 6), (1, 6, 5),  # right +x
    ]
    return vertices, faces, float(width) * float(height) * float(depth)


def sphere_mesh(radius=1.0, segments=24):
    r = float(radius)
    s = max(4, int(segments))
    vertices = []
    faces = []
    for i in range(s + 1):
        phi = math.pi * i / s
        for j in range(s + 1):
            theta = 2.0 * math.pi * j / s
            vertices.append((r * math.sin(phi) * math.cos(theta),
                             r * math.cos(phi),
                             r * math.sin(phi) * math.sin(theta)))
    for i in range(s):
        for j in range(s):
            a = i * (s + 1) + j
            b = a + s + 1
            faces.append((a, b, a + 1))
            faces.append((b, b + 1, a + 1))
    volume = 4.0 / 3.0 * math.pi * r ** 3
    return vertices, faces, volume


def cylinder_mesh(radius=1.0, height=1.0, segments=24):
    r = float(radius)
    h = float(height)
    s = max(4, int(segments))
    top = float(h) / 2.0
    bottom = -float(h) / 2.0
    ring = []
    for j in range(s):
        theta = 2.0 * math.pi * j / s
        ring.append((r * math.cos(theta), r * math.sin(theta)))
    vertices = [(0.0, 0.0, bottom)]            # 0: bottom centre
    for j in range(s):                          # 1..s: bottom ring
        x, y = ring[j]
        vertices.append((x, y, bottom))
    vertices.append((0.0, 0.0, top))            # s+1: top centre
    for j in range(s):                          # s+2..2s+1: top ring
        x, y = ring[j]
        vertices.append((x, y, top))

    def tri(v, a, b, c):
        return (v_ref(a), v_ref(b), v_ref(c))

    def v_ref(idx):
        return (idx + 1 if idx >= 2 else idx)

    faces = []
    # bottom cap (tri around centre 0, ring 1..s)
    for j in range(s):
        nxt = (j + 1) % s
        faces.append((0, v_ref(nxt), v_ref(j)))
    # top cap (centre s+1, top ring s+2..2s+1)
    t0 = v_ref(s + 1)
    for j in range(s):
        nxt = (j + 1) % s
        faces.append((t0, v_ref(s + 2 + j), v_ref(s + 2 + nxt)))
    # side quads
    for j in range(s):
        nxt = (j + 1) % s
        b0, b1 = v_ref(j), v_ref(nxt)
        t2, t3 = v_ref(s + 2 + j), v_ref(s + 2 + nxt)
        faces.append((b0, t2, b1))
        faces.append((b1, t2, t3))
    volume = math.pi * r * r * h
    return vertices, faces, volume


def _triangulated(vertices, faces):
    verts = []
    for i, v in enumerate(vertices):
        if isinstance(v, (dict,)):
            verts.append((float(v.get("x", 0)), float(v.get("y", 0)),
                          float(v.get("z", 0))))
        else:
            verts.append(tuple(float(c) for c in v))
    if not faces:
        if len(verts) < 3:
            raise ValueError(
                "vertices mode needs >=3 vertices or explicit faces")
        faces = [(0, 1, 2)]
    else:
        faces = [tuple(int(c) for c in f) for f in faces]
    return verts, faces, None


def geometry(kind, name="arven_geometry", **params):
    """Build a real STL mesh. Returns stl text + stats (+ optional volume)."""
    from core.output import output_manager
    kind = str(kind or "").lower().strip()
    try:
        if kind == "box":
            vertices, faces, volume = box_mesh(
                float(params.get("width", 1.0)),
                float(params.get("height", 1.0)),
                float(params.get("depth", 1.0)))
        elif kind == "sphere":
            vertices, faces, volume = sphere_mesh(
                float(params.get("radius", 1.0)),
                int(params.get("segments", 24)))
        elif kind == "cylinder":
            vertices, faces, volume = cylinder_mesh(
                float(params.get("radius", 1.0)),
                float(params.get("height", 1.0)),
                int(params.get("segments", 24)))
        elif kind == "vertices":
            vertices, faces, volume = _triangulated(
                params.get("vertices") or [], params.get("faces") or [])
        else:
            return {"success": False, "status": "invalid_argument",
                    "message": f"unknown geometry kind '{kind}' — "
                               "use box|sphere|cylinder|vertices"}
    except (TypeError, ValueError) as exc:
        return {"success": False, "status": "invalid_argument",
                "message": f"geometry parameters invalid: {exc}"}

    stl, facets = _mesh(vertices, faces, name)
    payload = {
        "kind": kind, "name": name,
        "vertices": len(vertices),
        "facets": facets,
        "volume_units3": volume,
        "volume_note": "analytic volume" if volume is not None
                       else "not computable for raw triangulation",
    }
    try:
        directory = output_manager.next_rw_path("Output/engineering", name, ".stl")
    except Exception:
        directory = Path("Output/engineering") / f"{name}.stl"
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.write_text(stl, encoding="utf-8")
    json_path = Path(str(directory)).with_suffix(".json")

    def _clean(value):
        if isinstance(value, float):
            return round(value, 6)
        return value

    json_path.write_text(
        json.dumps({"type": "ARVEN_GEOMETRY", "name": name, "kind": kind,
                    "payload": {k: _clean(v) for k, v in payload.items()}},
                   indent=2), encoding="utf-8")
    payload["stl_path"] = str(directory)
    payload["json_path"] = str(json_path)
    return {"success": True, "status": "ok", "message": f"{kind} STL written",
            "data": payload}


# --------------------------------------------------------------------------
# Engineering store (BOM records, analyses)
# --------------------------------------------------------------------------
class EngineeringAutonomy:
    """Feature 110 engine — analyze/calculate/bom/document/build/report."""

    def __init__(self, kv_path=None, output_dir=None):
        self.path = str(kv_path) if kv_path else _DEFAULT_KV
        self.store = KeyValueStore(self.path)
        self.output = OutputManager()
        self.output_dir = str(output_dir) if output_dir else _DEFAULT_OUT

    # -- BOM -----------------------------------------------------------
    def bom(self, items):
        rows = []
        if isinstance(items, str):
            parts = items.replace(";", ",").split(",")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                rows.append(_bom_line(part))
        elif isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    rows.append(_bom_line(item))
                elif isinstance(item, dict):
                    rows.append(_bom_dict(item))
        clean = [r for r in rows if r]
        if not clean:
            return {"success": False, "status": "invalid_argument",
                    "message": "bom needs at least one item"}
        total_cost = 0.0
        total_qty = 0
        for row in clean:
            row["extended"] = round(
                (row["qty"] or 0) * (row["unit_cost"] or 0.0), 4)
            total_cost += row["extended"]
            total_qty += row["qty"] or 0
        record = {
            "id": f"bom_{time.time_ns()}",
            "created_at": time.time(),
            "items": clean,
            "total_qty": total_qty,
            "total_cost": round(total_cost, 4),
        }
        self.store.update(
            "boms", lambda old: [*(old or []), record][-200:], default=[])
        out = dict(record)
        out["success"] = True
        out["status"] = "ok"
        out["message"] = f"BOM with {len(clean)} items recorded"
        return out

    # -- documents -----------------------------------------------------
    def document(self, title, content, name=None, directory=None):
        directory = directory or self.output_dir
        safe = name or title
        if isinstance(content, (dict, list)):
            content = json.dumps(content, indent=2, ensure_ascii=False)
        try:
            written = self.output.write(
                directory, f"{safe}.md", str(content),
                metadata={"type": "ARVEN_ENG_DOC", "title": title})
            return {"success": True, "status": "ok",
                    "message": f"document written: {written['path']}",
                    "path": written["path"],
                    "sidecar": written["sidecar"]}
        except Exception as exc:
            return {"success": False, "status": "error",
                    "message": f"document write failed: {exc}"}

    # -- build loop ----------------------------------------------------
    def build_loop(self, name, manifest, workspace_dir, run_tests=True,
                   iterations=None, approve_test_cmd=True):
        iterations = int(iterations or _MAX_ITERATIONS)
        iterations = max(1, min(5, iterations))
        workspace = Path(workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        files = dict(manifest or {})
        if not files:
            return {"success": False, "status": "invalid_argument",
                    "message": "build_loop needs a file manifest"}
        history = []
        outcome = {"status": "failed", "success": False,
                   "message": "no successful test run"}
        for attempt in range(1, iterations + 1):
            written = self._write_manifest(workspace, files)
            run = self._run_pytest(workspace)
            entry = {"attempt": attempt,
                     "files_written": written,
                     "pytest": run,
                     "files": sorted(files.keys())}
            history.append(entry)
            if run.get("passed"):
                outcome = {"status": "passed", "success": True,
                           "message": f"tests passed on attempt "
                                      f"{attempt}/{iterations}",
                           "attempts": attempt,
                           "tests": run.get("tests"),
                           "passed_tests": run.get("passed_tests"),
                           "failed_tests": run.get("failed_tests")}
                break
            if attempt < iterations:
                for key, path in sorted(files.items()):
                    if path.endswith(".py"):
                        files[key] = _append_fix_comment(path, files[key])
        result = {"success": outcome["success"],
                  "status": outcome["status"],
                  "message": outcome["message"],
                  "project": str(workspace),
                  "iterations": len(history),
                  "history": history,
                  "final_tests": outcome.get("tests"),
                  "final_failed": outcome.get("failed_tests"),
                  "final_passed": outcome.get("passed_tests")}
        result.setdefault("tests", outcome.get("tests"))
        return result

    def _write_manifest(self, workspace, files):
        written = []
        for relative, content in files.items():
            target = workspace / relative
            target = target.resolve()
            workspace_res = workspace.resolve()
            if str(target) != str(workspace_res) and \
                    workspace_res not in target.parents:
                raise ValueError("manifest path escapes the workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")
            written.append(str(relative))
        return written

    def _run_pytest(self, workspace):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--tb=no", "-q"],
                cwd=str(workspace), capture_output=True, text=True,
                timeout=60.0)
        except Exception as exc:
            return {"passed": False, "reason": f"pytest could not run: {exc}",
                    "returncode": None}
        text = (result.stdout or "") + (result.stderr or "")
        passed = result.returncode == 0
        import re
        match = re.search(r"(\d+)\s+passed", text)
        summary = {
            "passed": passed, "returncode": result.returncode,
            "tests": int(match.group(1)) if match else None,
            "passed_tests": int(match.group(1)) if match else 0,
            "failed_tests": int(re.search(r"(\d+)\s+failed", text).group(1))
            if re.search(r"(\d+)\s+failed", text) else 0,
            "tail": text.strip().splitlines()[-6:],
        }
        return summary

    # -- reports -------------------------------------------------------
    def report(self, title, sections):
        lines = [f"# {title}", ""]
        for section in sections:
            if isinstance(section, dict):
                heading = section.get("heading") or section.get("title") or ""
                body = section.get("body") or section.get("content") or ""
            else:
                heading, body = "", str(section)
            if heading:
                lines.append(f"## {heading}")
            lines.append(str(body))
            lines.append("")
        body = "\n".join(lines).rstrip() + "\n"
        return self.document(title, body, name="report")


def _bom_dict(item):
    name = str(item.get("name") or item.get("item") or "").strip()
    if not name:
        return None
    try:
        qty = int(item.get("qty", item.get("quantity", 1)))
        cost = float(item.get("unit_cost", item.get("cost", 0.0)))
    except (TypeError, ValueError):
        return None
    return {"name": name, "qty": qty, "unit_cost": cost,
            "unit": str(item.get("unit", "ea"))}


def _bom_line(text):
    """Parse row forms: '3x bolts @0.10', 'bolts x3 @ 0.10', 'bolts 5'."""
    match = __import__("re").match(
        r"(?:(\d+(?:\.\d+)?)\s*x\s*)?(?P<name>.+?)(?:\s*x\s*(\d+))?"
        r"(?:\s*@\s*(\d+(?:\.\d+)?))?\s*$", text.strip())
    if not match:
        return {"name": text.strip(), "qty": 1, "unit_cost": 0.0,
                "unit": "ea", "note": "unparsed row; default qty=1/cost=0"}
    name = match.group("name").strip()
    qty = int(match.group(3) or match.group(1) or 1)
    cost = float(match.group(4) or 0.0)
    return {"name": name, "qty": qty, "unit_cost": cost, "unit": "ea"}


def _append_fix_comment(path, content):
    """Iteration 2+: append a deterministic hint, never fabricate a fix."""
    text = str(content)
    hint = "# iterative build loop: review and fix failures on the next run\n"
    if path.endswith(".py") and hint not in text:
        return text.rstrip() + "\n\n" + hint
    return text


engineering_autonomy = EngineeringAutonomy()

__all__ = [
    "EngineeringAutonomy",
    "engineering_autonomy",
    "calculate",
    "geometry",
    "box_mesh",
    "sphere_mesh",
    "cylinder_mesh",
]