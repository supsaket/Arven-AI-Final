"""Day 3 concurrency: guards serialize, kv stores atomically, missions lock."""

import threading

import pytest

from core.kv import KeyValueStore
from core.missions import MissionsEngine
from core.recovery import ExecutionGuard


def test_kv_concurrent_writes_all_land(tmp_path):
    kv = KeyValueStore(str(tmp_path / "kv.json"))
    errors = []

    def writer(i):
        try:
            for j in range(20):
                kv.set(f"k_{i}_{j}", i * 1000 + j)
        except Exception as exc:  # pragma: no cover - failure must surface
            errors.append(str(exc))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(kv.as_dict()) == 8 * 20
    reloaded = KeyValueStore(str(tmp_path / "kv.json"))
    assert len(reloaded.as_dict()) == 8 * 20          # durable after restart
    assert reloaded.get("k_7_19") == 7019


def test_execution_guard_parallel_workers_serialize():
    guard = ExecutionGuard()
    state = {"active": 0, "max_seen": 0}
    lock = threading.Lock()
    errors = []

    def worker():
        if not guard.acquire(("tool", "args"), timeout=5):
            errors.append("acquire failed")
            return
        try:
            with lock:
                state["active"] += 1
                state["max_seen"] = max(state["max_seen"], state["active"])
            import time
            time.sleep(0.05)
            with lock:
                state["active"] -= 1
        finally:
            guard.release(("tool", "args"))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert state["max_seen"] == 1
    assert state["active"] == 0
    assert guard.was_run(("tool", "args")) is True


def test_mission_steps_run_concurrently_under_lock(tmp_path):
    engine = MissionsEngine(path=str(tmp_path / "m.json"))
    mid = engine.create_mission("parallel", [
        {"id": "s1", "title": "one"},
        {"id": "s2", "title": "two"},
        {"id": "s3", "title": "three"},
    ])["id"]
    errors = []

    def run_step(step_id):
        try:
            out = engine.run_step(mid, step_id, fn=lambda: {"ok": True})
            if out.get("status") != "done":
                errors.append(f"{step_id}: {out}")
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

    threads = [threading.Thread(target=run_step, args=(f"s{i}",))
               for i in (1, 2, 3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    summary = engine.summary(mid)
    assert summary["steps_done"] == 3
    assert summary["progress_pct"] == 100.0


def test_guard_times_out_when_busy():
    guard = ExecutionGuard()
    assert guard.acquire(("busy", "")) is True
    assert guard.acquire(("busy", ""), timeout=0.01) is False  # no deadlock
    guard.release(("busy", ""))


def test_kv_never_partially_applies_single_key(tmp_path):
    kv = KeyValueStore(str(tmp_path / "kv2.json"))
    kv.set("point", {"x": 1, "y": 2})
    assert kv.get("point")["y"] == 2          # whole value read back intact
    kv.delete("point")
    assert kv.get("point") is None