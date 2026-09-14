"""Feature 113 — Mid-Turn Mission Steering.

Steer an ACTIVE orchestrated mission while it runs, without restarting it:

* ``classify(instruction)`` — decide, explicitly, what kind of steering the
  operator wants (modify / extend / cancel / redirect / pause / resume /
  query / unknown). The classifier is keyword-driven and never guesses: an
  instruction it cannot confidently map is ``unknown``.
* ``apply(instruction, mission_id, **opts)`` — the current mission is steered
  NOW through the real mission API:
    - pause   -> MissionsEngine.pause (mid-turn halt)
    - resume  -> MissionsEngine.resume (+ MissionOrchestrator resume so the
                 remaining open steps keep dispatching)
    - cancel  -> MissionOrchestrator.cancel (audited, non-destructive)
    - extend  -> MissionsEngine.append_steps (new steps, additive)
    - redirect-> MissionsEngine.retitle (goal rewritten, steps preserved)
    - modify  -> recorded intent (no honest in-flight rewrite of running
                 steps is possible without discarding work) — applied as a
                 documented steering directive on the report
* ``checkpoint(mission_id)`` — poll hook the orchestrator may call between
  steps: auto-applies queued pause/cancel intents so a synchronous run can
  honour mid-turn steering; returns ``halt`` when the run should stop.
* every steering event (instruction, kind, decision, at, mission_id) is
  persisted and restored on restart (``restore``) so nothing is silently lost.

Completed work is NEVER discarded: extend/redirect keep the step history and
all DONE step results. ``unknown`` classifications are surfaced, not guessed.
"""

import re
import time

from core.kv import KeyValueStore

_DEFAULT_KV = "data/mission_steering.json"

STEERING_KINDS = ("modify", "extend", "cancel", "redirect", "pause",
                  "resume", "query", "unknown")

_PAUSE_PATTERNS = (
    "pause", "hold", "stop for now", "freeze", "halt", "wait a moment",
    "do not continue", "hold on",
)
_RESUME_PATTERNS = ("resume", "continue", "proceed", "carry on", "keep going",
                    "unpause", "restart the mission")
_CANCEL_PATTERNS = ("cancel", "abort", "drop", "kill the mission", "scrap",
                    "halt completely", "stop the mission", "end the mission")
_EXTEND_PATTERNS = ("add a step", "add step", "add another step",
                    "add the step", "include a step", "append a step",
                    "one more step", "add more steps", "new step")
_REDIRECT_PATTERNS = ("redirect", "instead focus", "change goal",
                      "change the goal", "new goal", "focus on",
                      "target something different", "aim at")
_MODIFY_PATTERNS = ("modify", "adjust", "tweak", "update the plan",
                    "change the plan", "revise", "change that step")
_QUERY_PATTERNS = ("what is the status", "status of the mission",
                   "how is it going", "where are we", "progress report")


def _has_any(text, patterns):
    return any(p in text for p in patterns)


def _now():
    return time.time()


