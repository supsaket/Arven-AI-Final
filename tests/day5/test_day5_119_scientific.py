"""Feature 119 — Scientific engine: real numerics, honest dependency gating."""

from core import scientific


def test_compute_linear_regression(tmp_path, monkeypatch):
    monkeypatch.setattr(scientific, "_DEFAULT_KV", str(tmp_path / "sci.json"))
    monkeypatch.setattr(scientific, "_DEFAULT_OUT", str(tmp_path / "out"))
    out = scientific.compute("linear_regression",
                             data=[0, 1, 2, 3, 4],
                             params={"y": [1, 3, 5, 7, 9]})
    assert out["success"] is True
    res = out["output"]["result"]
    assert res["slope"] == 2.0
    assert res["intercept"] == 1.0
    assert res["r2"] == 1.0


def test_simpson_integral_and_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(scientific, "_DEFAULT_KV", str(tmp_path / "sci.json"))
    out = scientific.compute("simpson_integral",
                             data=[0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100])
    assert out["success"] is True
    val = scientific.validate("simpson_integral", spec={"freq": 2.0},
                              tolerance=0.001)
    assert val["verdict"] in ("PASS", "FAIL")
    assert "error" in val


def test_dft_peaks_and_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(scientific, "_DEFAULT_KV", str(tmp_path / "sci.json"))
    monkeypatch.setattr(scientific, "_DEFAULT_OUT", str(tmp_path / "out"))
    out = scientific.compute("dft_magnitudes",
                             data=[1.0, 2.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0])
    assert out["success"] is True
    assert "dominant_bin" in out["output"]
    assert "magnitudes" in out["output"]
    flow = scientific.workflow(
        "integrate a sine-squared wave", dataset=None,
        params={"method": "simpson_integral", "validate": True})
    assert flow["success"] is True
    assert flow["method"] == "simpson_integral"
    assert flow["validation"]["verdict"] in ("PASS", "FAIL")


def test_unknown_method_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(scientific, "_DEFAULT_KV", str(tmp_path / "sci.json"))
    out = scientific.compute("perpetual_motion")
    assert out["success"] is False
    assert "invalid" in out.get("status", "")


def test_analyze_persists_record(tmp_path, monkeypatch):
    monkeypatch.setattr(scientific, "_DEFAULT_KV", str(tmp_path / "sci.json"))
    out = scientific.analyze("quantum soup", note="hermetic")
    assert out["success"] is True
    assert out["record"]["topic"] == "quantum soup"


def test_detect_lists_runtime(tmp_path):
    out = scientific.detect()
    assert out["success"] is True
    present = out.get("present")
    if isinstance(present, dict):
        for module in ("numpy", "scipy", "sympy"):
            assert module in present
    else:
        for module in ("numpy", "scipy", "sympy"):
            assert module in present