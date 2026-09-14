"""Feature 117 — PCB & EDA: real board, real DRC, honest fabrication gate."""

from core import pcb_eda
from core.kv import KeyValueStore


def _hermetic(tmp_path, monkeypatch):
    store = KeyValueStore(str(tmp_path / "pcb.json"))
    monkeypatch.setattr(pcb_eda, "_pcb_store", store)
    monkeypatch.setattr(pcb_eda, "_DEFAULT_OUT", str(tmp_path / "out"))
    return store


def test_create_board_blink(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    out = pcb_eda.create_board("blink", name="test_blink")
    assert out["success"] is True
    assert out["name"] == "test_blink"
    assert out["board_id"]
    assert len(out["layers"]) > 0
    assert out["path"]


def test_drc_on_created_board(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    board = pcb_eda.create_board("auto", name="drc_board")
    out = pcb_eda.drc(board["board_id"], clearance=0.2)
    assert out["status"] == "ok"
    assert "violations" in out
    assert out["violation_count"] == 0


def test_export_writes_netlist_bom_placement(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    board = pcb_eda.create_board("blink", name="export_board")
    out = pcb_eda.export_outputs(board["board_id"])
    assert out["status"] == "ok"
    for artifact in ("netlist", "bom", "placement"):
        assert artifact in out["artifacts"]


def test_fabrication_gate_is_honest(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    board = pcb_eda.create_board("sensor", name="fab_board")
    fab = tmp_path / "fab"
    fab.mkdir()
    out = pcb_eda.fabrication_check(board["board_id"], fab_dir=str(fab))
    assert out["status"] == "ok"
    assert out["fabrication_ready"] is False  # no gerbers present
    assert out["missing_files"]


def test_fabrication_gate_passes_when_gerbers_seeded(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    board = pcb_eda.create_board("blink", name="fab_pass_board")
    fab = tmp_path / "fab"
    fab.mkdir()
    first = pcb_eda.fabrication_check(board["board_id"], fab_dir=str(fab))
    assert first["fabrication_ready"] is False
    for fname in first["missing_files"]:
        (fab / fname).write_text("seeded-gerber", encoding="utf-8")
    second = pcb_eda.fabrication_check(board["board_id"], fab_dir=str(fab))
    assert second["fabrication_ready"] is True


def test_detect_lists_eda_backends(tmp_path):
    out = pcb_eda.detect()
    assert "status_code" in out
    assert "kai_backends" in out