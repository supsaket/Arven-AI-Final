"""Contingency & Impact Analysis (Day 2, feature 104).

Impact scoring with real likelihood*severity math, stored fallback plans,
side-effect-free dry-runs, and a supervision gate that refuses to execute
external fallback actions unless they are confirmed and require no privileged
side effects.
"""

from datetime import datetime

from core.kv import KeyValueStore


class ContingencyPlanner:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/contingency.json")

    # ------------------------------------------------------------------
    def _now(self):
        return datetime.now().isoformat()

    def _plans(self):
        return self.kv.get("fallback_plans", {})

    # ------------------------------------------------------------------
    def impact_matrix(self, change, affected, likelihood, severity):
        likelihood = max(0.0, min(1.0, float(likelihood)))
        severity = max(0.0, min(1.0, float(severity)))
        impact = round(likelihood * severity, 4)
        priority = "high" if impact >= 0.6 else "medium" if impact >= 0.3 else "low"
        entry = {
            "change": change,
            "affected": affected,
            "likelihood": likelihood,
            "severity": severity,
            "impact": impact,
            "priority": priority,
            "at": self._now(),
        }
        rows = self.kv.get("impact_matrix", [])
        rows.append(entry)
        self.kv.set("impact_matrix", rows)
        return entry

    def impact_rows(self):
        return self.kv.get("impact_matrix", [])

    # ------------------------------------------------------------------
    def fallback_plan(self, trigger, actions):
        plans = self._plans()
        plan = {
            "id": trigger,
            "trigger": trigger,
            "actions": [self._normalise_action(a) for a in actions],
            "created_at": self._now(),
            "last_run": None,
        }
        plans[trigger] = plan
        self.kv.set("fallback_plans", plans)
        return plan

    @staticmethod
    def _normalise_action(action):
        if isinstance(action, dict):
            base = dict(action)
        else:
            base = {"name": str(action), "description": str(action)}
        base.setdefault("requires_confirmation", False)
        base.setdefault("external", False)
        if base.get("external"):
            base["requires_confirmation"] = True
        return base

    def get_plan(self, trigger):
        return self._plans().get(trigger)

    # ------------------------------------------------------------------
    def dry_run(self, plan):
        """Ordered transcript; never executes anything."""
        actions = plan["actions"] if isinstance(plan, dict) else \
            self.get_plan(str(plan))
        if actions is None:
            raise KeyError(f"no fallback plan for '{plan}'")
        transcript = []
        for action in actions:
            transcript.append({
                "action": action.get("name"),
                "external": bool(action.get("external")),
                "requires_confirmation": bool(
                    action.get("requires_confirmation")),
                "would_execute": not (action.get("external")
                                      and action.get("requires_confirmation")),
            })
        return {"plan": plan.get("trigger"), "ordered": transcript,
                "side_effects": False}

    # ------------------------------------------------------------------
    def execute_fallback(self, trigger, confirmed=False, by=None):
        plan = self.get_plan(trigger)
        if plan is None:
            raise KeyError(f"no fallback plan for '{trigger}'")
        executed = []
        refused = []
        for action in plan["actions"]:
            if action.get("external"):
                if not confirmed:
                    refused.append({
                        "action": action.get("name"),
                        "status": "REFUSED",
                        "reason": "requires confirmation (external side effect)",
                    })
                    continue
                refused.append({
                    "action": action.get("name"),
                    "status": "REFUSED",
                    "reason": "external backend not available in this build",
                })
                continue
            executed.append({
                "action": action.get("name"),
                "status": "dry-run-only",
                "message": "local action recorded; no side effects performed",
            })
        plan["last_run"] = self._now()
        self.kv.set("fallback_plans", self._plans())
        return {"trigger": trigger, "executed": executed, "refused": refused}

    # ------------------------------------------------------------------
    def supervise(self, plans=None):
        plan_keys = plans or sorted(self._plans())
        results = []
        for trigger in plan_keys:
            plan = self.get_plan(trigger)
            if plan is None:
                results.append({"trigger": trigger, "status": "missing"})
                continue
            last_run = plan.get("last_run")
            results.append({
                "trigger": trigger,
                "status": "active" if last_run else "stale",
                "last_run": last_run,
                "actions": len(plan["actions"]),
                "external_actions": sum(
                    1 for a in plan["actions"] if a.get("external")),
            })
        return {"plans": results,
                "active": [r for r in results if r["status"] == "active"],
                "stale": [r for r in results if r["status"] == "stale"]}


__all__ = ["ContingencyPlanner"]