"""Day 4 — Feature 110: Autonomous Engineering, Prototyping & Spatial
Visualization.

Real artifacts only: safe-calculator results, real ASCII STL meshes, persisted
BOM rows, markdown documents and a bounded pytest build loop that reports
failures honestly.
"""

import json
import math
import os

import pytest

from core.engineering_autonomy import (
    EngineeringAutonomy,
    calculate,
    geometry,
)


def test_calculate_known_arithmetic():
    assert calculate("2+3*4")["result"] == 14.0
    assert calculate("sqrt(144)")["result"] == 12.0
    assert calculate("(2*pi*5)")["result"] == pytest.approx(10.0 * math.pi)


def test_calculate_empty_is_invalid():
    out = calculate("")
    assert out["success"] is False
    assert out["status"] == "invalid_argument"


def test_calculate_rejects_code_execution():
    for expr in ("__import__('os').system('echo hi')",
                 "open('x').read()",
                 "os.getcwd()",
                 "\"2\" + 3",
                 "[1,2,3][0]",
                 "a=1; a",
                 "1 < 2",
                 "__builtins__"):
        out = calculate(expr)
        assert out["success"] is False, expr
        assert out["status"] == "invalid_argument", expr
        assert "result" not in out, expr


def test_geometry_box_writes_real_stl(tmp_path, monkeypatch):
    from core import output as output_mod
    stl_path = tmp_path / "arven_box.stl"

    class _Stub:
        def next_rw_path(self, base, name, ext):
            return stl_path

    monkeypatch.setattr(output_mod, "output_manager", _Stub())
    out = geometry("box", name="arven_box", width=4, height=3, depth=2)
    assert out["status"] == "ok"
    payload = out["data"]
    assert payload["facets"] == 12
    assert payload["volume_units3"] == 24.0
    assert payload["stl_path"] == str(stl_path)
    stl = stl_path.read_text(encoding="utf-8")
    assert stl.startswith("solid arven_box")
    assert stl.rstrip().endswith("endsolid arven_box")
    meta = json.loads(stl_path.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["type"] == "ARVEN_GEOMETRY"


def test_geometry_sphere_facets_count(tmp_path, monkeypatch):
    from core import output as output_mod
    stl_path = tmp_path / "arven_sphere.stl"
    monkeypatch.setattr(output_mod, "output_manager",
                        type("_Stub", (), {
                            "next_rw_path": lambda self, b, n, e: stl_path})())
    out = geometry("sphere", name="arven_sphere", radius=1.0, segments=16)
    assert out["success"] is True
    assert out["data"]["facets"] == 512  # 2 * s * s


def test_geometry_unknown_kind_is_honest():
    out = geometry("pyramid")
    assert out["status"] == "invalid_argument"
    assert out["success"] is False


def test_bom_totals_and_persistence(tmp_path):
    engine = EngineeringAutonomy(kv_path=str(tmp_path / "eng.json"))
    out = engine.bom("3x bolts @0.10; 2x clips @0.35")
    assert out["success"] is True
    assert out["total_qty"] == 5
    assert out["total_cost"] == pytest.approx(1.0)
    assert len(out["items"]) == 2
    second = engine.bom([{"name": "panel", "qty": 2, "unit_cost": 5.0}])
    assert second["total_cost"] == 10.0
    records = engine.store.get("boms")
    assert len(records) == 2


def test_document_writes_markdown(tmp_path):
    engine = EngineeringAutonomy(kv_path=str(tmp_path / "d.json"),
                                 output_dir=str(tmp_path / "reports"))
    out = engine.document("Spec", "# Head\n\nbody", name="spec")
    assert out["success"] is True
    path = out["path"]
    assert path.endswith(".md")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as handle:
        assert "# Head" in handle.read()


def test_build_loop_passes_when_tests_pass(tmp_path):
    engine = EngineeringAutonomy(kv_path=str(tmp_path / "b.json"))
    out = engine.build_loop(
        "good", {"test_ok.py": "def test_ok():\n    assert True"},
        str(tmp_path / "wgood"), run_tests=True, iterations=1)
    assert out["status"] == "passed"
    assert out["success"] is True
    assert out["tests"] == 1


def test_build_loop_reports_failure_honestly(tmp_path):
    engine = EngineeringAutonomy(kv_path=str(tmp_path / "b.json"))
    out = engine.build_loop(
        "bad", {"test_bad.py": "def test_bad():\n    assert False"},
        str(tmp_path / "wbad"), run_tests=True, iterations=1)
    assert out["status"] == "failed"
    assert out["success"] is False
    assert out["history"][0]["pytest"]["failed_tests"] >= 1


def test_registry_eng_calculate(registry):
    out = registry.invoke("eng_calculate", expression="12*3")
    assert out["success"] is True
    assert out["result"] == 36.0


def test_registry_eng_analyze(registry):
    out = registry.invoke("eng_analyze",
                          requirement="build an offline, safe prototype")
    assert out["success"] is True
    assert out["requirements"]
    assert any("offline" in constraint for constraint in out["constraints"])