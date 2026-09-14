"""Feature 52 — Experiential Learning.

``ExperienceVault`` records (trigger, action, outcome, reward, tags) entries,
ranks similar experiences with real token-overlap + reward scoring, and
synthesises lessons and context hints. Honest: every score is computed from
the stored experiences — no hidden caching.
"""

import copy
import math
import re
import time

from core.kv import KeyValueStore

_KEY = "experience.vault"
_DEFAULT_PATH = "data/runtime/experience.json"


def _tokens(text):
    return re.findall(r"[a-z0-9_]+", str(text).lower())


class ExperienceVault:

    def __init__(self, path=None):
        self.store = KeyValueStore(str(path) if path else _DEFAULT_PATH)

    # ------------------------------------------------------------------
    def _vault(self):
        return list(self.store.get(_KEY) or [])

    def _save(self, vault):
        self.store.set(_KEY, vault)

    def record(self, trigger, action, outcome="success", reward=0.0, tags=None):
        outcome = str(outcome).lower()
        if outcome not in ("success", "failure"):
            raise ValueError("outcome must be 'success' or 'failure'")
        entry = {
            "id": f"exp_{time.time_ns()}",
            "ts": time.time(),
            "trigger": str(trigger),
            "action": str(action),
            "outcome": outcome,
            "reward": float(reward),
            "tags": [str(t) for t in (tags or [])],
        }
        vault = self._vault()
        vault.append(entry)
        if len(vault) > 1000:
            vault = vault[-1000:]
        self._save(vault)
        return copy.deepcopy(entry)

    def all(self):
        return copy.deepcopy(self._vault())

    # ------------------------------------------------------------------
    def similar(self, trigger, k=5):
        query_tokens = set(_tokens(trigger))
        scored = []
        for entry in self._vault():
            haystack = (
                f"{entry['trigger']} {entry['action']} {' '.join(entry['tags'])}"
            )
            overlap = len(query_tokens & set(_tokens(haystack)))
            if overlap <= 0:
                continue
            norm_overlap = overlap / max(1, len(query_tokens))
            reward_weight = 0.0
            if entry["reward"] > 0:
                reward_weight = 1.0 - math.exp(-max(0.0, entry["reward"]))
            success_bonus = 0.1 if entry["outcome"] == "success" else 0.0
            score = round(
                norm_overlap * 2.0 + reward_weight * 1.0 + success_bonus, 4
            )
            scored.append({
                "experience": copy.deepcopy(entry),
                "score": score,
                "overlap": overlap,
            })
        scored.sort(key=lambda item: (item["score"], item["experience"]["reward"]),
                    reverse=True)
        return scored[: int(k)]

    def lessons(self, topic):
        query_tokens = set(_tokens(topic))
        matched = []
        for entry in self._vault():
            haystack = (
                f"{entry['trigger']} {entry['action']} {' '.join(entry['tags'])}"
            )
            if query_tokens & set(_tokens(haystack)):
                matched.append(entry)
        successes = [e for e in matched if e["outcome"] == "success"]
        failures = [e for e in matched if e["outcome"] == "failure"]

        def top(entries, limit=3):
            ordered = sorted(
                entries, key=lambda e: (e["reward"], e["ts"]), reverse=True
            )
            return [
                {"action": e["action"], "reward": e["reward"],
                 "trigger": e["trigger"]}
                for e in ordered[:limit]
            ]

        action_aggregate = {}
        action_counts = {}
        for entry in successes:
            action_aggregate[entry["action"]] = (
                action_aggregate.get(entry["action"], 0)
                + 1 + max(0.0, entry["reward"])
            )
            action_counts[entry["action"]] = action_counts.get(entry["action"], 0) + 1
        suggested_action = None
        if action_aggregate:
            suggested_action = max(
                action_aggregate.items(), key=lambda kv: kv[1]
            )[0]
        total = len(matched)
        success_rate = round(
            len(successes) / total, 3
        ) if total else 0.0
        return {
            "topic": str(topic),
            "total": total,
            "successes": len(successes),
            "failures": len(failures),
            "success_rate": success_rate,
            "top_successes": top(successes),
            "top_failures": top(failures),
            "suggested_action": suggested_action,
            "action_counts": dict(sorted(
                action_counts.items(), key=lambda kv: -kv[1]
            )),
        }

    def context_hints(self, trigger, k=5):
        hints = []
        for ranked in self.similar(trigger, k):
            entry = ranked["experience"]
            hints.append({
                "hint": f"{entry['action']} → {entry['outcome']}",
                "action": entry["action"],
                "score": ranked["score"],
                "outcome": entry["outcome"],
                "reward": entry["reward"],
            })
        return hints


__all__ = ["ExperienceVault"]