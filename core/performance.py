"""Performance Optimizer / Profiling (feature 64, Day 2).

Profiler measures real wall-clock timings (perf_counter) — never fabricated —
and persists aggregate stats in a KeyValueStore. It provides ``timed``,
``report``, ``benchmark``, ``fps_estimate``, and ``hotspots``.
"""

import time
from collections import defaultdict

from core.kv import KeyValueStore


class Profiler:

    def __init__(self, kv_path=None):
        self.kv = KeyValueStore(kv_path if kv_path else "data/profiler.json")
        self._fps_window = []

    def _stats(self, label):
        key = f"perf.{label}"
        return self.kv.get(key, {
            "label": label, "count": 0, "total": 0.0, "min": None,
            "max": 0.0, "last": 0.0, "avg": 0.0,
        })

    # ------------------------------------------------------------------
    def timed(self, label, fn, *args, **kwargs):
        """Run fn measuring real perf_counter duration; record stats."""
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            duration = time.perf_counter() - start
            self._record(label, duration)
            return result, duration
        except Exception:
            duration = time.perf_counter() - start
            self._record(label, duration)
            raise

    def _record(self, label, duration):
        def update(stats):
            stats = dict(stats or self._stats(label))
            stats["label"] = label
            stats["count"] = stats.get("count", 0) + 1
            stats["total"] = stats.get("total", 0.0) + duration
            stats["avg"] = stats["total"] / stats["count"]
            stats["last"] = duration
            stats["max"] = max(stats.get("max", 0.0), duration)
            stats["min"] = duration if stats.get("min") is None else min(stats["min"], duration)
            return stats
        self.kv.update(f"perf.{label}", update, default=None)

    # ------------------------------------------------------------------
    def report(self, label):
        return dict(self._stats(label))

    def benchmark(self, label, fn, iterations=100):
        iterations = max(1, int(iterations))
        total = 0.0
        for _ in range(iterations):
            start = time.perf_counter()
            fn()
            total += time.perf_counter() - start
        duration = total / iterations
        self._record(label, duration)
        return {
            "label": label,
            "iterations": iterations,
            "avg_per_iteration": duration,
            "total": total,
        }

    # ------------------------------------------------------------------
    def fps_estimate(self, window=60):
        """Rolling FPS estimate based on real recent call intervals."""
        window = max(2, int(window))
        if len(self._fps_window) < 2:
            return {"fps": 0.0, "samples": len(self._fps_window), "note": "insufficient samples"}
        marks = self._fps_window[-window:]
        delta = marks[-1] - marks[0]
        fps = (len(marks) - 1) / delta if delta > 0 else 0.0
        return {"fps": round(fps, 2), "samples": len(marks), "note": "real measured"}

    def tick(self, now=None):
        self._fps_window.append(now if now is not None else time.perf_counter())
        if len(self._fps_window) > 5000:
            self._fps_window = self._fps_window[-1000:]

    # ------------------------------------------------------------------
    def hotspots(self, top=5):
        entries = []
        for key in self.kv.keys(prefix="perf."):
            stats = self.kv.get(key)
            if stats and stats.get("count"):
                entries.append(stats)
        entries.sort(key=lambda s: s.get("avg", 0.0), reverse=True)
        return entries[:int(top)]


__all__ = ["Profiler"]
