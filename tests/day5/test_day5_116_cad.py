"""Feature 116 — CAD & 3D: real meshes, round-trips, honest reconstruction."""

import json

from core import cad_3d


def test_make_sphere_writes_stl(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_3d, "_OUT", str(tmp_path))
    out = cad_3d.make("sphere", name="unit_sphere")
    assert out["success"] is True
    assert out["kind"] == "sphere"
    assert out["facets"] > 1
    assert out["path"]


def test_make_box_writes_stl_with_validated_dims(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_3d, "_OUT", str(tmp_path))
    out = cad_3d.make("box", name="cube", size=1.0)
    assert out["success"] is True
    parsed = cad_3d.parse_stl(out["path"])
    assert len(parsed["facets"]) == out["facets"]
    assert cad_3d.inspect(out["path"])["status"] == "ok"
    validated = cad_3d.validate(out["path"], {"x": 1.0, "y": 1.0, "z": 1.0},
                                tolerance=0.05)
    assert validated["result"] == "PASS"
    assert validated["topology"]["watertight"] is True
    assert validated["dimensions_conform"] is True


def test_export_converts_stl_to_obj(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_3d, "_OUT", str(tmp_path))
    made = cad_3d.make("box", name="cube", size=1.0)
    exported = cad_3d.export_object(made["path"])
    assert exported["success"] is True
    reread = cad_3d.parse_obj(exported["path"])
    assert reread["facet_count"] == made["facets"]
    assert reread["status"] == "ok"


def test_hull_reconstruction_from_point_cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_3d, "_OUT", str(tmp_path))
    cloud = [[0, 0, 0], [1, 0, 0], [0, 1, 0],
             [0, 0, 1], [0.5, 0.5, 0.5]]
    source = tmp_path / "cloud.json"
    source.write_text(json.dumps(cloud), encoding="utf-8")
    out = cad_3d.reconstruct("hull", source=str(source), name="tetra")
    assert out["success"] is True
    assert out["mode"] == "hull"
    assert out["facets"] >= 4
    assert "algorithmic convex hull" in out["type"]


def test_photogrammetry_is_honest_when_cv_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_3d, "_OUT", str(tmp_path))
    out = cad_3d.reconstruct("photogrammetry", source=str(tmp_path))
    assert out["success"] is False
    assert out["status"] in ("DEPENDENCY_MISSING", "CAD_MISSING",
                             "CAPABILITY_UNSUPPORTED")


def test_detect_lists_tooling_and_sources(tmp_path):
    out = cad_3d.detect()
    assert out["status_code"] in ("ok", "CAD_MISSING")
    assert isinstance(out["cad_backends"], list)
    assert "probes" in out