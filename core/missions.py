"""Feature 50 — Task/Mission Supervision.

``MissionsEngine`` (alias ``MissionEngine``): persisted, supervised missions
with a real step state machine, dependency gating, timeout-controlled step
execution, escalation, checkpoint logging and restart recovery.

Persistence is via ``core.kv.KeyValueStore``; a fresh engine constructed on
the same kv path holds exactly the same missions after ``restore()``.

Security: ``cancel``/``archive`` never hard-delete; ``cancel`` records an
audit entry. Risky external actions are NOT auto-executed here — workflows/
skills own those gates — this module only supervises steps.
"""

import copy
import re
import threading
import time

from core.kv import KeyValueStore
from core.lifecycle import BoundedOperation

MISSION_ACTIVE = "active"
MISSION_PAUSED = "paused"
MISSION_BLOCKED = "blocked"
MISSION_COMPLETED = "completed"
MISSION_FAILED = "failed"
MISSION_ARCHIVED = "archived"

STEP_OPEN = "open"
STEP_RUNNING = "running"
STEP_DONE = "done"
STEP_FAILED = "failed"
STEP_BLOCKED = "blocked"

_REGISTRY_KEY = "missions.registry"
_DEFAULT_PATH = "data/runtime/missions.json"

_TERMINAL = {MISSION_COMPLETED, MISSION_FAILED, MISSION_ARCHIVED}


def _now():
    return time.time()


def _slug(text):
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_")
    return cleaned or "step"


def _validate_mission(title, steps, priority, budget_seconds):
    if not str(title or "").strip():
        raise ValueError("mission title must be non-empty")
    if not isinstance(steps, (list, tuple)) or not steps:
        raise ValueError("a mission needs at least one step")
    if not isinstance(priority, (int, float)):
        raise ValueError("priority must be a number")
    if budget_seconds is not None and not isinstance(budget_seconds, (int, float)):
        raise ValueError("budget_seconds must be numeric or None")
    return True


def _valid_step_status(value):
    if value in (STEP_OPEN, STEP_RUNNING, STEP_DONE, STEP_FAILED, STEP_BLOCKED):
        return value
    return STEP_OPEN


def _normalize_steps(steps):
    normalized = []
    for index, raw in enumerate(steps):
        if isinstance(raw, str):
            entry = {"title": raw}
        elif isinstance(raw, dict):
            entry = dict(raw)
        else:
            raise ValueError(f"step {index} must be a string or a dict")
        title = str(entry.get("title") or "").strip()
        if not title:
            raise ValueError(f"step {index} has no title")
        step_id = str(entry.get("id") or f"{_slug(title)}_{index}").strip()
        if not step_id:
            step_id = f"step_{index}"
        depends = entry.get("depends") or []
        if isinstance(depends, str):
            depends = [depends]
        normalized.append({
            "id": step_id,
            "title": title,
            "status": _valid_step_status(entry.get("status")),
            "depends": [str(d) for d in depends],
            "result": entry.get("result") if "result" in entry else None,
        })
    ids = [s["id"] for s in normalized]
    if len(set(ids)) != len(ids):
        raise ValueError("step ids must be unique within a mission")
    for step in normalized:
        for dep in step["depends"]:
            if dep not in ids:
                raise ValueError(f"step '{step['id']}' depends on unknown step '{dep}'")
    return normalized