class MissionSteering:
    """Classify + apply + persist mid-turn mission steering intents."""

    def __init__(self, kv_path=None, missions=None, orchestrator=None):
        self.path = str(kv_path) if kv_path else _DEFAULT_KV
        self.store = KeyValueStore(self.path)
        self._missions = missions
        self._orchestrator = orchestrator
        self._checkpoint_marks = {}

    # ------------------------------------------------------------------
    # wiring (injectable for tests)
    # ------------------------------------------------------------------
    def _missions_instance(self):
        if self._missions is not None:
            return self._missions
        from core.missions import MissionsEngine
        return MissionsEngine()

    def _orchestrator_instance(self):
        if self._orchestrator is not None:
            return self._orchestrator
        from core.mission_orchestrator import MissionOrchestrator
        return MissionOrchestrator()

    # ------------------------------------------------------------------
    # classification
    # ------------------------------------------------------------------
    def classify(self, instruction):
        text = str(instruction or "").strip().lower()
        if not text:
            return {"kind": "unknown", "reason": "empty instruction"}
        if _has_any(text, _PAUSE_PATTERNS):
            return {"kind": "pause", "reason": "keyword match"}
        if _has_any(text, _RESUME_PATTERNS):
            return {"kind": "resume", "reason": "keyword match"}
        if _has_any(text, _CANCEL_PATTERNS):
            return {"kind": "cancel", "reason": "keyword match"}
        if _has_any(text, _EXTEND_PATTERNS):
            return {"kind": "extend", "reason": "keyword match"}
        if _has_any(text, _REDIRECT_PATTERNS):
            return {"kind": "redirect", "reason": "keyword match"}
        if _has_any(text, _MODIFY_PATTERNS):
            return {"kind": "modify", "reason": "keyword match"}
        if _has_any(text, _QUERY_PATTERNS):
            return {"kind": "query", "reason": "keyword match"}
        return {"kind": "unknown",
                "reason": "no steering keyword matched; not guessed"}

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _events(self):
        return list(self.store.get("events") or [])

    def _save_events(self, events):
        self.store.set("events", events[-500:])

    def _record(self, event):
        events = self._events()
        events.append(event)
        self._save_events(events)
        return event

    # ------------------------------------------------------------------
    # apply
    # ------------------------------------------------------------------
    def apply(self, instruction, mission_id, options=None, record=True):
        """Apply a steering instruction to the named mission right now.

        ``record=False`` is used by the checkpoint hook so auto-applied
        intents never duplicate operator events in the history.
        """
        options = dict(options or {})
        mission_id = str(mission_id or "").strip()
        classified = self.classify(instruction)
        kind = classified["kind"]
        event = {
            "at": _now(), "mission_id": mission_id,
            "instruction": str(instruction or "").strip(),
            "kind": kind, "reason": classified["reason"],
            "options": {k: v for k, v in options.items()
                        if k in ("title", "steps", "reason")},
        }
        if not mission_id:
            event["decision"] = "invalid_argument"
            event["detail"] = "mission_id missing"
            if record:
                self._record(event)
            return {"success": False, "status": "invalid_argument",
                    "message": "mission_id is empty", "event": event}
        if kind == "unknown":
            event["decision"] = "needs_review"
            event["detail"] = "classification unknown; nothing applied"
            if record:
                self._record(event)
            return {"success": False, "status": "invalid_argument",
                    "message": "steering classified unknown — nothing "
                               "applied (no guessing)",
                    "event": event}

        missions = self._missions_instance()
        try:
            current = missions.get_mission(mission_id)
        except KeyError as exc:
            event["decision"] = "invalid_argument"
            event["detail"] = str(exc)
            if record:
                self._record(event)
            return {"success": False, "status": "invalid_argument",
                    "message": str(exc), "mission_id": mission_id,
                    "event": event}
        if current["status"] in ("completed", "failed", "archived") \
                and kind in ("pause", "resume", "extend", "redirect"):
            event["decision"] = "rejected"
            event["detail"] = f"mission is {current['status']}"
            if record:
                self._record(event)
            return {"success": False, "status": "ok",
                    "message": f"mission is {current['status']}; "
                               f"'{kind}' not applied",
                    "mission_id": mission_id, "event": event}

        try:
            outcome = self._dispatch(kind, mission_id, current, options)
        except (KeyError, ValueError) as exc:
            event["decision"] = "error"
            event["detail"] = repr(exc)
            if record:
                self._record(event)
            return {"success": False, "status": "error",
                    "message": repr(exc), "mission_id": mission_id,
                    "event": event}
        event["decision"] = "applied"
        event["detail"] = outcome["message"]
        if record:
            self._record(event)
        result = {"success": True, "status": "ok", "mission_id": mission_id,
                  "kind": kind, "instruction": event["instruction"],
                  "message": outcome["message"], "event": event}
        result.update(outcome.get("extra") or {})
        return result

    def _dispatch(self, kind, mission_id, current, options):
        missions = self._missions_instance()
        if kind == "pause":
            missions.pause(mission_id, reason="mid-turn steering: pause")
            return {"message": "mission paused (mid-turn)"}
        if kind == "resume":
            try:
                missions.resume(mission_id, reason="mid-turn steering: resume")
            except ValueError:
                pass  # already active
            resumed = self._orchestrator_instance().resume(mission_id)
            status = resumed.get("status", "ok")
            return {"message": f"mission resumed; orchestrator status: "
                               f"{status}", "extra": {"resume": resumed}}
        if kind == "cancel":
            self._orchestrator_instance().cancel(
                mission_id, reason="mid-turn steering: cancel")
            return {"message": "mission cancelled (audited, non-destructive)"}
        if kind == "extend":
            steps = options.get("steps") or []
            if not steps:
                return {"message": "extend requires steps in options"}
            prepared = [{"title": str(s).strip()} if isinstance(s, str)
                        else dict(s) for s in steps]
            _, added = missions.append_steps(mission_id, prepared)
            return {"message": f"appended {len(added['added'])} step(s)",
                    "extra": {"added": added["added"]}}
        if kind == "redirect":
            title = str(options.get("title") or "").strip() \
                or str(options.get("goal") or "").strip()
            if not title:
                return {"message": "redirect requires a new title/goal"}
            missions.retitle(mission_id, title)
            return {"message": f"mission redirected -> '{title}'"}
        if kind == "modify":
            # Honest: in-flight running steps cannot be rewritten without
            # discarding work. Recorded as a directive on the report.
            detail = str(options.get("detail")
                         or "modify directive recorded (no step rewriting)")
            return {"message": "modify directive recorded",
                    "extra": {"modify_directive": detail}}
        if kind == "query":
            summary = missions.summary(mission_id)
            return {"message": f"mission progress "
                               f"{summary['progress_pct']}% — "
                               f"{summary['status']}",
                    "extra": {"summary": summary}}
        return {"message": f"steering kind '{kind}' handled as no-op"}

    # ------------------------------------------------------------------
    # mid-turn checkpoint hook (between-steps consultation)
    # ------------------------------------------------------------------
    def checkpoint(self, mission_id):
        """Consult queued intents; auto-apply pause/cancel/others.

        Returns ``halt`` = True when a synchronous orchestrator loop should
        stop advancing steps (pause or cancel applied). Each intent is only
        auto-applied once per mission (tracked by a checkpoint watermark).
        """
        mission_id = str(mission_id or "").strip()
        since = self._checkpoint_marks.get(mission_id, 0.0)
        events = self._events()
        pending = [e for e in events
                   if e.get("mission_id") == mission_id
                   and e.get("decision") == "applied"
                   and float(e.get("at") or 0.0) > since]
        halt = False
        applied = []
        for event in pending:
            kind = event.get("kind", "unknown")
            if kind in ("pause", "cancel", "resume") and not halt:
                self.apply(f"checkpoint:{kind}", mission_id, record=False)
                applied.append(kind)
                if kind != "resume":
                    halt = True
            elif kind not in ("pause", "cancel", "resume"):
                applied.append(kind)
        self._checkpoint_marks[mission_id] = time.time()
        return {"halt": halt, "applied": applied,
                "mission_id": mission_id}

    # ------------------------------------------------------------------
    # reporting
    # ------------------------------------------------------------------
    def history(self, mission_id=None):
        events = self._events()
        if mission_id is not None:
            events = [e for e in events
                      if e.get("mission_id") == str(mission_id)]
        return list(reversed(events[-100:]))

    def restore(self):
        self.store = KeyValueStore(self.path)
        events = self._events()
        return {"restored": len(events), "events": events[-20:]}

    def status(self):
        events = self._events()
        kinds = {}
        for e in events:
            k = e.get("kind", "unknown")
            kinds[k] = kinds.get(k, 0) + 1
        return {
            "total_events": len(events),
            "by_kind": kinds,
            "pending_unknown": sum(
                1 for e in events if e.get("decision") == "needs_review"),
        }


mission_steering = MissionSteering()

__all__ = [
    "MissionSteering", "mission_steering",
    "STEERING_KINDS", "classify",
]