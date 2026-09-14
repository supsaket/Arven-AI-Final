"""Feature 53 — Decision Support.

``DecisionEngine`` stores weighted criteria (+benefit / -cost), options with
per-criterion scores, and ``evaluate()`` computes min-max normalised, weighted
totals with a recommendation and a spread-based confidence. Every evaluation
is logged and persisted. Real arithmetic; the recommendation is informational
only.
"""

import time

from core.kv import KeyValueStore

_CRIT_KEY = "decisions.criteria"
_OPT_KEY = "decisions.options"
_LOG_KEY = "decisions.log"
_PC_KEY = "decisions.proscons"
_DEFAULT_PATH = "data/runtime/decisions.json"


class DecisionEngine:

    def __init__(self, path=None):
        self.store = KeyValueStore(str(path) if path else _DEFAULT_PATH)

    # ------------------------------------------------------------------
    def criteria(self):
        return dict(self.store.get(_CRIT_KEY) or {})

    def options(self):
        return dict(self.store.get(_OPT_KEY) or {})

    # ------------------------------------------------------------------
    def add_criteria(self, name, weight, direction="benefit"):
        name = str(name).strip()
        if not name:
            raise ValueError("criteria name must be non-empty")
        weight = float(weight)
        if weight <= 0:
            raise ValueError("criteria weight must be positive")
        direction = str(direction).strip().lower()
        if direction in ("+", "benefit"):
            direction = "benefit"
        elif direction in ("-", "cost"):
            direction = "cost"
        else:
            raise ValueError("direction must be benefit(+/+) or cost(-/-)")
        criteria = self.criteria()
        criteria[name] = {"weight": weight, "direction": direction}
        self.store.set(_CRIT_KEY, criteria)
        return dict(criteria[name])

    def add_option(self, name, scores):
        name = str(name).strip()
        if not name:
            raise ValueError("option name must be non-empty")
        scores = dict(scores or {})
        known = set(self.criteria())
        unknown = [k for k in scores if k not in known]
        if unknown:
            raise ValueError(f"option '{name}' references unknown criteria: {unknown}")
        options = self.options()
        options[name] = scores
        self.store.set(_OPT_KEY, options)
        return dict(options[name])

    # ------------------------------------------------------------------
    def evaluate(self):
        criteria = self.criteria()
        options = self.options()
        if not criteria:
            raise ValueError("no criteria defined")
        if not options:
            raise ValueError("no options defined")

        info = {}
        normalized = {}
        for cname, criterion in criteria.items():
            values = []
            for scores in options.values():
                value = scores.get(cname)
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    continue
            if values:
                info[cname] = {
                    "weight": criterion["weight"],
                    "direction": criterion["direction"],
                    "min": min(values),
                    "max": max(values),
                }
            else:
                info[cname] = {
                    "weight": criterion["weight"],
                    "direction": criterion["direction"],
                    "min": 0.0,
                    "max": 0.0,
                }
            for oname, scores in options.items():
                try:
                    number = float(scores.get(cname))
                except (TypeError, ValueError):
                    normalized.setdefault(oname, {})[cname] = 0.0
                    continue
                low = info[cname]["min"]
                high = info[cname]["max"]
                if high == low:
                    nscore = 1.0
                elif criterion["direction"] == "benefit":
                    nscore = (number - low) / (high - low)
                else:
                    nscore = (high - number) / (high - low)
                normalized.setdefault(oname, {})[cname] = round(nscore, 6)

        weight_sum = sum(c["weight"] for c in criteria.values()) or 1.0
        totals = {}
        for oname in options:
            total = 0.0
            for cname, criterion in criteria.items():
                total += criterion["weight"] * normalized.get(oname, {}).get(cname, 0.0)
            totals[oname] = round(total / weight_sum, 6)

        ranked = sorted(totals.items(), key=lambda kv: -kv[1])
        top_name, top_score = ranked[0]
        spread = (ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else 0.0
        confidence = 0.0
        if len(ranked) > 1 and top_score > 0:
            confidence = round(min(1.0, spread / top_score), 4)

        result = {
            "criteria": info,
            "normalized": normalized,
            "scores": totals,
            "recommendation": {"name": top_name, "score": top_score},
            "spread": round(spread, 6),
            "confidence": confidence,
        }
        self._log(result)
        return result

    def _log(self, result):
        entries = list(self.store.get(_LOG_KEY) or [])
        entries.append({
            "ts": time.time(),
            "criteria": self.criteria(),
            "options": self.options(),
            "recommendation": result["recommendation"],
            "scores": dict(result["scores"]),
            "confidence": result["confidence"],
        })
        if len(entries) > 200:
            entries = entries[-200:]
        self.store.set(_LOG_KEY, entries)

    def log(self):
        return list(self.store.get(_LOG_KEY) or [])

    # ------------------------------------------------------------------
    def pros_cons(self, topic, pros=None, cons=None):
        topic = str(topic)
        store = dict(self.store.get(_PC_KEY) or {})
        if pros is None and cons is None:
            return store.get(topic, {"topic": topic, "pros": [], "cons": []})
        entry = store.get(topic, {"topic": topic, "pros": [], "cons": []})
        if pros is not None:
            merged = list(entry["pros"]) + [str(p) for p in pros]
            entry["pros"] = list(dict.fromkeys(merged))
        if cons is not None:
            merged = list(entry["cons"]) + [str(c) for c in cons]
            entry["cons"] = list(dict.fromkeys(merged))
        store[topic] = entry
        self.store.set(_PC_KEY, store)
        return entry


__all__ = ["DecisionEngine"]