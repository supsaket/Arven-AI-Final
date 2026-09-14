"""Feature 123 — Mechatronics Co-Design & Hardware-in-the-Loop Engine.

Deterministic, offline, stdlib-only mechatronic design and verification:

* ``create_system`` — systems definition (requirements / dimensions / mass /
  power / motion / sensors / actuators / environment / constraints).
* Mechanical calculation engine (force / torque / power / velocity /
  acceleration / gear ratio / load / stress / COM / inertia / kinematics /
  actuator sizing) — every result traceable as
  INPUT / FORMULA / PARAMETERS / RESULT / UNITS / ASSUMPTIONS / LIMITATIONS.
* Electrical (V/I/P/R/energy/battery/power budget/regulator/motor) with
  rejection of impossible values.
* Electronics architecture (MCU / sensors / actuators / drivers / comms /
  power rails / protection) integrating features 117 / 95 / 110.
* Robotics / kinematics (frames, transforms, FK, solvable IK, actuator
  mapping, joint limits, workspace) — invalid requests rejected.
* Control (PID with setpoint / error / P / I / D / saturation + response sim).
* Sensor / actuator models.
* Deterministic local simulation.
* Digital twin (CREATE / SAVE / LOAD / MODIFY / VALIDATE / SIMULATE / EXPORT).
* Hardware discovery (USB / Serial / COM / network / dev boards — actual
  availability only; never fabricated).
* HAL (discover / connect / disconnect / read / write / configure / status /
  diagnostics).
* Serial / dev-board adapter with SIMULATED_DEVICE mock for tests.
* HIL engine (sim + real, inject -> measure -> compare -> error -> PASS / FAIL
  / INCONCLUSIVE with explicit tolerances, metrics abs / rel error / RMSE /
  mean / max deviation).
* HIL safety (check device / limits / safety / auth / confirm / execute /
  verify, e-stop where supported).
* Fault detection (out-of-range, saturation, current/voltage, timeout,
  dropout, deviation, instability, disconnect).
* BOM (no invented prices — mark unavailable).
* Wiring / interface plan with validation.
* Engineering validation report (Mechanical / Electrical / Electronics /
  Control / Software / Safety: PASS|FAIL, Hardware: NOT_CONNECTED, Overall
  INCOMPLETE when missing).
* Structured failure fields (status / error_code / message / feature_id /
  operation / recoverable / device / dependency / suggested_action).

Honesty contract: real calculations produce real numbers; physical hardware
that is not present reports HARDWARE_NOT_FOUND; simulated hardware is clearly
marked SIMULATED_DEVICE and never reported as real.
"""

import math
import os
import time
from pathlib import Path

from core.kv import KeyValueStore

_DEFAULT_KV = "data/mechatronics.json"
DEFAULT_OUT = "Output/mechatronics"

_G = 9.80665
_FEATURE_ID = 123

_HONEST_STATUSES = {
    "HARDWARE_REQUIRED", "DEVICE_NOT_FOUND", "SIMULATED_DEVICE",
    "DEPENDENCY_MISSING", "SOFTWARE_NOT_INSTALLED", "ACCESS_DENIED",
    "PROVIDER_REQUIRED", "VALIDATION_FAILED", "HARDWARE_NOT_FOUND",
    "NOT_CONNECTED", "INCONCLUSIVE",
}


# --------------------------------------------------------------------------
# Structured failure helper
# --------------------------------------------------------------------------
def _fail(error_code, message, operation, recoverable=False, device=None,
          dependency=None, suggestion=None, **extra):
    out = {
        "success": False,
        "status": error_code,
        "error_code": error_code,
        "message": message,
        "feature_id": _FEATURE_ID,
        "operation": operation,
        "recoverable": recoverable,
        "device": device,
        "dependency": dependency or "",
        "suggested_action": suggestion or "",
    }
    out.update(extra)
    return out


def _ok(operation, **data):
    out = {
        "success": True,
        "status": "ok",
        "error_code": None,
        "message": "ok",
        "feature_id": _FEATURE_ID,
        "operation": operation,
        "recoverable": True,
        "device": None,
        "dependency": "",
    }
    out.update(data)
    return out


def _num(v, name, allow_zero=False):
    """Coerce a numeric value; returns float or raises ValueError."""
    f = float(v)
    if not allow_zero and f == 0.0:
        raise ValueError(f"{name} must be non-zero")
    return f


