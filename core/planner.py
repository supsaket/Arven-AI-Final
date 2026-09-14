"""Adaptive Planning & Dynamic Replanning (feature 74, Day 2).

A bounded, honest planner: plans are stored step-by-step, a "planned"
execution state is tracked, and when a step is reported blocked the planner
replans by replacing the failed step with alternatives. No execution happens
here — the planner is a coordinator, not an actor.
"""

import re
from datetime import datetime

from core.kv import KeyValueStore

_ID_RE = re.compile(r"[^a-zA-Z0-9_.\-]")


class AdaptivePlanner:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/planner.json")

    # ------------------------------------------------------------------
    def _now(self):
        return datetime.now().isoformat()

    @staticmethod
    def _slug(value):
        return _ID_RE.sub("-", str(value).strip().lower())[:60] or "plan"

    def _plans(self):
        return self.kv.get("plans", {})

    def _save(self, plans):
        self.kv.set("plans", plans)

    def _normalise_step(self, step, ref):
        if not isinstance(step, dict):
            step = {"action": str(step), "args": {}}
        step = dict(step)
        step.setdefault("ref", ref)
        step.setdefault("args", {})
        step.setdefault("status", "planned")
        return step

    # ------------------------------------------------------------------
    def create_plan(self, goal, steps, assumptions=None):
        if not isinstance(steps, list) or not steps:
            raise ValueError("plan needs a non-empty step list")
        if not goal or not str(goal).strip():
            raise ValueError("plan needs a goal")
        plan_id = self._slug(goal)
        plan = {
            "id": plan_id,
            "goal": str(goal),
            "steps": [
                self._normalise_step(s, i + 1)
                for i, s in enumerate(steps)
            ],
            "assumptions": list(assumptions or []),
            "status": "planned",
            "created_at": self._now(),
            "updated_at": self._now(),
            "replan_events": [],
            "deprecated": False,
        }
        plans = self._plans()
        plans[plan_id] = plan
        self._save(plans)
        return plan

    def get_plan(self, plan_id):
        return self._plans().get(plan_id)

    def list_plans(self):
        return sorted(self._plans().values(), key=lambda p: p["created_at"])

    def status(self, plan_id):
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        blocked = [s["ref"] for s in plan["steps"] if s.get("status") == "blocked"]
        return {
            "id": plan["id"],
            "goal": plan["goal"],
            "status": plan["status"],
            "total_steps": len(plan["steps"]),
            "remaining_steps": sum(
                1 for s in plan["steps"] if s.get("status") == "planned"),
            "blocked_steps": blocked,
            "updated_at": plan["updated_at"],
        }

    # ------------------------------------------------------------------
    def replace_step(self, plan_id, step_ref, replacements):
        """Mark a step planned->blocked and append alternative steps."""
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        for step in plan["steps"]:
            if str(step["ref"]) == str(step_ref):
                step["status"] = "blocked"
                step["blocked_at"] = self._now()
                break
        else:
            raise ValueError(f"no step ref {step_ref} in plan {plan_id}")

        alts = []
        if isinstance(replacements, list):
            items = replacements
        else:
            items = [replacements]
        if not items:
            raise ValueError("replan needs at least one alternative")
        for alt in items:
            if isinstance(alt, dict) and alt.get("ref"):
                ref = alt["ref"]
            else:
                ref = f"{step_ref}.alt"
            alts.append(self._normalise_step(alt, ref))

        plan["steps"].extend(alts)
        plan["status"] = "replanned"
        plan["updated_at"] = self._now()
        plan.setdefault("replan_events", []).append({
            "at": self._now(),
            "failed_ref": str(step_ref),
            "alternatives": [a["ref"] for a in alts],
        })
        self._save(self._plans())
        return {
            "id": plan["id"],
            "goal": plan["goal"],
            "status": plan["status"],
            "blocked_step": str(step_ref),
            "added_steps": [a["ref"] for a in alts],
        }

    # ------------------------------------------------------------------
    def complete_step(self, plan_id, step_ref):
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        for step in plan["steps"]:
            if str(step["ref"]) == str(step_ref) and \
                    step.get("status") != "blocked":
                step["status"] = "complete"
                step["completed_at"] = self._now()
                break
        remaining = [s for s in plan["steps"] if s.get("status") == "planned"]
        if not remaining:
            plan["status"] = "complete"
        plan["updated_at"] = self._now()
        self._save(self._plans())
        return plan["status"]

    def deprecate(self, plan_id):
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        plan["deprecated"] = True
        plan["status"] = "deprecated"
        plan["updated_at"] = self._now()
        self._save(self._plans())
        return plan["status"]


__all__ = ["AdaptivePlanner"]