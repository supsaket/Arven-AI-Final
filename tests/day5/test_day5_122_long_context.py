"""Feature 122 — Long-context engine: honest window, compaction, recovery."""

import os

from core import long_context

_PIPELINE = "RETRIEVE->COMPRESS->COMPACT->CONTINUE"


def test_detect_reports_honest_window():
    out = long_context.detect()
    assert out["success"] is True
    assert out["max_context"] > 0
    assert out["family"] in long_context._KNOWLEDGE


def test_process_compacts_large_input(tmp_path, monkeypatch):
    monkeypatch.setattr(long_context, "_OUT_DIR", str(tmp_path / "ckpts"))
    text = "The quick brown fox jumps over the lazy dog. " * 400
    engine = long_context.LongContextEngine(data_file=str(tmp_path / "lc.json"))
    out = engine.process(text, max_context=300, top_k=3, compress_ratio=0.4)
    assert out["success"] is True
    assert out["mode"] == "COMPACTED"
    assert out["strategy"] == _PIPELINE
    assert out["chunks"] > 1
    assert out["compressed_tokens"] < out["original_tokens"]
    assert out["retrieval_hits"]


def test_process_native_when_fits(tmp_path, monkeypatch):
    monkeypatch.setattr(long_context, "_OUT_DIR", str(tmp_path / "ckpts"))
    engine = long_context.LongContextEngine(data_file=str(tmp_path / "lc.json"))
    out = engine.process("small input fits", max_context=3000)
    assert out["mode"] == "USE_NATIVE_CONTEXT"


def test_checkpoint_and_restore_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(long_context, "_OUT_DIR", str(tmp_path / "ckpts"))
    engine = long_context.LongContextEngine(data_file=str(tmp_path / "lc.json"))
    state = {"doc": "state-payload", "n": 7}
    saved = engine.checkpoint(state, name="test_cp")
    assert saved["success"] is True
    assert os.path.exists(saved["path"])
    restored = engine.restore(saved["path"])
    assert restored["success"] is True
    assert restored["state"] == state


def test_long_document_loads_files(tmp_path, monkeypatch):
    monkeypatch.setattr(long_context, "_OUT_DIR", str(tmp_path / "ckpts"))
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha " * 400, encoding="utf-8")
    b.write_text("beta " * 400, encoding="utf-8")
    engine = long_context.LongContextEngine(data_file=str(tmp_path / "lc.json"))
    out = engine.long_document([str(a), str(b)], max_context=2000, top_k=2)
    assert out["success"] is True
    assert len(out["load"]["documents"]) == 2
    assert out["load"]["total_tokens"] > 0
    assert out["load"]["errors"] == []


def test_budget_uses_window(tmp_path):
    small = long_context.budget("x" * 500, max_context=1000)
    assert small["success"] is True
    assert small["strategy"] == "USE_NATIVE_CONTEXT"
    assert "budget_tokens" in small
    big = long_context.budget("x" * 3000, max_context=500)
    assert big["strategy"] == _PIPELINE
    assert big["remaining_tokens"] == 0


def test_status(tmp_path):
    engine = long_context.LongContextEngine(data_file=str(tmp_path / "lc.json"))
    st = engine.status()
    assert st["success"] is True
    assert "records" in st or "checkpoints" in st