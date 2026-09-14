"""Day 3 recovery hardening: undo rollback + backup integrity + guard (T5/T7)."""

import threading

import pytest

from core.kv import KeyValueStore
from core.recovery import (
    ExecutionGuard, RecoveryAction, classify, run_tool_with_recovery)
from core.undo import TransactionManager


# ----------------------------------------------------------------------
# Recovery engine (feature 74/102 foundations)
# ----------------------------------------------------------------------

def test_classify_maps_results_and_errors():
    assert classify(RecoveryAction("ok")) == "ok"
    assert classify({"status": "ok"}) == "ok"
    assert classify({"status": "retry"}) == "retryable"
    assert classify({"status": "blocked"}) == "blocked"
    assert classify({"status": "weird"}) == "failed"
    assert classify(TimeoutError("boom")) == "retryable"
    assert classify(OSError(11001, "nxdomain")) == "retryable"
    assert classify(ValueError("bad")) == "failed"
    assert classify(True) == "ok"


def test_execution_guard_at_most_once():
    guard = ExecutionGuard()
    assert guard.acquire(("tool", "args")) is True
    assert guard.acquire(("tool", "args"), timeout=0.05) is False
    assert guard.is_active(("tool", "args")) is True
    guard.release(("tool", "args"))
    assert guard.is_active(("tool", "args")) is False
    assert guard.was_run(("tool", "args")) is True
    assert guard.acquire(("tool", "args")) is True
    guard.release(("tool", "args"))


def test_recovery_safe_retries_transient_then_success():
    attempts = {"n": 0}

    def flaky(**kw):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError(11001, "transient")
        return {"status": "ok", "success": True}

    out = run_tool_with_recovery(flaky, attempts=4)
    assert out["success"] is True
    assert out["retries"] == 3
    assert attempts["n"] == 3


def test_recovery_exhausted_is_honest():
    def always_fails(**kw):
        raise ValueError("nope")

    out = run_tool_with_recovery(always_fails, attempts=2)
    assert out["success"] is False
    assert out["status"] == "error"
    assert "after 2 attempt" in out["message"]
    assert out["recovery"] == "exhausted"


def test_recovery_destructive_runs_exactly_once():
    calls = {"n": 0}

    def destructive(**kw):
        calls["n"] += 1
        raise OSError(11001, "boom")

    out = run_tool_with_recovery(destructive, attempts=5, destructive=True)
    assert calls["n"] == 1
    assert out["success"] is False
    assert out["recovery"] == "no_retry_destructive"


# ----------------------------------------------------------------------
# Undo / transactions (feature 102)
# ----------------------------------------------------------------------

def test_rollback_restores_every_preimage(tmp_path):
    kv = KeyValueStore(str(tmp_path / "undo.json"))
    kv.set("a", "old-a")
    kv.set("b", "old-b")
    txn = TransactionManager(kv=kv)
    rid = txn.begin()["id"]
    txn.op(rid, "a", "new-a")
    txn.op(rid, "a", "newer-a")
    txn.op(rid, "b", "new-b")
    txn.op(rid, "c", "added-c")
    assert kv.get("a") == "newer-a"
    result = txn.rollback(rid)
    assert result["status"] == "rolled_back"
    assert result["keys_restored"] == 3
    assert kv.get("a") == "old-a"
    assert kv.get("b") == "old-b"
    assert kv.get("c") is None


def test_commit_is_final(tmp_path):
    kv = KeyValueStore(str(tmp_path / "undo2.json"))
    kv.set("x", 1)
    txn = TransactionManager(kv=kv)
    rid = txn.begin()["id"]
    txn.op(rid, "x", 2)
    out = txn.commit(rid)
    assert out["status"] == "committed"
    assert out["ops_committed"] == 1
    assert kv.get("x") == 2
    assert txn.status(rid)["status"] == "committed"


def test_partial_failure_rollback_is_honest(tmp_path):
    class FailingKV(KeyValueStore):
        fail_set = None

        def set(self, key, value):
            if self.fail_set and key in self.fail_set:
                raise OSError("storage write failed (simulated)")
            return super().set(key, value)

    kv = FailingKV(str(tmp_path / "undo3.json"))
    kv.set("good", "old-good")
    kv.set("bad", "old-bad")
    txn = TransactionManager(kv=kv)
    rid = txn.begin()["id"]
    txn.op(rid, "good", "new-good")
    txn.op(rid, "bad", "new-bad")
    kv.fail_set = {"bad"}
    result = txn.rollback(rid)
    assert result["status"] == "rolled_back"
    assert result["keys_restored"] == 1
    assert result["keys_failed"] == 1
    assert "could not be restored" in result["message"]
    assert kv.get("good") == "old-good"      # restored
    assert kv.get("bad") == "new-bad"        # honestly left


