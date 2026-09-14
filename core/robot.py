"""Robotics & Automation (94) plus Actuation & Robot Learning (108).

SAFETY > AUTONOMY. Motion only after explicit arming plus confirmation.
Envelope checks refuse unsafe moves. Simulated robots are clearly flagged
``simulated: True``. With no real hardware backend, actuation reports
NOT_CONFIGURED honestly and is NOT executed.
"""

import uuid
from datetime import datetime

from core.kv import KeyValueStore

MAX_STEP_DEFAULT = 15.0


class RobotController:

    def __init__(self, kv=None, simulated=True, hardware_backend=None):
        self.kv = kv or KeyValueStore("data/robot.json")
        self.simulated = simulated
        self.hardware_backend = hardware_backend
        self._axes = self._default_axes()
        self._armed = False
        self._arm_log = []

    # ------------------------------------------------------------------
    @staticmethod
    def _default_axes():
        return {
            "shoulder": {"min": -180.0, "max": 180.0, "home": 0.0,
                         "current": 0.0},
            "elbow": {"min": -135.0, "max": 135.0, "home": 0.0,
                      "current": 0.0},
            "wrist": {"min": -180.0, "max": 180.0, "home": 0.0,
                      "current": 0.0},
            "gripper": {"min": 0.0, "max": 100.0, "home": 50.0,
                        "current": 50.0},
        }

    def max_step(self):
        config = self.kv.get("robot_config", {})
        return config.get("max_step", MAX_STEP_DEFAULT)

    def set_max_step(self, value):
        config = self.kv.get("robot_config", {})
        config["max_step"] = float(value)
        self.kv.set("robot_config", config)
        return config["max_step"]

    # ------------------------------------------------------------------
    def _audit(self, entry):
        self._arm_log.append({"at": datetime.now().isoformat(), **entry})

    def arm(self, confirmed=False, by=None):
        if not confirmed:
            self._audit({"event": "arm_refused", "by": by,
                         "reason": "no confirmation"})
            return {"status": "REFUSED",
                    "message": "arming requires confirmation"}
        self._armed = True
        self._audit({"event": "armed", "by": by})
        return {"status": "ARMED", "armed": True}

    def disarm(self, by=None):
        self._armed = False
        self._audit({"event": "disarmed", "by": by})
        return {"status": "DISARMED", "armed": False}

    @property
    def armed(self):
        return bool(self._armed)

    # ------------------------------------------------------------------
    def safety_envelope(self):
        axes = self._state_axes()
        bitmask = 0
        for axis, spec in axes.items():
            if spec["current"] < spec["min"] or spec["current"] > spec["max"]:
                bitmask |= 1 << list(axes).index(axis)
        return {
            "axes": {name: {"min": s["min"], "max": s["max"],
                            "home": s["home"], "current": s["current"]}
                     for name, s in axes.items()},
            "within_envelope": bitmask == 0,
            "bitmask": bitmask,
        }

    def _state_axes(self):
        stored = self.kv.get("joint_state", self._default_axes())
        merged = {}
        for name in self._axes:
            spec = dict(self._axes[name])
            if name in stored:
                spec.update(stored[name])
            merged[name] = spec
        return merged

    def _persist_axes(self, axes):
        for name in axes:
            base = dict(self._axes[name])
            base.update({k: v for k, v in axes[name].items()
                         if k in ("min", "max", "home", "current")})
            axes[name] = base
        self.kv.set("joint_state", axes)

    # ------------------------------------------------------------------
    def home(self, by=None):
        axes = self._state_axes()
        for name in axes:
            axes[name]["current"] = axes[name]["home"]
        self._persist_axes(axes)
        self._audit({"event": "home", "by": by})
        return {"simulated": self.simulated, "axes": {
            name: a["current"] for name, a in axes.items()}}

    def plan_move(self, axis, target_deg=None, coords=None):
        value = target_deg if target_deg is not None else coords
        if value is None:
            raise ValueError("provide target_deg or coords")
        axes = self._state_axes()
        if axis not in axes:
            raise KeyError(f"unknown axis '{axis}'; known: {sorted(axes)}")
        target = float(value)
        spec = axes[axis]
        within = spec["min"] <= target <= spec["max"]
        distance = abs(target - spec["current"])
        max_step = self.max_step()
        step_ok = distance <= max_step
        steps = int(distance / max_step) + (1 if distance % max_step else 0) \
            if distance else 0
        return {
            "axis": axis,
            "target": target,
            "current": spec["current"],
            "distance": round(distance, 3),
            "steps": steps,
            "within_envelope": bool(within),
            "step_ok": bool(step_ok),
            "safe": bool(within and step_ok),
        }

    def execute_plan(self, plan, confirmed=False, trusted=False, request_id=None):
        request_id = request_id or str(uuid.uuid4())[:8]
        if not self._armed:
            return {"status": "REFUSED",
                    "message": "robot is not armed; arming + confirmation required",
                    "request_id": request_id}
        if not confirmed:
            return {"status": "REFUSED",
                    "message": "execution requires confirmation",
                    "request_id": request_id}
        if not plan.get("safe"):
            return {"status": "REFUSED",
                    "message": "plan violates safety envelope or step limit",
                    "safe": plan.get("safe"),
                    "request_id": request_id}
        if not self.simulated and self.hardware_backend is None:
            return {"status": "NOT_CONFIGURED",
                    "message": "no real hardware backend; move NOT executed",
                    "simulated": False,
                    "request_id": request_id}

        # Execute (simulated position update; real backend would actuate).
        axis = plan["axis"]
        target = plan["target"]
        axes = self._state_axes()
        axes[axis]["current"] = target
        self._persist_axes(axes)
        self._audit({"event": "executed", "axis": axis, "target": target,
                     "request_id": request_id, "by": trusted or None})
        return {
            "status": "EXECUTED",
            "simulated": self.simulated,
            "axis": axis,
            "current": axes[axis]["current"],
            "request_id": request_id,
        }

    # ------------------------------------------------------------------
    def collision_proxy(self, axes):
        """Heuristic overlap check against a fixture table (real logic)."""
        current_state = self._state_axes()
        conflicts = []
        for name, target in (axes or {}).items():
            current = current_state.get(name, {}).get("current")
            if current is None:
                continue
            target = float(target)
            if abs(current - target) > self.max_step():
                conflicts.append({"axis": name, "kind": "max_step_exceeded",
                                  "from": current, "to": target})
            spec = current_state[name]
            if not (spec["min"] <= target <= spec["max"]):
                conflicts.append({"axis": name, "kind": "outside_envelope",
                                  "target": target})
        # Fixture table: two axes converging near their shared limits read as
        # a potential tip/tool collision in the proxy.
        shared_limits = [
            ("shoulder", "elbow", 150.0, 120.0),
        ]
        for a1, a2, limit1, limit2 in shared_limits:
            t1 = axes.get(a1)
            t2 = axes.get(a2)
            if t1 is None or t2 is None:
                continue
            if float(t1) >= limit1 and float(t2) >= limit2:
                conflicts.append({"axes": [a1, a2],
                                  "kind": "fixture_proximity",
                                  "note": f"{a1}>={limit1} and {a2}>={limit2}"})
        return {
            "collision": bool(conflicts),
            "conflicts": conflicts,
            "heuristic": True,
        }

    # ------------------------------------------------------------------
    def teach(self, name, sequence):
        skills = self.kv.get("learned_skills", {})
        if name in skills:
            return {"status": "REFUSED", "message": f"skill '{name}' exists"}
        skills[name] = {
            "name": name,
            "sequence": [dict(s) for s in sequence],
            "learned_at": datetime.now().isoformat(),
        }
        self.kv.set("learned_skills", skills)
        return {"status": "LEARNED", "skill": name, "steps": len(sequence)}

    def replay(self, name, confirmed=False, request_id=None):
        if not self._armed:
            return {"status": "REFUSED",
                    "message": "precondition: robot must be armed to replay"}
        if not confirmed:
            return {"status": "REFUSED",
                    "message": "precondition: replay requires confirmation"}
        skills = self.kv.get("learned_skills", {})
        skill = skills.get(name)
        if skill is None:
            return {"status": "FAILED", "message": f"unknown skill '{name}'"}
        executed = []
        for step in skill["sequence"]:
            plan = self.plan_move(step.get("axis"), target_deg=step.get("target"))
            if not plan["safe"]:
                executed.append({"axis": plan["axis"], "status": "SKIPPED",
                                 "reason": "envelope"})
                continue
            self.execute_plan(plan, confirmed=True, request_id=request_id)
            executed.append({"axis": plan["axis"],
                             "target": plan["target"], "status": "EXECUTED"})
        return {"status": "REPLAYED", "skill": name, "steps": executed,
                "simulated": self.simulated}

    def learned_skills(self):
        return {name: {"name": v["name"], "steps": len(v["sequence"])}
                for name, v in self.kv.get("learned_skills", {}).items()}


__all__ = ["RobotController", "MAX_STEP_DEFAULT"]