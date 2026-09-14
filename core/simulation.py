"""Predictive Simulation & Forecasting (Day 2, feature 76).

Runs user-supplied deterministic models over a real step loop, applies
optional moving-average smoothing and a least-squares trend line, and reports
results honestly labelled as ``method: heuristic`` — never claiming accuracy
beyond the data.
"""

from datetime import datetime

from core.kv import KeyValueStore
from core.output import output_manager


class SimulationEngine:

    def __init__(self, kv=None, output_dir="Output/Simulations"):
        self.kv = kv or KeyValueStore("data/simulation.json")
        self.output_dir = output_dir
        self._models = {}

    # ------------------------------------------------------------------
    def define_model(self, name, fn):
        """Register a deterministic callable ``fn(step, params) -> float``."""
        if not callable(fn):
            raise TypeError("model must be callable fn(step, params)")
        self._models[name] = fn
        return name

    def models(self):
        return sorted(self._models)

    # ------------------------------------------------------------------
    def _series(self, fn, steps, params):
        return [fn(step, params) for step in range(int(steps))]

    def run(self, name, steps, params=None, window=None):
        fn = self._models.get(name)
        if fn is None:
            raise KeyError(f"no model '{name}'; defined: {self.models()}")
        params = params or {}
        steps = int(steps)
        raw = self._series(fn, steps, params)
        smoothed = _moving_average(raw, window) if window else list(raw)
        trend = _least_squares(smoothed)
        summary = {
            "model": name,
            "steps": steps,
            "method": "heuristic",
            "start": raw[0] if raw else 0,
            "end": raw[-1] if raw else 0,
            "min": min(raw) if raw else 0,
            "max": max(raw) if raw else 0,
            "avg": (sum(raw) / len(raw)) if raw else 0,
            "trend_slope": trend[0],
            "trend_intercept": trend[1],
        }
        outcome = {
            "model": name,
            "series": smoothed,
            "raw": raw,
            "trend": trend,
            "summary": summary,
            "method": "heuristic",
        }
        self._persist(name, outcome)
        return outcome

    # ------------------------------------------------------------------
    def sensitivity(self, name, param, values, steps, **params):
        values = list(values)
        results = []
        for value in values:
            probe = dict(params)
            probe[param] = value
            outcome = self.run(name, steps, probe)
            results.append({
                "param": param,
                "value": value,
                "summary": outcome["summary"],
                "series": outcome["series"],
            })
        return {"param": param, "values": values, "runs": results}

    # ------------------------------------------------------------------
    def report(self, name, directory=None):
        target = directory or self.output_dir
        stored = self.kv.get(f"sim_result::{name}", [])
        if not stored:
            raise KeyError(f"no stored simulation result for '{name}'")
        lines = [f"# Simulation Report — {name}",
                 f"> Generated {datetime.now().isoformat()}",
                 f"> Method: heuristic (no accuracy claim beyond input data)", ""]
        for s in stored:
            lines += [
                f"## Run ({s['steps']} steps)",
                f"- start: {s['start']}  end: {s['end']}",
                f"- min: {s['min']}  max: {s['max']}  avg: {round(s['avg'], 4)}",
                f"- trend slope: {round(s['trend_slope'], 4)}",
                "",
            ]
        content = "\n".join(lines)
        result = output_manager.write(target, f"simulation_{name}.md", content)
        return result["path"]

    # ------------------------------------------------------------------
    def _persist(self, name, outcome):
        stored = self.kv.get(f"sim_result::{name}", [])
        stored.append(outcome["summary"])
        self.kv.set(f"sim_result::{name}", stored)


def _moving_average(values, window):
    window = max(1, int(window))
    if window >= len(values):
        return list(values)
    out = []
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        window_values = values[lo:i + 1]
        out.append(sum(window_values) / len(window_values))
    return out


def _least_squares(values):
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = y_mean - slope * x_mean
    return (slope, intercept)


__all__ = ["SimulationEngine"]
