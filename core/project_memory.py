"""Project Memory (Day 2, feature 103).

Persisted project vault with phases, check-ins, decisions log, risk register
and artifact list. Restores across restarts via the shared key-value store.
"""

import uuid
from datetime import datetime

from core.kv import KeyValueStore


class ProjectVault:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/project_memory.json")

    # ------------------------------------------------------------------
    def _projects(self):
        return self.kv.get("projects", {})

    def _put(self, project):
        projects = self._projects()
        projects[project["name"]] = project
        self.kv.set("projects", projects)

    def _now(self):
        return datetime.now().isoformat()

    # ------------------------------------------------------------------
    def create_project(self, name, phases=None, initial_status="active"):
        phases = phases or [
            {"id": "spec", "title": "Specification", "status": "open"},
            {"id": "build", "title": "Building", "status": "open"},
            {"id": "review", "title": "Review", "status": "open"},
            {"id": "done", "title": "Done", "status": "open"},
        ]
        project = {
            "name": name,
            "phases": list(phases),
            "status": initial_status,
            "artifacts": [],
            "decisions": [],
            "risk_register": [],
            "created_at": self._now(),
        }
        self._put(project)
        return project

    def check_in(self, name, phase_id, note):
        project = self.query_project(name)
        status_ok = False
        for phase in project["phases"]:
            if phase["id"] == phase_id:
                status_ok = True
        if not status_ok:
            raise KeyError(f"no phase '{phase_id}' in project '{name}'")
        project["decisions"].append({
            "ts": self._now(), "text": note, "phase": phase_id,
        })
        self._put(project)
        return project["decisions"][-1]

    def advance_phase(self, name, phase_id):
        project = self.query_project(name)
        target_index = None
        for index, phase in enumerate(project["phases"]):
            if phase["id"] == phase_id:
                target_index = index
        if target_index is None:
            raise KeyError(f"no phase '{phase_id}' in project '{name}'")
        for index, phase in enumerate(project["phases"]):
            if index < target_index:
                phase["status"] = "closed"
            elif index == target_index:
                phase["status"] = "complete"
            else:
                phase["status"] = "open"
        self._put(project)
        return project["phases"]

    @staticmethod
    def _phase_index(project, phase_id):
        for index, phase in enumerate(project["phases"]):
            if phase["id"] == phase_id:
                return index
        return len(project["phases"])

    def update_risk(self, name, title, likelihood=None, impact=None):
        project = self.query_project(name)
        entry = {
            "title": title,
            "likelihood": likelihood,
            "impact": impact,
            "severity": _severity(likelihood, impact),
            "at": self._now(),
        }
        project["risk_register"].append(entry)
        self._put(project)
        return entry

    def add_artifact(self, name, path):
        project = self.query_project(name)
        project["artifacts"].append({"path": path, "at": self._now()})
        self._put(project)
        return project["artifacts"][-1]

    def query_project(self, name):
        project = self._projects().get(name)
        if project is None:
            raise KeyError(f"no project '{name}'")
        return project

    def project_status(self, name):
        project = self.query_project(name)
        return {
            "name": name,
            "status": project["status"],
            "phases": [{"id": p["id"], "status": p["status"]}
                       for p in project["phases"]],
            "decisions": len(project["decisions"]),
            "risks": len(project["risk_register"]),
            "artifacts": len(project["artifacts"]),
        }

    def projects(self):
        return sorted(self._projects())


def _severity(likelihood, impact):
    try:
        return round(float(likelihood or 0) * float(impact or 0), 2)
    except (TypeError, ValueError):
        return None


__all__ = ["ProjectVault"]