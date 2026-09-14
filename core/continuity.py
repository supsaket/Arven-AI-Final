"""Feature 101 — Long-Term Mission Continuity.

``ContinuityManager`` snapshots a mission's full state into its own kv store,
can ``resume()`` those snapshots back into a MissionsEngine on the same kv
path after a restart, and produces soft ― never destructive ― orphan and
quarantine reports.
"""

import copy
import time

from core.kv import KeyValueStore

_SNAP_KEY = "continuity.snapshots"
_DEFAULT_PATH = "data/runtime/continuity.json"


class ContinuityManager:

    def __init__(self, path=None, engine=None):
        self.path = str(path) if path else _DEFAULT_PATH
        self.store = KeyValueStore(self.path)
        self.engine = engine

    # ------------------------------------------------------------------
    def _snapshots(self):
        return dict(self.store.get(_SNAP_KEY) or {})

    def snapshot(self, mission_id, engine=None):
        engine = engine or self.engine
        if engine is None:
            raise ValueError("an engine is required to snapshot a mission")
        mission = engine.get_mission(mission_id)
        snap = {
            "ts": time.time(),
            "mission_id": str(mission_id),
            "mission_state": copy.deepcopy(mission),
            "pending": [
                s["id"] for s in mission["steps"] if s["status"] != "done"
            ],
        }
        snaps = self._snapshots()
        snaps[snap["mission_id"]] = snap
        self.store.set(_SNAP_KEY, snaps)
        return copy.deepcopy(snap)

    def resume(self, engine=None):
        engine = engine or self.engine
        if engine is None:
            raise ValueError("an engine is required to resume missions")
        plan = []
        for mission_id in sorted(self._snapshots()):
            snap = self._snapshots()[mission_id]
            state = snap.get("mission_state")
            restored = False
            if state:
                engine.import_mission(state)
                restored = True
            plan.append({
                "mission_id": mission_id,
                "title": state.get("title") if state else None,
                "snapshot_ts": snap.get("ts"),
                "pending": snap.get("pending", []),
                "status": state.get("status") if state else None,
                "restored": restored,
            })
        return plan

    def orphan_report(self, engine=None):
        """Soft report of step/mission references whose parent is missing.

        Never deletes anything; entries are advisory only.
        """
        engine = engine or self.engine
        present = set(engine.list_missions()) if engine is not None else set()
        reports = []
        for mission_id, snap in self._snapshots().items():
            if engine is not None and mission_id not in present:
                reports.append({
                    "kind": "orphan_snapshot",
                    "mission_id": mission_id,
                    "severity": "soft",
                    "note": "snapshot references a mission missing from the engine",
                })
            state = snap.get("mission_state") or {}
            step_ids = {s["id"] for s in state.get("steps", [])}
            for step in state.get("steps", []):
                for dep in step.get("depends", []):
                    if dep not in step_ids:
                        reports.append({
                            "kind": "orphan_step",
                            "mission_id": mission_id,
                            "step_id": step["id"],
                            "depends": dep,
                            "severity": "soft",
                            "note": f"step references missing dependency '{dep}'",
                        })
        return reports

    def quarantine(self, mission_id=None, reason="quarantined by continuity",
                   engine=None):
        """Pause orphaned/misbehaving missions. Audited, never deletes."""
        engine = engine or self.engine
        if engine is None:
            raise ValueError("an engine is required to quarantine missions")
        if mission_id is not None:
            targets = [str(mission_id)]
        else:
            targets = [
                mid for mid in engine.list_missions()
                if engine.get_mission(mid).get("status") == "blocked"
            ]
        quarantined = []
        for mid in targets:
            try:
                engine.quarantine_mission(mid, reason=reason)
                quarantined.append(mid)
            except KeyError:
                continue
        return {
            "quarantined": quarantined,
            "deleted": 0,
            "action": "paused",
            "note": "quarantine is non-destructive",
        }


__all__ = ["ContinuityManager"]