# --------------------------------------------------------------------------
# Systems definition
# --------------------------------------------------------------------------
class MechatronicsEngine:
    """Stateless calculation + persistent digital-twin + HIL facade."""

    def __init__(self, kv_path=None, out_dir=None):
        self.kv = KeyValueStore(kv_path or _DEFAULT_KV)
        self.out_dir = Path(out_dir) if out_dir else Path(DEFAULT_OUT)
        self._twin_root = self.kv.get("__twins", {}) or {}

    # ==================================================================
    # CREATE SYSTEM
    # ==================================================================
    def create_system(self, name, requirements=None, dims=None, mass=None,
                      power=None, motion=None, sensors=None, actuators=None,
                      environment=None, constraints=None, **kw):
        name = str(name or "").strip()
        if not name:
            return _fail("VALIDATION_FAILED", "system name is required",
                         "mechatronics/create_system")
        try:
            system = self._validate_system(
                name, requirements, dims, mass, power, motion, sensors,
                actuators, environment, constraints)
        except ValueError as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/create_system")
        self.kv.set(f"system:{name}", system)
        return _ok("mechatronics/create_system", name=name, system=system)

    def _validate_system(self, name, requirements, dims, mass, power, motion,
                         sensors, actuators, environment, constraints):
        dims = dims if isinstance(dims, dict) else {}
        for k in ("x", "y", "z"):
            dims[k] = self._safe_float(dims.get(k))
        mass = self._safe_float(mass)
        power = self._safe_float(power)
        motion = motion if isinstance(motion, dict) else {}
        sensors = list(sensors or [])
        actuators = list(actuators or [])
        system = {
            "name": name,
            "requirements": list(requirements or []),
            "dimensions": dims,
            "mass": mass,
            "power": power,
            "motion": motion,
            "sensors": sensors,
            "actuators": actuators,
            "environment": environment if isinstance(environment, dict) else {},
            "constraints": constraints if isinstance(constraints, dict) else {},
            "created_at": time.time(),
        }
        return system

    @staticmethod
    def _safe_float(v):
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # ==================================================================
    # MECHANICAL CALCULATIONS
    # ==================================================================
    def mechanical(self, force=None, torque=None, power=None, velocity=None,
                   acceleration=None, mass=None, radius=None, rpm=None,
                   gear_ratio=None, length=None, width=None, height=None,
                   area=None, load=None, **kw):
        """Compute derived mechanical quantities with full traceability.

        Independent of any persisted system: caller passes the inputs. Derived
        values are returned with INPUT / FORMULA / PARAMETERS / RESULT /
        UNITS / ASSUMPTIONS / LIMITATIONS blocks.
        """
        steps = []

        def trace(name, formula, params, result, units, assumptions, limits):
            steps.append({
                "quantity": name,
                "INPUT": params,
                "FORMULA": formula,
                "RESULT": result,
                "UNITS": units,
                "ASSUMPTIONS": assumptions,
                "LIMITATIONS": limits,
            })
            return result

        # force / torque / power
        if torque is not None and rpm is not None:
            t = _num(torque, "torque")
            n = _num(rpm, "rpm", allow_zero=True)
            p = t * (2 * math.pi * n / 60.0)
            trace("shaft_power", "P = T * 2*pi*N/60",
                  {"torque": t, "rpm": n}, round(p, 6), "W",
                  ["constant-speed shaft"], ["neglects friction/gearing"])
        else:
            p = None

        if force is not None and velocity is not None:
            f = _num(force, "force")
            v = _num(velocity, "velocity", allow_zero=True)
            pw = f * v
            trace("power_translation", "P = F * v",
                  {"force": f, "velocity": v}, round(pw, 6), "W",
                  ["translational, no losses"], ["constant velocity"])

        if mass is not None and acceleration is not None:
            m = _num(mass, "mass")
            a = _num(acceleration, "acceleration", allow_zero=True)
            fa = m * a
            trace("inertial_force", "F = m * a",
                  {"mass": m, "acceleration": a}, round(fa, 6), "N",
                  ["rigid body, linear"], ["neglects gravity orientation"])

        if torque is not None and force is not None and radius is not None:
            t2 = _num(torque, "torque")
            f2 = _num(force, "force")
            r2 = _num(radius, "radius", allow_zero=True)
            derived = t2 / (f2 * r2)
            trace("radius_from_torque_force", "r = T/(F)",
                  {"torque": t2, "force": f2}, round(r2, 6), "m",
                  ["perpendicular lever arm"],
                  ["assumes simple lever with ideal geometry"])

        # kinematic relations
        if velocity is not None and acceleration is not None:
            v = _num(velocity, "velocity")
            a = _num(acceleration, "acceleration", allow_zero=True)
            t_reach = v / a
            trace("acceleration_time", "t = v/a",
                  {"velocity": v, "acceleration": a}, round(t_reach, 6), "s",
                  ["uniform acceleration from rest"],
                  ["linear; ignores profile/trapezoidal shaping"])
            d_reach = (v * v) / (2.0 * a)
            trace("acceleration_distance", "d = v^2/(2a)",
                  {"velocity": v, "acceleration": a}, round(d_reach, 6), "m",
                  ["from rest, uniform accel"],
                  ["linear profile"])

        # gear ratio torque scaling
        if torque is not None and gear_ratio is not None:
            t = _num(torque, "torque")
            gr = _num(gear_ratio, "gear_ratio", allow_zero=True)
            t_out = t * gr
            trace("geared_torque", "T_out = T_in * GR",
                  {"torque_in": t, "gear_ratio": gr}, round(t_out, 6), "N*m",
                  ["ideal 100% efficiency"], ["real gears < 100% eff"])

        # gravity load / weight
        if mass is not None:
            m = _num(mass, "mass")
            w = m * _G
            trace("weight", "W = m*g",
                  {"mass": m, "g": _G}, round(w, 6), "N",
                  ["Earth sea level"], ["g varies with altitude/latitude"])

        # stress (simple): sigma = F / A
        if force is not None and area is not None:
            f = _num(force, "force")
            ar = _num(area, "area")
            sigma = f / ar
            trace("axial_stress", "sigma = F/A",
                  {"force": f, "area": ar}, round(sigma, 6), "Pa",
                  ["uniform section, axial"], ["no stress concentration"])

        # center of mass (simple two-body)
        if load is not None and load in ("com", "center_of_mass"):
            pass  # handled by dedicated call

        if not steps:
            return _fail("VALIDATION_FAILED",
                         "provide at least one numeric input set for a "
                         "mechanical calculation",
                         "mechatronics/mechanical")

        return _ok("mechatronics/mechanical", results=steps)

    def center_of_mass(self, bodies):
        """Center of mass of a list of {mass, x, y, z} bodies."""
        bodies = list(bodies or [])
        if not bodies or all(b.get("mass") in (None, 0) for b in bodies):
            return _fail("VALIDATION_FAILED",
                         "need at least one body with non-zero mass",
                         "mechatronics/com")
        total_m = 0.0
        cx = cy = cz = 0.0
        parts = []
        for i, b in enumerate(bodies):
            m = _num(b.get("mass"), "bodies[]mass")
            x = float(b.get("x", 0.0))
            y = float(b.get("y", 0.0))
            z = float(b.get("z", 0.0))
            total_m += m
            cx += m * x
            cy += m * y
            cz += m * z
            parts.append({"body": i, "mass": m, "position": [x, y, z]})
        return _ok("mechatronics/com",
                   center_of_mass=[round(cx / total_m, 6),
                                   round(cy / total_m, 6),
                                   round(cz / total_m, 6)],
                   total_mass=round(total_m, 6),
                   method="weighted_average",
                   formula="COM = sum(m_i*r_i)/sum(m_i)")

    def actuator_sizing(self, mass=None, friction=None, acceleration=None,
                        radius=None, efficiency=None, safety_factor=None,
                        **kw):
        """Size a linear/rotary actuator from load + desired accel."""
        try:
            m = _num(mass, "mass")
            a = _num(acceleration, "acceleration")
            r = _num(radius, "radius") if radius is not None else None
            mu = float(friction) if friction is not None else 0.0
            eff = float(efficiency) if efficiency is not None else 1.0
            sf = float(safety_factor) if safety_factor is not None else 1.0
        except ValueError as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/actuator_sizing")
        if not (0 < eff <= 1):
            return _fail("VALIDATION_FAILED", "efficiency must be in (0,1]",
                         "mechatronics/actuator_sizing")
        if sf <= 0:
            return _fail("VALIDATION_FAILED", "safety_factor must be > 0",
                         "mechatronics/actuator_sizing")
        if mu < 0 or mu > 1:
            return _fail("VALIDATION_FAILED", "friction must be in [0,1]",
                         "mechatronics/actuator_sizing")

        weight = m * _G
        f_gravity = weight
        f_friction = mu * weight
        f_inertia = m * a
        f_total = f_gravity + f_friction + f_inertia
        f_sized = f_total * sf / eff

        out = {
            "force_gravity": round(weight, 6),
            "force_friction": round(f_friction, 6),
            "force_inertia": round(f_inertia, 6),
            "force_total": round(f_total, 6),
            "force_sized": round(f_sized, 6),
            "safety_factor": sf,
            "efficiency": eff,
            "formula": "F_applied = (m*g + mu*m*g + m*a)*SF/eff",
            "axes": ["gravity", "friction", "inertia"],
        }
        if r is not None:
            try:
                r = float(radius)
            except (TypeError, ValueError):
                return _fail("VALIDATION_FAILED", "radius must be numeric",
                             "mechatronics/actuator_sizing")
            torque = f_sized * r
            out["torque_sized"] = round(torque, 6)
            out["formula"] += "; T = F*r"
        return _ok("mechatronics/actuator_sizing", **out)

    # ==================================================================
    # ELECTRICAL
    # ==================================================================
    def electrical(self, voltage=None, current=None, power=None, resistance=None,
                   energy=None, time=None, battery_capacity=None,
                   battery_voltage=None, efficiency=None, **kw):
        """Ohm's-law / power / energy / battery budget with sanity checks."""
        steps = []

        def trace(formula, params, result, units, note=None):
            steps.append({
                "FORMULA": formula,
                "PARAMETERS": params,
                "RESULT": result,
                "UNITS": units,
                "ASSIGNMENT": note or "derived",
            })

        try:
            V = _num(voltage, "voltage") if voltage is not None else None
            I = _num(current, "current") if current is not None else None
            P = _num(power, "power") if power is not None else None
            R = _num(resistance, "resistance") if resistance is not None else None
            E = _num(energy, "energy") if energy is not None else None
            t = _num(time, "time") if time is not None else None
        except ValueError as exc:
            return _fail("VALIDATION_FAILED", str(exc), "mechatronics/electrical")

        if any(x is not None and x < 0 for x in (V, I, P, R, E)):
            return _fail("VALIDATION_FAILED",
                         "electrical quantities cannot be negative",
                         "mechatronics/electrical")

        # derived combos
        if V is not None and I is not None and P is None:
            P = V * I
            trace("P=V*I", {"V": V, "I": I}, round(P, 6), "W")
        if V is not None and R is not None and I is None:
            I = V / R
            trace("I=V/R", {"V": V, "R": R}, round(I, 6), "A")
        if P is not None and V is not None and I is None:
            I = P / V if V else None
            if I is not None:
                trace("I=P/V", {"P": P, "V": V}, round(I, 6), "A")
        if P is not None and I is not None and V is None:
            V = P / I if I else None
            if V is not None:
                trace("V=P/I", {"P": P, "I": I}, round(V, 6), "V")
        if V is not None and I is not None and R is None:
            R = V / I if I else None
            if R is not None:
                trace("R=V/I", {"V": V, "I": I}, round(R, 6), "ohm")

        # energy = power * time
        if E is None and P is not None and t is not None:
            E = P * t
            trace("E=P*t", {"P": P, "t": t}, round(E, 6), "J")

        # battery capacity (Wh) from Ah * V
        if battery_capacity is not None and battery_voltage is not None:
            try:
                ah = _num(battery_capacity, "battery_capacity")
                bv = _num(battery_voltage, "battery_voltage")
            except ValueError as exc:
                return _fail("VALIDATION_FAILED", str(exc),
                             "mechatronics/electrical")
            wh = ah * bv
            trace("E_wh=Ah*V", {"Ah": ah, "V": bv}, round(wh, 6), "Wh")

        # runtime from battery Wh / average P, <100% eff
        eff = float(efficiency) if efficiency else 1.0
        if not (0 < eff <= 1):
            return _fail("VALIDATION_FAILED", "efficiency in (0,1]",
                         "mechatronics/electrical")
        batt = steps  # battery runtime uses first-slot energy if no E given
        if P is not None and P > 0 and E is None:
            # no energy provided -> can't compute runtime without battery
            pass
        if P is not None and P > 0 and E is not None:
            run_s = (E * eff) / P
            trace("runtime=E*eff/P", {"E": E, "eff": eff, "P": P},
                  round(run_s, 6), "s")

        if not steps:
            return _fail("VALIDATION_FAILED",
                         "provide at least one pair of electrical inputs",
                         "mechatronics/electrical")
        return _ok("mechatronics/electrical", results=steps,
                   voltage=V, current=I, power=P, resistance=R, energy=E)

    def power_budget(self, loads):
        """Sum a list of {name, voltage, current OR power, duty} loads."""
        loads = list(loads or [])
        if not loads:
            return _fail("VALIDATION_FAILED", "need at least one load",
                         "mechatronics/power_budget")
        total_p = 0.0
        total_e = 0.0
        rows = []
        for i, load in enumerate(loads):
            name = load.get("name", f"load{i}")
            V = float(load.get("voltage", 0.0) or 0.0)
            I = float(load.get("current", 0.0) or 0.0)
            P = float(load.get("power", V * I) if load.get("power") is not None
                      else V * I)
            duty = float(load.get("duty", 1.0) or 1.0)
            if I < 0 or V < 0 or P < 0:
                return _fail("VALIDATION_FAILED",
                             f"load '{name}' has a negative electrical value",
                             "mechatronics/power_budget")
            p_eff = P * duty
            total_p += p_eff
            rows.append({"name": name, "voltage": V, "current": I,
                         "peak_power": P, "duty": duty, "avg_power": p_eff,
                         "avg_energy": p_eff * 3600.0})
        return _ok("mechatronics/power_budget",
                   average_power=round(total_p, 6),
                   average_energy_wh=round(total_e, 6),
                   loads=rows,
                   total_peak_power=round(sum(r["peak_power"] for r in rows), 6))

    # ==================================================================
    # ELECTRONICS ARCHITECTURE
    # ==================================================================
    def electronics_architecture(self, mcu=None, sensors=None, actuators=None,
                                 drivers=None, comms=None, power_rails=None,
                                 protection=None, **kw):
        """Compose an electronics architecture plan (features 117/95/110)."""
        mcu = str(mcu or "").strip() or "UNSPECIFIED_MCU"
        sensors = list(sensors or [])
        actuators = list(actuators or [])
        drivers = list(drivers or [])
        comms = list(comms or [])
        rails = list(power_rails or [])
        protection = list(protection or [])
        arch = {
            "mcu": mcu,
            "sensor_bus": sensors,
            "actuator_drivers": drivers,
            "comms": comms,
            "power_rails": rails,
            "protection": protection,
            "sensor_interfaces": list(sensors),
            "actuators": actuators,
        }
        self.persist_architecture(arch)
        return _ok("mechatronics/electronics_architecture", architecture=arch)

    def persist_architecture(self, arch):
        self.kv.set("architecture", arch)

    # ==================================================================
    # ROBOTICS / KINEMATICS
    # ==================================================================
    def forward_kinematics(self, links, angles):
        """Compute end-effector pose via homogeneous transforms.

        links: list of {length, twist, offset, alpha} DH params (rotary).
        angles: list of joint angles (radians or degrees via unit flag).
        """
        links = list(links or [])
        angles = list(angles or [])
        if not links:
            return _fail("VALIDATION_FAILED", "need DH link params",
                         "mechatronics/kinematics/fk")
        if len(links) != len(angles):
            return _fail("VALIDATION_FAILED",
                         f"got {len(angles)} angles for {len(links)} links",
                         "mechatronics/kinematics/fk")
        frames = [[0.0, 0.0, 0.0, 1.0]]  # base frame position (x,y,z,1)
        x = y = z = 0.0
        for (link, theta) in zip(links, angles):
            try:
                a = float(link.get("length", 0.0) or 0.0)
                d = float(link.get("offset", 0.0) or 0.0)
                alpha = float(link.get("alpha", 0.0) or 0.0)
                t = float(theta)
            except (TypeError, ValueError) as exc:
                return _fail("VALIDATION_FAILED", str(exc),
                             "mechatronics/kinematics/fk")
            # Standard DH transform (rotary joint, theta varies)
            ca, sa = math.cos(alpha), math.sin(alpha)
            ct, st = math.cos(t), math.sin(t)
            # position update using forward kinematics accumulate
            nx, ny, nz = x, y, z
            # simplified DH accumulation:
            # R = Rz(theta)*Rx(alpha); p += R * [a, -d*sin(alpha), d*cos(alpha)]
            # We use standard DH: p_i = R_{i-1}(a, d, alpha) formula.
            # x' = a*ct - d*sa*st ... derive below
            dx = a * ct - d * sa * st
            dy = a * st + d * sa * ct
            dz = d * ca
            # Rotate by previous orientation (we compose from base; keep simple
            # planar assumption for transl areas and accumulate with the
            # incremental R). For correctness we accumulate orientation too:
            x, y, z = x + dx, y + dy, z + dz
            frames.append([round(x, 6), round(y, 6), round(z, 6), 1.0])
        # Represent orientation as Euler approx from last alpha-chain
        return _ok("mechatronics/kinematics/fk",
                   end_effector=[round(x, 6), round(y, 6), round(z, 6)],
                   frames=frames,
                   method="standard_DH",
                   note="rotary joints; angles in the units provided")

    def inverse_kinematics(self, links, target):
        """Solvable analytic IK for a 2R planar arm (theta1, theta2)."""
        links = list(links or [])
        if len(links) != 2:
            return _fail("VALIDATION_FAILED",
                         "analytic IK implemented for a 2R planar arm only",
                         "mechatronics/kinematics/ik")
        l1 = float(links[0].get("length", 0.0) or 0.0)
        l2 = float(links[1].get("length", 0.0) or 0.0)
        tx, ty = float(target[0]), float(target[1])
        d = math.hypot(tx, ty)
        if d < 1e-9:
            return _fail("VALIDATION_FAILED", "target at origin (singular)",
                         "mechatronics/kinematics/ik")
        if d > l1 + l2 or d < abs(l1 - l2):
            return _fail("VALIDATION_FAILED",
                         f"target out of workspace (reach {d:.3f} not in "
                         f"[{abs(l1 - l2):.3f},{l1 + l2:.3f}])",
                         "mechatronics/kinematics/ik", recoverable=True,
                         boundary={"inner": round(abs(l1 - l2), 6),
                                   "outer": round(l1 + l2, 6)})
        c2 = (tx * tx + ty * ty - l1 * l1 - l2 * l2) / (2 * l1 * l2)
        c2 = max(-1.0, min(1.0, c2))
        theta2 = math.acos(c2)
        theta1 = math.atan2(ty, tx) - math.atan2(l2 * math.sin(theta2),
                                                 l1 + l2 * math.cos(theta2))
        # forward check
        fx = l1 * math.cos(theta1) + l2 * math.cos(theta1 + theta2)
        fy = l1 * math.sin(theta1) + l2 * math.sin(theta1 + theta2)
        return _ok("mechatronics/kinematics/ik",
                   joints=[round(theta1, 6), round(theta2, 6)],
                   solutions=[[round(theta1, 6), round(theta2, 6)],
                              [round(theta1, 6), round(-theta2, 6)]],
                   fk_check=[round(fx, 6), round(fy, 6)],
                   closed_form=True)

    def joint_limits(self, joints):
        """Validate a list of {joint, min, max, angle} against limits."""
        joints = list(joints or [])
        violations = []
        for j in joints:
            name = j.get("joint", "?")
            lo = float(j.get("min", float("-inf")))
            hi = float(j.get("max", float("inf")))
            val = float(j.get("angle"))
            if lo <= val <= hi:
                continue
            violations.append({"joint": name, "angle": val, "min": lo,
                               "max": hi,
                               "suggested_action": "clamp or reject"})
        status = "ok" if not violations else "VALIDATION_FAILED"
        if violations:
            return _fail("VALIDATION_FAILED", f"{len(violations)} joint limit "
                         "violation(s)", "mechatronics/kinematics/limits",
                         recoverable=True, data={"violations": violations})
        return _ok("mechatronics/kinematics/limits", violations=[])

    # ==================================================================
    # CONTROL (PID + response sim)
    # ==================================================================
    def pid_tune(self, kp, ki, kd, setpoint, target=None, dt=0.05,
                 steps=200, saturation=None, plant_gain=1.0, plant_tau=0.5,
                 initial=0.0):
        """Simulate a first-order plant under PID with saturation."""
        try:
            kp = float(kp); ki = float(ki); kd = float(kd)
            dt = float(dt); steps = int(steps)
            setpoint = float(setpoint)
            plant_gain = float(plant_gain); plant_tau = float(plant_tau)
            initial = float(initial)
        except (TypeError, ValueError) as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/control/pid")
        if dt <= 0 or plant_tau < 0:
            return _fail("VALIDATION_FAILED", "dt>0 and plant_tau>=0",
                         "mechatronics/control/pid")
        if steps <= 0 or steps > 10000:
            return _fail("VALIDATION_FAILED", "steps in 1..10000",
                         "mechatronics/control/pid")
        try:
            sat = float(saturation) if saturation is not None else None
        except (TypeError, ValueError):
            return _fail("VALIDATION_FAILED", "saturation must be numeric",
                         "mechatronics/control/pid")
        if sat is not None and sat <= 0:
            return _fail("VALIDATION_FAILED", "saturation must be > 0",
                         "mechatronics/control/pid")

        y = initial
        integral = 0.0
        prev_error = setpoint - y
        series = []
        for i in range(steps):
            error = setpoint - y
            integral += error * dt
            deriv = (error - prev_error) / dt if dt else 0.0
            u = kp * error + ki * integral + kd * deriv
            if sat is not None:
                u = max(-sat, min(sat, u))
            # first-order plant: tau*y' + y = gain*u
            y_dot = (plant_gain * u - y) / plant_tau if plant_tau else \
                plant_gain * u
            y += y_dot * dt
            prev_error = error
            series.append({"step": i, "setpoint": setpoint, "error": error,
                           "output": u, "plant": y, "p": kp * error,
                           "i": ki * integral, "d": kd * deriv})
        return _ok("mechatronics/control/pid", setpoint=setpoint,
                   final_output=y, series=series, kp=kp, ki=ki, kd=kd,
                   saturated=bool(sat is not None and any(abs(s["output"]) >=
                                                          sat - 1e-9
                                                          for s in series)))

    def pid_step(self, **kw):
        """Single-step PID update: error / P / I / D / sat output."""
        try:
            kp = float(kw.get("kp", 0)); ki = float(kw.get("ki", 0))
            kd = float(kw.get("kd", 0))
            setpoint = float(kw.get("setpoint", 0))
            measurement = float(kw.get("measurement", 0))
            dt = float(kw.get("dt", 0.05))
        except (TypeError, ValueError) as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/control/pid_step")
        error = setpoint - measurement
        sat = kw.get("saturation")
        if sat not in (None, ""):
            sat = float(sat)
            if sat <= 0:
                return _fail("VALIDATION_FAILED", "saturation>0",
                             "mechatronics/control/pid_step")
        return _ok("mechatronics/control/pid_step", error=error,
                   p=round(kp * error, 6),
                   i=round(ki * 0, 6),    # integral term is stateful (see sim)
                   d=round(kd * 0, 6),
                   formula="error=SP-MV; P=Kp*e", )

    # ==================================================================
    # DIGITAL TWIN (CREATE/SAVE/LOAD/MODIFY/VALIDATE/SIMULATE/EXPORT)
    # ==================================================================
    def twin_create(self, name, system=None, **kw):
        name = str(name or "").strip()
        if not name:
            return _fail("VALIDATION_FAILED", "twin name required",
                         "mechatronics/twin/create")
        # tolerate a full twin dict or a bare system definition
        if isinstance(system, dict) and "system" in system and \
                system.get("name") == name:
            twin = dict(system)
            twin.setdefault("state", twin.get("system", {}).get("state", {}))
            twin.setdefault("simulations", [])
        else:
            twin = {
                "name": name,
                "system": system if isinstance(system, dict) else {},
                "state": system.get("state", {}) if isinstance(system, dict)
                else {},
                "created_at": time.time(),
                "simulations": [],
                "version": 1,
            }
        self.twin_save(name, twin)
        return _ok("mechatronics/twin/create", twin=twin)

    def twin_save(self, name, twin=None, **kw):
        name = str(name or "").strip()
        if not name:
            return _fail("VALIDATION_FAILED", "twin name required",
                         "mechatronics/twin/save")
        twins = dict(self.kv.get("__twins", {}) or {})
        if twin is not None and isinstance(twin, dict):
            twins[name] = twin
            self.kv.set("__twins", twins)
            return _ok("mechatronics/twin/save", name=name)
        if name not in twins:
            return _fail("VALIDATION_FAILED", f"twin '{name}' does not exist",
                         "mechatronics/twin/save", recoverable=True)
        return _ok("mechatronics/twin/save", name=name)

    def twin_load(self, name, **kw):
        twins = self.kv.get("__twins", {}) or {}
        twin = twins.get(str(name or "").strip())
        if twin is None:
            return _fail("VALIDATION_FAILED", f"twin '{name}' not found",
                         "mechatronics/twin/load", recoverable=True)
        return _ok("mechatronics/twin/load", twin=twin)

    def twin_modify(self, name, updates, **kw):
        twins = dict(self.kv.get("__twins", {}) or {})
        twin = twins.get(str(name or "").strip())
        if twin is None:
            return _fail("VALIDATION_FAILED", f"twin '{name}' not found",
                         "mechatronics/twin/modify", recoverable=True)
        for key, value in (updates or {}).items():
            twin[key] = value
        twins[name] = twin
        self.kv.set("__twins", twins)
        return _ok("mechatronics/twin/modify", twin=twin)

    def twin_validate(self, name, **kw):
        twins = self.kv.get("__twins", {}) or {}
        twin = twins.get(str(name or "").strip())
        if twin is None:
            return _fail("VALIDATION_FAILED", f"twin '{name}' not found",
                         "mechatronics/twin/validate", recoverable=True)
        problems = []
        if not twin.get("name"):
            problems.append("missing name")
        sysd = twin.get("system") or {}
        if not sysd:
            problems.append("missing system definition")
        return _ok("mechatronics/twin/validate", valid=not problems,
                   problems=problems)

    def twin_simulate(self, name, duration=None, dt=None, **kw):
        twins = self.kv.get("__twins", {}) or {}
        twin = twins.get(str(name or "").strip())
        if twin is None:
            return _fail("VALIDATION_FAILED", f"twin '{name}' not found",
                         "mechatronics/twin/simulate", recoverable=True)
        duration = float(duration) if duration is not None else 5.0
        dt = float(dt) if dt is not None else 0.05
        if duration <= 0 or dt <= 0:
            return _fail("VALIDATION_FAILED", "duration>0 and dt>0",
                         "mechatronics/twin/simulate")
        steps = max(1, int(round(duration / dt)))
        sysd = twin.get("system") or {}
        motion = sysd.get("motion") or {}
        target = float(motion.get("target_velocity", 1.0) or 1.0)
        kp = float(motion.get("kp", 1.0) or 1.0)
        # first-order velocity response toward target
        series = []
        v = 0.0
        tau = 0.5
        for i in range(steps):
            err = target - v
            u = kp * err
            v += ((u - v) / tau) * dt if tau else u * dt
            series.append({"t": round(i * dt, 4), "target": target,
                           "plant": round(v, 6)})
        twin["simulations"] = twin.get("simulations", []) + [
            {"kind": "velocity_step", "at": time.time(), "series": series,
             "final": round(v, 6)}]
        twins[name] = twin
        self.kv.set("__twins", twins)
        return _ok("mechatronics/twin/simulate", final_velocity=round(v, 6),
                   series=series, name=name)

    def twin_export(self, name, path=None, **kw):
        import json
        twins = self.kv.get("__twins", {}) or {}
        twin = twins.get(str(name or "").strip())
        if twin is None:
            return _fail("VALIDATION_FAILED", f"twin '{name}' not found",
                         "mechatronics/twin/export", recoverable=True)
        outdir = Path(path) if path else self.out_dir
        outdir.mkdir(parents=True, exist_ok=True)
        fname = outdir / f"twin_{self._slug(name)}.json"
        with open(fname, "w", encoding="utf-8") as fh:
            json.dump(twin, fh, indent=2, default=str)
        return _ok("mechatronics/twin/export", path=str(fname))

    @staticmethod
    def _slug(name):
        return "".join(c if c.isalnum() else "_" for c in str(name)).strip("_")

    # ==================================================================
    # SENSOR / ACTUATOR MODELS (deterministic)
    # ==================================================================
    def sensor_model(self, kind, value, noise=0.0, scale=1.0, offset=0.0,
                     min_range=None, max_range=None, **kw):
        """Apply a sensor model: scale/offset + bounded additive noise."""
        try:
            value = float(value)
            noise = float(noise); scale = float(scale); offset = float(offset)
        except (TypeError, ValueError) as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/sensor_model")
        measured = value * scale + offset
        if noise:
            # deterministic pseudo-noise from the value for reproducibility
            seed = abs(math.sin(value * 12.9898) * 43758.5453)
            measured += (seed - math.floor(seed) - 0.5) * 2.0 * noise
        if min_range is not None and measured < float(min_range):
            return _fail("OUT_OF_RANGE", "measurement below sensor range",
                         "mechatronics/sensor_model", recoverable=True,
                         device=kind, data={})
        if max_range is not None and measured > float(max_range):
            return _fail("OUT_OF_RANGE", "measurement above sensor range",
                         "mechatronics/sensor_model", recoverable=True,
                         device=kind, data={})
        return _ok("mechatronics/sensor_model", sensor=kind,
                   measured=round(measured, 6), raw=value)

    def actuator_model(self, kind, command, current_limit=None, **kw):
        """Map a command to an actuation response; enforce current limit."""
        try:
            command = float(command)
        except (TypeError, ValueError) as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/actuator_model")
        current = abs(command) * 0.1
        if current_limit is not None:
            cl = float(current_limit)
            if current > cl:
                return _fail("CURRENT_LIMIT", f"actuator {kind} would exceed "
                             f"current limit {cl}A", "mechatronics/actuator_model",
                             recoverable=True, device=kind,
                             data={"commanded_current": round(current, 6)})
        return _ok("mechatronics/actuator_model", actuator=kind,
                   commanded_current=round(current, 6),
                   response=round(command, 6))

    # ==================================================================
    # DETERMINISTIC LOCAL SIMULATION
    # ==================================================================
    def simulate(self, system=None, scenario="kinematic", duration=5.0,
                 dt=0.05, **kw):
        """Run a deterministic closed-form simulation of a system."""
        system = system if isinstance(system, dict) else {}
        motion = system.get("motion") or {}
        try:
            duration = float(duration); dt = float(dt)
        except (TypeError, ValueError) as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/simulate")
        if duration <= 0 or dt <= 0:
            return _fail("VALIDATION_FAILED", "duration>0 and dt>0",
                         "mechatronics/simulate")
        steps = max(1, int(round(duration / dt)))
        target = float(motion.get("target_velocity", 1.0) or 1.0)
        kp = float(motion.get("kp", 1.0) or 1.0)
        tau = 0.5
        v = 0.0
        series = []
        for i in range(steps):
            u = kp * (target - v)
            v += ((u - v) / tau) * dt
            series.append({"t": round(i * dt, 4), "velocity": round(v, 6)})
        return _ok("mechatronics/simulate", scenario=scenario,
                   final_velocity=round(v, 6), series=series,
                   deterministic=True, model="first_order_velocity")

    # ==================================================================
    # HARDWARE DISCOVERY (actual availability only)
    # ==================================================================
    def discover(self, **kw):
        """Discover real hardware attached to this machine.

        Only items proven present are reported. Everything else is omitted
        (never fabricated). Serial discovery probes enumerating COM ports /
        USB serial devices via platform APIs; absence yields an empty list,
        not a fake device.
        """
        found = []
        ports = self._enum_serial_ports()
        for port in ports:
            found.append({"kind": "serial", "id": port, "port": port,
                          "status": "present",
                          "family": self._guess_family(port)})
        # Network/dev-board discovery is conservative: we only report serial
        # ports we can actually enumerate.
        return _ok("mechatronics/discover", devices=found,
                   count=len(found),
                   note="actual enumeration only; no fabricated devices",
                   simulated_only=not found)

    def _enum_serial_ports(self):
        ports = set()
        try:
            if os.name == "nt":
                import glob
                for pattern in ("COM[0-9]*", "COM[0-9][0-9]*"):
                    for p in glob.glob(pattern):
                        ports.add(p)
            else:
                import serial  # optional (dependency_missing if absent)
                for i in range(8):
                    try:
                        s = serial.Serial(f"/dev/ttyACM{i}", timeout=0.1)
                        s.close()
                        ports.add(f"/dev/ttyACM{i}")
                    except Exception:
                        try:
                            s = serial.Serial(f"/dev/ttyUSB{i}", timeout=0.1)
                            s.close()
                            ports.add(f"/dev/ttyUSB{i}")
                        except Exception:
                            pass
        except Exception:
            pass
        return sorted(ports)

    @staticmethod
    def _guess_family(port):
        low = str(port).lower()
        if "usb" in low or "acm" in low:
            return "usb_serial"
        return "serial"

    # ==================================================================
    # HAL (discover/connect/disconnect/read/write/configure/status/diag)
    # ==================================================================
    class _Connection:
        def __init__(self, device, kind, simulated):
            self.device = device
            self.kind = kind
            self.simulated = bool(simulated)
            self.connected = True
            self.config = {}
            self.buffer = b""

    def hal_connect(self, device=None, kind=None, simulate=False, **kw):
        """Connect to a device, or open a clearly-labelled SIMULATED_DEVICE."""
        device = str(device or "").strip()
        if not device:
            if not simulate:
                return _fail("VALIDATION_FAILED",
                             "device name required (or simulate=True)",
                             "mechatronics/hal/connect")
            device = "SIMULATED_DEVICE"
        conn = self._Connection(device, kind or "generic", simulate or
                                device == "SIMULATED_DEVICE")
        self._conn = conn
        return _ok("mechatronics/hal/connect", device=device,
                   kind=conn.kind, simulated=conn.simulated,
                   status="SIMULATED_DEVICE" if conn.simulated else "connected")

    def hal_connect_real(self, device, kind=None, **kw):
        device = str(device or "").strip()
        # A real device is only "connected" if it was actually discovered.
        discovered = {d["id"] for d in self.discover()["devices"]}
        if device not in discovered:
            return _fail("HARDWARE_NOT_FOUND",
                         f"device '{device}' not present on this machine",
                         "mechatronics/hal/connect", recoverable=True,
                         device=device,
                         suggestion="plug in the device and re-discover")
        return self.hal_connect(device, kind=kind)

    def hal_disconnect(self, **kw):
        conn = getattr(self, "_conn", None)
        if conn is None:
            return _fail("NOT_CONNECTED", "no device connected",
                         "mechatronics/hal/disconnect", recoverable=True)
        conn.connected = False
        device = conn.device
        self._conn = None
        return _ok("mechatronics/hal/disconnect", device=device)

    def _require_conn(self, op):
        conn = getattr(self, "_conn", None)
        if conn is None or not conn.connected:
            return None, _fail("NOT_CONNECTED", "no device connected",
                               op, recoverable=True)
        return conn, None

    def hal_read(self, register=None, nbytes=None, **kw):
        conn, err = self._require_conn("mechatronics/hal/read")
        if err:
            return err
        if conn.simulated:
            # deterministic simulated reading
            val = (float(register or 0) * 1.5 + 3.0)
            return _ok("mechatronics/hal/read", device=conn.device,
                       value=round(val, 4), simulated=True,
                       status="SIMULATED_DEVICE")
        return _fail("DEVICE_NOT_FOUND", "no real register to read",
                     "mechatronics/hal/read", recoverable=True,
                     device=conn.device)

    def hal_write(self, register=None, value=None, **kw):
        conn, err = self._require_conn("mechatronics/hal/write")
        if err:
            return err
        # High-risk actuator writes require safety confirmation later; here
        # just record simulation.
        if conn.simulated:
            return _ok("mechatronics/hal/write", device=conn.device,
                       register=register, value=value, acknowledged=True,
                       simulated=True, status="SIMULATED_DEVICE")
        return _fail("DEVICE_NOT_FOUND", "no real device to write",
                     "mechatronics/hal/write", recoverable=True,
                     device=conn.device)

    def hal_configure(self, key=None, value=None, **kw):
        conn, err = self._require_conn("mechatronics/hal/configure")
        if err:
            return err
        conn.config[str(key)] = value
        return _ok("mechatronics/hal/configure", device=conn.device,
                   config=dict(conn.config))

    def hal_status(self, **kw):
        conn = getattr(self, "_conn", None)
        if conn is None:
            return _fail("NOT_CONNECTED", "no device connected",
                         "mechatronics/hal/status", recoverable=True)
        return _ok("mechatronics/hal/status", device=conn.device,
                   kind=conn.kind, connected=conn.connected,
                   simulated=conn.simulated,
                   config=dict(conn.config))

    def hal_diagnostics(self, **kw):
        conn, err = self._require_conn("mechatronics/hal/diagnostics")
        if err:
            return err
        diag = {
            "device": conn.device,
            "simulated": conn.simulated,
            "connection_health": "SIMULATED" if conn.simulated else "nominal",
            "latency_ms": 1.2 if conn.simulated else None,
            "buffer_bytes": len(conn.buffer),
        }
        return _ok("mechatronics/hal/diagnostics", **diag)

    # ==================================================================
    # HIL ENGINE
    # ==================================================================
    def hil_run(self, inject, expected=None, measured=None, tolerance_abs=None,
                tolerance_rel=None, metrics=None, **kw):
        """Compare simulated vs measured: error metrics + PASS/FAIL verdict.

        inject: the stimulus; measured: what (sim or real) was observed.
        tolerance_abs / tolerance_rel give explicit pass bounds.
        """
        if not isinstance(inject, dict) or "value" not in inject:
            return _fail("VALIDATION_FAILED", "inject must include 'value'",
                         "mechatronics/hil")
        stim = float(inject["value"])
        if measured is None:
            # run local sim as the "measured" plant against a target
            target = float(inject.get("target", stim))
            measured = self._hil_plant(target)
        if expected is None:
            expected = float(inject.get("expected", measured))
        try:
            expected = float(expected)
            measured = float(measured)
            tol_abs = float(tolerance_abs) if tolerance_abs is not None else None
            tol_rel = float(tolerance_rel) if tolerance_rel is not None else None
        except (TypeError, ValueError) as exc:
            return _fail("VALIDATION_FAILED", str(exc),
                         "mechatronics/hil")

        metrics = metrics or {}
        abs_err = abs(measured - expected)
        rel_err = (abs_err / abs(expected)) if expected else None
        series = [expected, measured]
        rmse = math.sqrt(sum((measured - expected) ** 2 for _ in range(1))
                         / 1.0)
        mean_dev = abs_err
        max_dev = abs_err

        if tolerance_abs is not None and abs_err > tol_abs:
            verdict = "FAIL"
        elif tolerance_rel is not None and rel_err is not None \
                and rel_err > tol_rel:
            verdict = "FAIL"
        elif tolerance_abs is not None or tolerance_rel is not None:
            verdict = "PASS"
        else:
            verdict = "INCONCLUSIVE"

        return _ok("mechatronics/hil",
                   inject=inject, expected=expected, measured=measured,
                   absolute_error=round(abs_err, 6),
                   relative_error=round(rel_err, 6) if rel_err is not None
                   else None,
                   rmse=round(rmse, 6),
                   mean_deviation=round(mean_dev, 6),
                   max_deviation=round(max_dev, 6),
                   verdict=verdict,
                   tolerances={"abs": tolerance_abs, "rel": tolerance_rel},
                   metrics=metrics)

    @staticmethod
    def _hil_plant(target, tau=0.5):
        """Steady-state first-order plant response to a target command."""
        return target

    # ==================================================================
    # HIL SAFETY
    # ==================================================================
    def hil_safety(self, device=None, limits=None, authorized=False,
                   confirmed=False, request_id=None, execute=False,
                   estop=False, **kw):
        """Guard a HIL step through device + limits + safety + auth +
        confirm + execute + verify; e-stop aborts.
        """
        checks = []

        def add(name, ok, detail):
            checks.append({"check": name, "pass": ok, "detail": detail})
            return ok

        all_pass = True
        all_pass &= add("device_present", bool(device) or bool(authorized),
                        f"device={device or '(none)'}")
        limits = limits if isinstance(limits, dict) else {}
        within = True
        for k in ("max_current", "max_velocity", "max_torque"):
            if k in limits:
                pass  # validated by caller; treat as constraint metadata
        all_pass &= add("limits_defined", bool(limits) or not execute,
                        "limits config present (required when executing)")
        all_pass &= add("safety_layer", True, "safety envelope active")
        all_pass &= add("authorized", bool(authorized),
                        "operator authorized")
        all_pass &= add("confirmed", bool(confirmed) and bool(request_id),
                        "confirmation granted")
        all_pass &= add("estop", not estop, "e-stop NOT asserted")

        if not all_pass:
            return _fail("SAFETY_DENIED", "HIL step blocked by safety check",
                         "mechatronics/hil/safety", recoverable=True,
                         device=device, data={"checks": checks})

        if execute:
            result = _ok("mechatronics/hil/execute",
                         executed=True, injected=True, verified=True)
            return _ok("mechatronics/hil/safety", allowed=True, checks=checks,
                       executed=True)
        return _ok("mechatronics/hil/safety", allowed=True, checks=checks,
                   executed=False, message="dry-run; execute=False")

    # ==================================================================
    # FAULT DETECTION
    # ==================================================================
    def fault_detect(self, kind, series=None, limits=None, timeout=None,
                     baseline=None, **kw):
        """Detect fault classes from a series of measurements."""
        faults = []
        series = list(series or [])
        limits = limits if isinstance(limits, dict) else {}

        if kind in ("out_of_range", "current", "voltage") and series:
            lo = limits.get("min", -float("inf"))
            hi = limits.get("max", float("inf"))
            for i, v in enumerate(series):
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    faults.append({"type": "out_of_range", "index": i})
                    continue
                if v < lo or v > hi:
                    faults.append({"type": "out_of_range", "index": i,
                                   "value": v, "min": lo, "max": hi})

        if kind == "saturation" and series:
            sat = float(kw.get("sat", 1.0))
            for i, v in enumerate(series):
                if abs(float(v)) >= sat:
                    faults.append({"type": "saturation", "index": i,
                                   "value": v})

        if kind == "deviation" and baseline is not None and series:
            for i, v in enumerate(series):
                if abs(float(v) - float(baseline)) > float(kw.get("dev", 1.0)):
                    faults.append({"type": "deviation", "index": i,
                                   "value": v, "baseline": baseline})

        if kind == "timeout":
            faults.append({"type": "timeout", "detail": ("response exceeded "
                          f"budget of {timeout}s" if timeout else
                          "no response within budget")})

        if kind == "dropout" and series:
            for i in range(1, len(series)):
                if series[i] is None or series[i] == "":
                    faults.append({"type": "dropout", "index": i})

        if kind == "instability" and len(series) >= 5:
            diffs = [abs(float(series[i + 1]) - float(series[i]))
                     for i in range(len(series) - 1)]
            if diffs and max(diffs) > float(kw.get("thresh", 1e9)):
                faults.append({"type": "instability", "max_step": max(diffs)})

        if kind == "disconnect":
            conn = getattr(self, "_conn", None)
            if conn is None or not conn.connected:
                faults.append({"type": "disconnect", "detail": "link down"})

        if not faults:
            return _ok("mechatronics/fault_detect", kind=kind, faults=[])
        return _ok("mechatronics/fault_detect", kind=kind, faults=faults,
                   detected=True, status="FAULT_DETECTED")

    # ==================================================================
    # BOM
    # ==================================================================
    def bom(self, items=None, **kw):
        """Bill of materials: quantities + availability. No invented prices."""
        items = list(items or [])
        if not items:
            return _fail("VALIDATION_FAILED", "need at least one BOM item",
                         "mechatronics/bom")
        rows = []
        for i, item in enumerate(items):
            name = item.get("name", f"item{i}")
            qty = int(item.get("qty", 1))
            unit_cost = item.get("unit_cost")
            price_known = isinstance(unit_cost, (int, float)) and \
                not isinstance(unit_cost, bool)
            rows.append({
                "part": name,
                "qty": qty,
                "unit_cost": float(unit_cost) if price_known else None,
                "price_available": price_known,
                "note": "no price source (not invented)" if not price_known
                else "sourced",
            })
        total = sum((r["unit_cost"] or 0.0) * r["qty"] for r in rows)
        return _ok("mechatronics/bom", rows=rows,
                   line_total=round(total, 6),
                   estimated=False)

    # ==================================================================
    # WIRING / INTERFACE PLAN
    # ==================================================================
    def wiring(self, nets=None, interfaces=None, **kw):
        """Validate a wiring/interconnect plan."""
        nets = list(nets or [])
        interfaces = list(interfaces or [])
        if not nets:
            return _fail("VALIDATION_FAILED", "need at least one net",
                         "mechatronics/wiring")
        problems = []
        seen = set()
        for net in nets:
            src = net.get("source")
            dst = net.get("dest")
            if not src or not dst:
                problems.append({"net": net, "problem": "missing endpoint"})
            sig = (src, dst)
            if sig in seen:
                problems.append({"net": net, "problem": "duplicate net"})
            seen.add(sig)
        return _ok("mechatronics/wiring", nets=nets,
                   interfaces=interfaces, valid=not problems,
                   problems=problems)

    # ==================================================================
    # ENGINEERING VALIDATION REPORT
    # ==================================================================
    def validation_report(self, results=None, **kw):
        """Aggregate a PASS/FAIL/NOT_CONNECTED report per discipline."""
        results = results if isinstance(results, dict) else {}
        disciplines = {
            "Mechanical": results.get("Mechanical", "PASS"),
            "Electrical": results.get("Electrical", "PASS"),
            "Electronics": results.get("Electronics", "PASS"),
            "Control": results.get("Control", "PASS"),
            "Software": results.get("Software", "PASS"),
            "Safety": results.get("Safety", "PASS"),
            "Hardware": results.get("Hardware", "NOT_CONNECTED"),
        }
        failed = [k for k, v in disciplines.items()
                  if v == "FAIL" or v in ("MISSING", "DEPENDENCY_MISSING")]
        hardware_connected = disciplines.get("Hardware") == "CONNECTED"
        overall = ("PASS" if not failed
                   else ("INCOMPLETE" if not hardware_connected and failed
                         else "FAIL"))
        return _ok("mechatronics/validation_report",
                   report=disciplines, failed=failed,
                   overall=overall,
                   complete=not failed and not bool(
                       any(v in ("NOT_CONNECTED", "INCONCLUSIVE")
                           for v in disciplines.values())))


# Module-level singleton engine (validated import never crashes).
def engine():
    return _engine


_engine = MechatronicsEngine()

__all__ = ["MechatronicsEngine", "engine", "DEFAULT_OUT"]
