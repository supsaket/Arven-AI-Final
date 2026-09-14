"""Anomaly detection (Day 2, feature 57) — persisted via KeyValueStore.

Supported anomaly kinds:

* ``point``    — z-score deviation of a value against its rolling window
* ``threshold``— value outside declared ``min``/``max`` bounds
* ``trend``    — slope magnitude of a linear fit over the trailing window
* ``rule``     — explicit user-supplied predicate over value + history

State is honest: series with too few points report ``insufficient_data`` and
constant series report ``stationary`` (no z-score anomalies, std ~ 0).
"""

import math
import statistics
import time

from core.kv import KeyValueStore

DEFAULT_WINDOW = 10
DEFAULT_Z_LIMIT = 3.0
MAX_POINTS = 200


def _linear_slope(values):
    """Ordinary least-squares slope of y over integer x."""

    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    ex = float(sum(xs))
    ey = float(sum(values))
    exx = float(sum(x * x for x in xs))
    exy = float(sum(x * y for x, y in zip(xs, values)))
    denominator = n * exx - ex * ex
    if abs(denominator) < 1e-12:
        return 0.0
    return (n * exy - ex * ey) / denominator


def _severity(score):
    if score >= 8.0:
        return "critical"
    if score >= 5.0:
        return "high"
    if score >= 3.0:
        return "medium"
    return "low"


class AnomalyEngine:

    def __init__(self, path="data/anomaly.json", window_size=DEFAULT_WINDOW, z_limit=DEFAULT_Z_LIMIT):
        self.kv = KeyValueStore(path)
        self.window_size = int(window_size)
        self.z_limit = float(z_limit)
        self._rules = {}

    # ------------------------------------------------------------------
    def configure(self, series_id, **opts):
        key = f"anomaly.config.{series_id}"
        def merge(old):
            base = dict(old or {})
            for name, value in opts.items():
                if value is not None:
                    base[name] = value
            return base
        return self.kv.update(key, merge, default={})

    def set_bounds(self, series_id, min_value=None, max_value=None):
        return self.configure(series_id, min=min_value, max=max_value)

    def add_rule(self, series_id, name, fn, severity="medium"):
        self._rules.setdefault(series_id, {})[name] = (fn, severity)
        return True

    def _config(self, series_id):
        stored = self.kv.get(f"anomaly.config.{series_id}", {}) or {}
        return {
            "window_size": stored.get("window_size", self.window_size),
            "z_limit": stored.get("z_limit", self.z_limit),
            "trend_limit": stored.get("trend_limit"),
            "min": stored.get("min"),
            "max": stored.get("max"),
        }

    # ------------------------------------------------------------------
    def ingest(self, series_id, value, ts=None, label=None):
        value = float(value)
        ts = time.time() if ts is None else ts
        key = f"anomaly.series.{series_id}"
        def append(old):
            points = list(old or [])
            points.append({"ts": ts, "value": value, "label": label})
            return points[-MAX_POINTS:]
        self.kv.update(key, append, default=[])
        return len(self.kv.get(key, []))

    def _points(self, series_id):
        return list(self.kv.get(f"anomaly.series.{series_id}", []) or [])

    def _state(self, points, window_size):
        if len(points) < max(2, window_size):
            return "insufficient_data"
        values = [p["value"] for p in points[-window_size:]]
        if statistics.pstdev(values) <= 1e-9:
            return "stationary"
        return "active"

    # ------------------------------------------------------------------
    def detect(self, series_id):
        points = self._points(series_id)
        cfg = self._config(series_id)
        window = cfg["window_size"]
        state = self._state(points, window)
        anomalies = []

        if len(points) >= window:
            z_limit = cfg["z_limit"]
            for i in range(len(points)):
                value = points[i]["value"]
                history = [p["value"] for p in points[max(0, i - window):i]]
                if len(history) < 2:
                    continue
                std = statistics.pstdev(history)
                mean = statistics.mean(history)
                if std > 1e-9:
                    z = (value - mean) / std
                    if abs(z) >= z_limit:
                        anomalies.append({
                            "index": i,
                            "ts": points[i]["ts"],
                            "value": value,
                            "kind": "point",
                            "severity": _severity(abs(z)),
                            "score": round(abs(z), 4),
                            "reason": f"z-score {abs(z):.2f} >= {z_limit:g}",
                            "label": points[i].get("label"),
                        })

            trend_limit = cfg["trend_limit"]
            if trend_limit is not None:
                for i in range(window - 1, len(points)):
                    chunk = [p["value"] for p in points[i - window + 1:i + 1]]
                    slope = _linear_slope(chunk)
                    if abs(slope) > trend_limit:
                        anomalies.append({
                            "index": i,
                            "ts": points[i]["ts"],
                            "value": points[i]["value"],
                            "kind": "trend",
                            "severity": _severity(abs(slope) / trend_limit),
                            "score": round(abs(slope) / trend_limit, 4),
                            "reason": f"window slope {slope:.3f} beyond limit {trend_limit:g}",
                            "label": points[i].get("label"),
                        })

        lo, hi = cfg["min"], cfg["max"]
        for i in range(len(points)):
            value = points[i]["value"]
            if lo is not None and value < lo:
                excess = lo - value
            elif hi is not None and value > hi:
                excess = value - hi
            else:
                continue
            scale = 1.0
            if lo is not None and hi is not None and hi > lo:
                scale = max(scale, hi - lo)
            ratio = excess / scale
            anomalies.append({
                "index": i,
                "ts": points[i]["ts"],
                "value": value,
                "kind": "threshold",
                "severity": _severity(2.0 + ratio),
                "score": round(1.0 + ratio, 4),
                "reason": f"value {value:g} outside bounds [{lo}, {hi}]",
                "label": points[i].get("label"),
            })

        for name, (fn, severity) in (self._rules.get(series_id, {}) or {}).items():
            for i in range(len(points)):
                history = [p["value"] for p in points[max(0, i - window):i]]
                try:
                    fired = bool(fn(points[i]["value"], history, series_id))
                except Exception:
                    fired = False
                if fired:
                    anomalies.append({
                        "index": i,
                        "ts": points[i]["ts"],
                        "value": points[i]["value"],
                        "kind": "rule",
                        "name": name,
                        "severity": severity,
                        "score": 1.0,
                        "reason": f"rule '{name}' fired",
                        "label": points[i].get("label"),
                    })

        anomalies.sort(key=lambda a: (a["index"], a["kind"]))
        result = {
            "series_id": series_id,
            "state": state,
            "checked": len(points),
            "anomalies": anomalies,
        }
        self.kv.set(f"anomaly.last_detect.{series_id}", result)
        return result

    # ------------------------------------------------------------------
    def report(self, series_id):
        points = self._points(series_id)
        cfg = self._config(series_id)
        window = cfg["window_size"]
        values = [p["value"] for p in points]
        detected = self.detect(series_id)

        by_kind = {}
        by_severity = {}
        for item in detected["anomalies"]:
            by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
            by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1

        trailing = values[-window:] if len(values) >= window else values
        last_slope = _linear_slope(trailing) if len(trailing) >= 2 else None

        return {
            "series_id": series_id,
            "points": len(points),
            "window": window,
            "state": detected["state"],
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": statistics.mean(values) if values else None,
            "std": statistics.pstdev(values) if values else None,
            "last_slope": last_slope,
            "by_kind": by_kind,
            "by_severity": by_severity,
            "anomalies": len(detected["anomalies"]),
        }


__all__ = ["AnomalyEngine"]