"""Engineering Design & Coding Assistant (Day 2, feature 95).

Spec assembly, sprint board, built-in review checklists and a real experiment
log with average/min/max metrics, plus markdown export.
"""

import uuid
from datetime import datetime

from core.kv import KeyValueStore
from core.output import output_manager

CHECKLISTS = {
    "code_review": [
        "Logic is correct and covered by tests",
        "Edge cases and error paths handled",
        "No secrets or credentials committed",
        "Naming and structure match conventions",
        "Dependencies are justified and pinned",
    ],
    "design_review": [
        "Requirements are traced to components",
        "Interfaces are explicit and stable",
        "Failure modes are documented",
        "Scalability / performance considered",
        "Security and privacy by design",
    ],
}


class EngineeringProjects:

    def __init__(self, kv=None, output_dir="Output/Engineering"):
        self.kv = kv or KeyValueStore("data/engineering.json")
        self.output_dir = output_dir

    # ------------------------------------------------------------------
    def _now(self):
        return datetime.now().isoformat()

    # ------------------------------------------------------------------
    def create_spec(self, name, requirements, interfaces):
        spec = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "requirements": list(requirements),
            "interfaces": list(interfaces),
            "created_at": self._now(),
            "status": "draft",
        }
        specs = self.kv.get("specs", {})
        specs[name] = spec
        self.kv.set("specs", specs)
        return spec

    def get_spec(self, name):
        return self.kv.get("specs", {}).get(name)

    def specs(self):
        return list(self.kv.get("specs", {}).values())

    # ------------------------------------------------------------------
    def add_task(self, name, title, assignee, est_hours,
                 column="To Do"):
        board = self.kv.get("sprint_board", {})
        task = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "title": title,
            "assignee": assignee,
            "est_hours": float(est_hours),
            "column": column,
            "status": "open",
            "created_at": self._now(),
        }
        board[task["id"]] = task
        self.kv.set("sprint_board", board)
        return task

    def sprint_board(self):
        tasks = list(self.kv.get("sprint_board", {}).values())
        tasks.sort(key=lambda t: t["created_at"])
        return tasks

    def move_task(self, task_id, column):
        board = self.kv.get("sprint_board", {})
        if task_id not in board:
            raise KeyError(f"no task '{task_id}'")
        board[task_id]["column"] = column
        self.kv.set("sprint_board", board)
        return board[task_id]

    # ------------------------------------------------------------------
    def review_checklist(self, category):
        if category not in CHECKLISTS:
            raise KeyError(f"no checklist '{category}'; "
                           f"known: {sorted(CHECKLISTS)}")
        return list(CHECKLISTS[category])

    def run_review(self, category, name=None, passed=None):
        items = self.review_checklist(category)
        if passed is not None and not isinstance(passed, (list, tuple)):
            raise TypeError("passed must be a list of item indices/strings")
        record = {
            "category": category,
            "name": name,
            "items": items,
            "passed": list(passed) if passed else [],
            "at": self._now(),
        }
        reviews = self.kv.get("reviews", [])
        reviews.append(record)
        self.kv.set("reviews", reviews)
        return record

    # ------------------------------------------------------------------
    def record_measurement(self, name, metric, value, unit, ts=None):
        value = float(value)
        entry = {
            "name": name,
            "metric": metric,
            "value": value,
            "unit": unit,
            "ts": ts or self._now(),
        }
        log = self.kv.get("measurements", [])
        log.append(entry)
        self.kv.set("measurements", log)
        values = [e["value"] for e in log if e["metric"] == metric]
        return {
            "recorded": entry,
            "metric": metric,
            "count": len(values),
            "average": round(sum(values) / len(values), 4),
            "min": min(values),
            "max": max(values),
        }

    def measurements(self, metric=None):
        log = self.kv.get("measurements", [])
        if metric:
            return [e for e in log if e["metric"] == metric]
        return log

    # ------------------------------------------------------------------
    def export(self, name, directory=None):
        target = directory or self.output_dir
        spec = self.get_spec(name)
        if spec is None:
            raise KeyError(f"no spec '{name}'")
        lines = [f"# Engineering Design — {name}",
                 f"> Generated {self._now()}", "",
                 "## Requirements", ""]
        lines.extend(f"- {r}" for r in spec["requirements"])
        lines += ["", "## Interfaces", ""]
        lines.extend(f"- {i}" for i in spec["interfaces"])
        lines += ["", "## Sprint Board", ""]
        for task in self.sprint_board():
            if task["name"] == name:
                lines.append(
                    f"- [{task['column']}] {task['title']} "
                    f"({task['assignee']}, {task['est_hours']}h)")
        content = "\n".join(lines) + "\n"
        result = output_manager.write(target, f"engineering_{name}.md", content)
        return result["path"]


__all__ = ["EngineeringProjects", "CHECKLISTS"]