class MissionsEngine:

    def __init__(self, path=None):
        self.path = str(path) if path else _DEFAULT_PATH
        self.store = KeyValueStore(self.path)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # persistence helpers
    # ------------------------------------------------------------------
    def _registry(self):
        return dict(self.store.get(_REGISTRY_KEY) or {})

    def _save_registry(self, registry):
        self.store.set(_REGISTRY_KEY, registry)

    def _fetch(self, mission_id):
        mission = self._registry().get(str(mission_id))
        if mission is None:
            raise KeyError(f"unknown mission: {mission_id}")
        return mission

    def _upsert(self, mission):
        registry = self._registry()
        registry[mission["id"]] = mission
        self._save_registry(registry)
        return mission

    def _log(self, mission, event, detail="", step_id=None, **extra):
        entry = {"at": _now(), "event": event, "detail": detail}
        if step_id:
            entry["step_id"] = step_id
        entry.update(extra)
        mission.setdefault("checkpoint_log", []).append(entry)
        return entry

    def _audit(self, mission, event, reason=""):
        entry = {"at": _now(), "event": event, "reason": reason}
        mission.setdefault("audit", []).append(entry)
        return entry

    def _find_step(self, mission, step_id):
        step = next((s for s in mission["steps"] if s["id"] == str(step_id)), None)
        if step is None:
            raise KeyError(f"mission {mission['id']} has no step '{step_id}'")
        return step

    # ------------------------------------------------------------------
    # mission lifecycle
    # ------------------------------------------------------------------
    def create_mission(self, title, steps, priority=5, budget_seconds=None,
                       mission_id=None):
        _validate_mission(title, steps, priority, budget_seconds)
        normalized = _normalize_steps(steps)
        mid = str(mission_id) if mission_id else f"mission_{time.time_ns()}"
        mission = {
            "id": mid,
            "title": str(title).strip(),
            "goal": str(title).strip(),
            "priority": int(priority),
            "status": MISSION_ACTIVE,
            "created_at": _now(),
            "budget_seconds": float(budget_seconds) if budget_seconds is not None else None,
            "steps": normalized,
            "checkpoint_log": [],
            "audit": [],
            "escalations": [],
        }
        self._log(mission, "created", str(title))
        return self._upsert(mission)

    def get_mission(self, mission_id):
        return copy.deepcopy(self._fetch(mission_id))

    def list_missions(self, status=None):
        missions = self._registry()
        if status is None:
            return sorted(missions.keys())
        return sorted(mid for mid, m in missions.items() if m.get("status") == status)

    def steps(self, mission_id):
        mission = self._fetch(mission_id)
        return copy.deepcopy(mission["steps"])

    def audit(self, mission_id):
        mission = self._fetch(mission_id)
        return list(mission.get("audit", []))

    def import_mission(self, mission):
        """Upsert a full mission dict (used by ContinuityManager.resume)."""
        if not isinstance(mission, dict) or not str(mission.get("id") or ""):
            raise ValueError("import_mission requires a mission dict with an id")
        normalized = _normalize_steps(mission.get("steps") or [])
        merged = dict(mission)
        merged["steps"] = normalized
        merged.setdefault("title", str(mission.get("goal") or "mission"))
        merged.setdefault("goal", merged["title"])
        merged.setdefault("status", MISSION_ACTIVE)
        merged.setdefault("checkpoint_log", [])
        merged.setdefault("audit", [])
        merged.setdefault("escalations", [])
        return self._upsert(merged)

    # ------------------------------------------------------------------
    # status transitions
    # ------------------------------------------------------------------
    def start(self, mission_id, reason="started"):
        with self._lock:
            mission = self._fetch(mission_id)
            if mission["status"] in _TERMINAL:
                raise ValueError(f"mission is {mission['status']}; cannot start")
            mission["status"] = MISSION_ACTIVE
            self._log(mission, "started", reason)
            return self._upsert(mission)

    def pause(self, mission_id, reason="paused"):
        with self._lock:
            mission = self._fetch(mission_id)
            if mission["status"] == MISSION_PAUSED:
                return mission
            if mission["status"] in _TERMINAL:
                raise ValueError(f"mission is {mission['status']}; cannot pause")
            mission["status"] = MISSION_PAUSED
            self._log(mission, "paused", reason)
            return self._upsert(mission)

    def resume(self, mission_id, reason="resumed"):
        with self._lock:
            mission = self._fetch(mission_id)
            if mission["status"] != MISSION_PAUSED:
                raise ValueError("only a paused mission can be resumed")
            mission["status"] = MISSION_ACTIVE
            self._log(mission, "resumed", reason)
            return self._upsert(mission)

    def cancel(self, mission_id, reason="cancelled by user"):
        """Record a cancellation audit entry. Never hard-deletes the mission."""
        with self._lock:
            mission = self._fetch(mission_id)
            if mission["status"] in (MISSION_ARCHIVED, MISSION_COMPLETED):
                raise ValueError(f"mission is {mission['status']}; cannot cancel")
            mission["status"] = MISSION_FAILED
            for step in mission["steps"]:
                if step["status"] in (STEP_OPEN, STEP_RUNNING):
                    step["status"] = STEP_FAILED
            self._audit(mission, "cancelled", reason)
            self._log(mission, "cancelled", reason)
            return self._upsert(mission)

    def finish(self, mission_id, reason="all steps complete"):
        with self._lock:
            mission = self._fetch(mission_id)
            pending = [s["id"] for s in mission["steps"] if s["status"] != STEP_DONE]
            if pending:
                raise ValueError(
                    f"cannot finish mission: steps not done: {pending}"
                )
            mission["status"] = MISSION_COMPLETED
            self._log(mission, "finished", reason)
            return self._upsert(mission)

    def archive(self, mission_id):
        """Explicitly non-destructive: Archived missions stay in the store."""
        with self._lock:
            mission = self._fetch(mission_id)
            mission["status"] = MISSION_ARCHIVED
            self._audit(mission, "archived", "non-destructive archive")
            self._log(mission, "archived", "non-destructive archive")
            return self._upsert(mission)

    def append_steps(self, mission_id, steps):
        """Feature 113 bridge — extend a mission with new steps (additive).

        Only open missions accept new steps; IDs are made unique against the
        existing mission. Existing steps/statuses are never touched.
        """
        with self._lock:
            mission = self._fetch(mission_id)
            if mission["status"] in _TERMINAL:
                raise ValueError(
                    f"mission is {mission['status']}; cannot append steps")
            existing = {s["id"] for s in mission["steps"]}
            added = []
            for index, raw in enumerate(steps):
                if isinstance(raw, str):
                    entry = {"title": raw}
                elif isinstance(raw, dict):
                    entry = dict(raw)
                else:
                    raise ValueError(f"step {index} must be a string/dict")
                title = str(entry.get("title") or "").strip()
                if not title:
                    raise ValueError(f"step {index} has no title")
                step_id = str(entry.get("id")
                              or f"{_slug(title)}_{index}").strip()
                if not step_id or step_id in existing:
                    base = _slug(title)
                    step_id = base
                    n = 2
                    while step_id in existing:
                        step_id = f"{base}_{n}"
                        n += 1
                depends = entry.get("depends") or []
                if isinstance(depends, str):
                    depends = [depends]
                added.append({
                    "id": step_id,
                    "title": title,
                    "status": STEP_OPEN,
                    "depends": [str(d) for d in depends],
                    "result": None,
                })
                existing.add(step_id)
            mission["steps"].extend(added)
            self._audit(mission, "extended",
                        f"appended {len(added)} step(s)")
            self._log(mission, "steps_appended",
                      f"{len(added)} step(s)", step_id=None)
            return self._upsert(mission), {
                "added": [s["id"] for s in added],
                "mission_id": mission_id,
            }

    def retitle(self, mission_id, title):
        """Feature 113 bridge — redirect a mission goal/title (additive)."""
        with self._lock:
            mission = self._fetch(mission_id)
            new_title = str(title or "").strip()
            if not new_title:
                raise ValueError("redirect needs a non-empty title")
            old = mission["title"]
            mission["title"] = new_title
            mission["goal"] = new_title
            self._audit(mission, "redirected",
                        f"'{old}' -> '{new_title}'")
            self._log(mission, "redirected", f"'{old}' -> '{new_title}'")
            return self._upsert(mission)

    def escalate(self, mission_id, reason):
        """Set the mission blocked and return a structured escalation note."""
        with self._lock:
            mission = self._fetch(mission_id)
            mission["status"] = MISSION_BLOCKED
            note = {
                "mission_id": mission["id"],
                "at": _now(),
                "reason": str(reason),
                "status": MISSION_BLOCKED,
                "action_required": "human review",
                "external_action": "none",
            }
            mission.setdefault("escalations", []).append(note)
            self._log(mission, "escalated", str(reason))
            return self._upsert(mission), copy.deepcopy(note)

    def quarantine_mission(self, mission_id, reason="quarantined by continuity"):
        """Pause a misbehaving mission; audited, non-destructive."""
        with self._lock:
            mission = self._fetch(mission_id)
            mission["status"] = MISSION_PAUSED
            self._audit(mission, "quarantined", reason)
            self._log(mission, "quarantined", reason)
            return self._upsert(mission)

    # ------------------------------------------------------------------
    # step lifecycle
    # ------------------------------------------------------------------
    def run_step(self, mission_id, step_id, fn=None, timeout=10.0):
        with self._lock:
            mission = self._fetch(mission_id)
            step = self._find_step(mission, step_id)
            if mission["status"] in _TERMINAL:
                raise ValueError(
                    f"mission is {mission['status']}; cannot run steps"
                )
            for dep in step.get("depends", []):
                dep_step = self._find_step(mission, dep)
                if dep_step["status"] == STEP_DONE:
                    continue
                if dep_step["status"] == STEP_FAILED:
                    step["status"] = STEP_BLOCKED
                    self._log(
                        mission, "step_blocked",
                        f"dependency '{dep}' failed", step_id=step["id"],
                        dependency=dep,
                    )
                    self._upsert(mission)
                    return {"status": STEP_BLOCKED, "step_id": step["id"],
                            "mission_id": mission_id,
                            "reason": f"dependency '{dep}' failed"}
                self._log(
                    mission, "step_waiting",
                    f"dependency '{dep}' not done", step_id=step["id"],
                    dependency=dep,
                )
                self._upsert(mission)
                return {"status": "waiting", "step_id": step["id"],
                        "mission_id": mission_id,
                        "reason": f"dependency '{dep}' not done"}
            if step["status"] == STEP_DONE:
                return {"status": STEP_DONE, "step_id": step["id"],
                        "mission_id": mission_id, "result": step.get("result"),
                        "already_done": True}
            if step["status"] == STEP_BLOCKED:
                step["status"] = STEP_OPEN
            step["status"] = STEP_RUNNING
            self._log(mission, "step_started", step["title"], step_id=step["id"])
            self._upsert(mission)
            try:
                value = self._run_bound(step, fn, timeout)
            except TimeoutError as exc:
                step["status"] = STEP_FAILED
                step["result"] = {"error": str(exc)}
                self._log(mission, "step_timeout", str(exc), step_id=step["id"])
                self._upsert(mission)
                return {"status": STEP_FAILED, "step_id": step["id"],
                        "mission_id": mission_id, "reason": str(exc)}
            except Exception as exc:
                step["status"] = STEP_FAILED
                step["result"] = {"error": repr(exc)}
                self._log(mission, "step_failed", repr(exc), step_id=step["id"])
                self._upsert(mission)
                return {"status": STEP_FAILED, "step_id": step["id"],
                        "mission_id": mission_id, "reason": repr(exc)}
            step["status"] = STEP_DONE
            step["result"] = value
            self._log(mission, "step_done", step["title"], step_id=step["id"])
            self._upsert(mission)
            return {"status": STEP_DONE, "step_id": step["id"],
                    "mission_id": mission_id, "result": value}

    def _run_bound(self, step, fn, timeout):
        callable_fn = self._resolve(fn, step)
        op, kind, value = BoundedOperation.run(callable_fn, timeout=float(timeout))
        if kind == "interrupted":
            raise TimeoutError(
                f"step '{step['id']}' exceeded {timeout}s budget"
            )
        if kind == "error":
            raise RuntimeError(f"{value}")
        return value

    def _resolve(self, fn, step):
        if callable(fn):
            return fn
        if fn is None:
            return lambda: None
        from tools.builder import get_registry
        tool = get_registry().get(str(fn))
        if tool is None:
            raise ValueError(
                f"unknown tool '{fn}' for step '{step['id']}'"
            )
        return tool.function

    # ------------------------------------------------------------------
    # supervision output
    # ------------------------------------------------------------------
    def summary(self, mission_id):
        mission = self._fetch(mission_id)
        steps = mission["steps"]
        total = len(steps)
        done = sum(1 for s in steps if s["status"] == STEP_DONE)
        progress = round(100.0 * done / total, 1) if total else 0.0
        next_step = None
        for step in steps:
            if step["status"] != STEP_OPEN:
                continue
            if all(
                self._find_step(mission, dep)["status"] == STEP_DONE
                for dep in step.get("depends", [])
            ):
                next_step = {
                    "id": step["id"],
                    "title": step["title"],
                    "depends": list(step.get("depends", [])),
                }
                break
        return {
            "mission_id": mission["id"],
            "title": mission["title"],
            "status": mission["status"],
            "priority": mission.get("priority"),
            "progress_pct": progress,
            "steps_done": done,
            "steps_total": total,
            "next_actionable_step": next_step,
            "budget_seconds": mission.get("budget_seconds"),
        }

    def restore(self):
        """Re-read mission state from disk (simulates a restart)."""
        self.store = KeyValueStore(self.path)
        registry = self._registry()
        return {"restored": len(registry), "missions": sorted(registry.keys())}


MissionEngine = MissionsEngine

__all__ = [
    "MissionsEngine",
    "MissionEngine",
    "MISSION_ACTIVE",
    "MISSION_PAUSED",
    "MISSION_BLOCKED",
    "MISSION_COMPLETED",
    "MISSION_FAILED",
    "MISSION_ARCHIVED",
    "STEP_OPEN",
    "STEP_RUNNING",
    "STEP_DONE",
    "STEP_FAILED",
    "STEP_BLOCKED",
]