def test_op_on_closed_transaction_rejected(tmp_path):
    kv = KeyValueStore(str(tmp_path / "undo4.json"))
    txn = TransactionManager(kv=kv)
    rid = txn.begin()["id"]
    txn.commit(rid)
    with pytest.raises(ValueError, match="committed"):
        txn.op(rid, "k", "v")


def test_unknown_transaction_raises(tmp_path):
    txn = TransactionManager(kv=KeyValueStore(str(tmp_path / "undo5.json")))
    with pytest.raises(KeyError):
        txn.status("missing-txn")
    with pytest.raises(KeyError):
        txn.rollback("missing-txn")


def test_active_transactions_lists_only_active(tmp_path):
    kv = KeyValueStore(str(tmp_path / "undo6.json"))
    txn = TransactionManager(kv=kv)
    rid1 = txn.begin("one")["id"]
    rid2 = txn.begin("two")["id"]
    txn.commit(rid2)
    active = [t["id"] for t in txn.active_transactions()]
    assert rid1 in active
    assert rid2 not in active


# ----------------------------------------------------------------------
# Backup integrity (feature 61)
# ----------------------------------------------------------------------

def _new_backup(tmp_path):
    from core.backup import BackupManager
    ws = tmp_path / "ws"
    (ws / "data").mkdir(parents=True)
    (ws / "data" / "a.txt").write_text("baseline", encoding="utf-8")
    return BackupManager(workspace_root=str(ws), output_root=str(tmp_path / "out"))


def test_rotate_archives_and_never_deletes(tmp_path):
    mgr = _new_backup(tmp_path)
    ids = [mgr.snapshot(f"r{i}")["id"] for i in range(3)]
    assert len(mgr.list_snapshots()) == 3
    out = mgr.rotate(keep=1)
    assert len(out["archived"]) == 2
    assert len(out["kept"]) == 1
    archive_root = mgr.backup_root / "_archive"
    for snap_id in out["archived"]:
        assert (archive_root / snap_id / "manifest.json").exists()
    # nothing was deleted: archived snapshots still contain data files
    for snap_id in out["archived"]:
        assert (archive_root / snap_id / "data" / "a.txt").read_text() == "baseline"


def test_snapshot_verify_tamper_detected(tmp_path):
    mgr = _new_backup(tmp_path)
    snap_id = mgr.snapshot("tamper")["id"]
    ok = mgr.verify(snap_id)
    assert ok["status"] == "AVAILABLE"
    assert ok["verified"] is True
    snap_dir = mgr.backup_root / snap_id
    (snap_dir / "data" / "a.txt").write_text("evil", encoding="utf-8")
    bad = mgr.verify(snap_id)
    assert bad["status"] == "FAILED"
    assert bad["verified"] is False
    assert bad["mismatches"][0]["error"] == "checksum_mismatch"


def test_restore_unknown_snapshot_refused(tmp_path):
    mgr = _new_backup(tmp_path)
    out = mgr.restore("no_such_snapshot", str(tmp_path / "t"),
                      confirmed=True)
    assert out["status"] == "FAILED"
    assert out["restored"] is False


def test_restore_refuses_unconfirmed(tmp_path):
    mgr = _new_backup(tmp_path)
    snap_id = mgr.snapshot("gated")["id"]
    out = mgr.restore(snap_id, str(tmp_path / "t"))
    assert out["status"] == "FAILED"
    assert "confirmation required" in out["message"]


# ----------------------------------------------------------------------
# Guard concurrency (feature 102 foundation)
# ----------------------------------------------------------------------

def test_guard_serialises_concurrent_access():
    guard = ExecutionGuard()
    state = {"holder": None, "max_parallel": 0, "now": 0}
    state["lock"] = threading.Lock()
    errors = []

    def worker(name):
        if not guard.acquire(("x", "y"), timeout=2):
            errors.append(name)
            return
        try:
            with state["lock"]:
                state["now"] += 1
                state["max_parallel"] = max(
                    state["max_parallel"], state["now"])
                state["holder"] = name
            import time
            time.sleep(0.05)
            with state["lock"]:
                state["now"] -= 1
        finally:
            guard.release(("x", "y"))

    threads = [threading.Thread(target=worker, args=(f"w{i}",))
               for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert state["max_parallel"] == 1


def test_guard_disallows_reentrant_second_acquirer():
    guard = ExecutionGuard()
    assert guard.acquire(("k", "")) is True
    assert guard.acquire(("k", ""), timeout=0.02) is False
    guard.release(("k", ""))