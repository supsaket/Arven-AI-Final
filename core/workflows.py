"""Feature 55 — Workflow Builder.

``WorkflowEngine`` validates & runs multi-step workflows in dependency order.
Steps may be registered tool names (validated against ``tools.builder``
registry at define time) or local callables. Risky steps require the shared
confirmation gate: an unconfirmed risky step pauses the run with
``requires_confirmation: True`` and is skipped until confirmed/trusted/
``request_id`` kwargs are supplied; progress persists so a run can be resumed.
Step execution is bounded by a timeout guard.
"""

import copy
import threading
import time

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.lifecycle import BoundedOperation
from tools.builder import get_registry

_KEY = "workflows.registry"
_TEMPLATE_KEY = "workflows.templates"
_DEFAULT_PATH = "data/runtime/workflows.json"

_RISKY_PREFIXES = (
    "send_", "delete_", "purchase_", "actuate_", "publish_", "wipe_",
    "exec_", "shell_", "format_", "email_", "calendar_", "messaging_",
    "shutdown_",
)


def _is_risky(action):
    name = action if isinstance(action, str) else getattr(action, "__name__", None)
    name = str(name or "callable").lower().strip()
    if name.startswith(_RISKY_PREFIXES):
        return True
    try:
        return bool(CONFIRMATION.requires_confirmation(name, ""))
    except Exception:
        return False


def _topo_order(steps):
    ids = [s["id"] for s in steps]
    indegree = {sid: 0 for sid in ids}
    dependents = {sid: [] for sid in ids}
    for step in steps:
        for dep in step.get("depends", []):
            if dep not in dependents:
                raise ValueError(f"step '{step['id']}' depends on unknown step '{dep}'")
            indegree[step["id"]] += 1
            dependents[dep].append(step["id"])
    queue = [sid for sid in ids if indegree[sid] == 0]
    order = []
    while queue:
        sid = queue.pop(0)
        order.append(sid)
        for dependent in dependents[sid]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if len(order) != len(ids):
        raise ValueError(f"workflow steps contain a cycle")
    return order


def _normalize_workflow_steps(steps, check_tools):
    normalized = []
    used = set()
    for index, raw in enumerate(steps):
        if isinstance(raw, str):
            entry = {"title": raw, "action": raw, "args": {}}
        elif isinstance(raw, dict):
            entry = dict(raw)
        else:
            raise ValueError(f"step {index} must be a string or a dict")
        action = entry.get("action")
        if action is None:
            raise ValueError(f"step {index} has no action")
        if not isinstance(action, str) and not callable(action):
            raise ValueError(
                f"step {index} action must be a tool name or a callable"
            )
        title = str(entry.get("title") or "").strip() or str(entry.get("step") or "")
        if not title:
            title = action if isinstance(action, str) else getattr(action, "__name__", "step")
        step_id = str(entry.get("id") or f"step_{index}").strip()
        if not step_id:
            step_id = f"step_{index}"
        if step_id in used:
            raise ValueError(f"duplicate step id '{step_id}'")
        used.add(step_id)
        depends = entry.get("depends") or []
        if isinstance(depends, str):
            depends = [depends]
        if isinstance(action, str) and check_tools and not get_registry().has(action):
            raise ValueError(f"unknown registered tool '{action}'")
        normalized.append({
            "id": step_id,
            "title": str(title),
            "action": action,
            "args": dict(entry.get("args") or {}),
            "depends": [str(d) for d in depends],
            "status": "pending",
            "result": None,
            "reason": None,
        })
    ids = [s["id"] for s in normalized]
    if len(set(ids)) != len(ids):
        raise ValueError("step ids must be unique")
    _topo_order(normalized)
    return normalized


class WorkflowEngine:

    def __init__(self, path=None):
        self.path = str(path) if path else _DEFAULT_PATH
        self.store = KeyValueStore(self.path)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    def _workflows(self):
        return dict(self.store.get(_KEY) or {})

    def _save(self, workflow):
        registry = self._workflows()
        registry[workflow["id"]] = workflow
        self.store.set(_KEY, registry)

    def _fetch(self, workflow_id):
        workflow = self._workflows().get(str(workflow_id))
        if workflow is None:
            raise KeyError(f"unknown workflow: {workflow_id}")
        return workflow

    def get(self, workflow_id):
        return copy.deepcopy(self._fetch(workflow_id))

    def list(self):
        return sorted(self._workflows().keys())

    # ------------------------------------------------------------------
    # templates
    # ------------------------------------------------------------------
    def save_template(self, name, steps):
        name = str(name).strip()
        if not name:
            raise ValueError("template name must be non-empty")
        cleaned = _normalize_workflow_steps(steps, check_tools=True)
        templates = dict(self.store.get(_TEMPLATE_KEY) or {})
        templates[name] = {"name": name, "steps": cleaned}
        self.store.set(_TEMPLATE_KEY, templates)
        return copy.deepcopy(templates[name])

    def get_template(self, name):
        templates = dict(self.store.get(_TEMPLATE_KEY) or {})
        if name not in templates:
            raise ValueError(f"unknown template '{name}'")
        return copy.deepcopy(templates[name])

    def list_templates(self):
        return sorted((self.store.get(_TEMPLATE_KEY) or {}).keys())

    # ------------------------------------------------------------------
    # definition
    # ------------------------------------------------------------------
    def define(self, name, steps=None, template=None, workflow_id=None):
        name = str(name).strip()
        if not name:
            raise ValueError("workflow name must be non-empty")
        if steps is None and template is not None:
            if isinstance(template, (list, tuple)):
                steps = list(template)
            else:
                steps = self.get_template(template)["steps"]
        if not steps:
            raise ValueError("a workflow needs at least one step")
        normalized = _normalize_workflow_steps(steps, check_tools=True)
        wf_id = str(workflow_id) if workflow_id else f"wf_{time.time_ns()}"
        workflow = {
            "id": wf_id,
            "name": name,
            "steps": normalized,
            "status": "ready",
            "created_at": time.time(),
            "audit": [],
            "run_id": None,
        }
        self._save(workflow)
        return copy.deepcopy(workflow)

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------
    def run(self, workflow_id, inputs=None, confirmed=False, trusted=False,
            request_id=None, timeout=30.0):
        with self._lock:
            workflow = self._fetch(workflow_id)
            if workflow["status"] == "aborted":
                return {"workflow_id": workflow_id, "status": "aborted",
                        "aborted": True,
                        "message": "workflow was aborted; define a new one"}
            inputs = dict(inputs or {})
            if request_id is not None:
                request_id = str(request_id)
            workflow["run_id"] = f"run_{time.time_ns()}"
            try:
                order = _topo_order(workflow["steps"])
            except ValueError as exc:
                return {"workflow_id": workflow_id, "status": "failed",
                        "message": str(exc)}
            step_map = {s["id"]: s for s in workflow["steps"]}
            workflow["status"] = "running"
            self._save(workflow)

            for step_id in order:
                step = step_map[step_id]
                if step["status"] == "done":
                    continue
                for dep in step.get("depends", []):
                    dep_step = step_map[dep]
                    if dep_step["status"] == "done":
                        continue
                    if dep_step["status"] == "failed":
                        step["status"] = "blocked"
                        step["reason"] = f"dependency '{dep}' failed"
                        workflow["status"] = "paused"
                        self._save(workflow)
                        return self._result(workflow, step_id, "blocked",
                                            step["reason"])
                    if dep_step["status"] == "requires_auth":
                        step["status"] = "requires_auth"
                        step["reason"] = f"dependency '{dep}' requires confirmation"
                        workflow["status"] = "paused"
                        self._save(workflow)
                        return self._result(
                            workflow, step_id, "requires_auth",
                            step["reason"], requires_confirmation=True,
                        )
                    step["status"] = "pending"
                    workflow["status"] = "paused"
                    self._save(workflow)
                    return self._result(workflow, step_id, "waiting",
                                        f"dependency '{dep}' not done")

                action = step["action"]
                risky = _is_risky(action)
                if risky and not (confirmed or trusted or request_id):
                    step["status"] = "requires_auth"
                    step["reason"] = f"step '{step_id}' is risky and unconfirmed"
                    workflow["status"] = "paused"
                    self._save(workflow)
                    return self._result(
                        workflow, step_id, "requires_auth", step["reason"],
                        requires_confirmation=True,
                    )

                merged = dict(inputs)
                merged.update(step.get("args", {}))
                step["status"] = "running"
                workflow["status"] = "running"
                self._save(workflow)

                kind, message = self._execute_step(
                    workflow, step, merged,
                    confirmed=confirmed, trusted=trusted,
                    request_id=request_id, timeout=timeout,
                )
                if kind == "requires_auth":
                    step["status"] = "requires_auth"
                    step["reason"] = message
                    workflow["status"] = "paused"
                    self._save(workflow)
                    return self._result(
                        workflow, step_id, "requires_auth", message,
                        requires_confirmation=True,
                    )
                if kind == "failed":
                    step["status"] = "failed"
                    step["reason"] = message
                    workflow["status"] = "paused"
                    self._save(workflow)
                    return self._result(workflow, step_id, "failed", message)
                step["status"] = "done"
                step["result"] = message
                step["reason"] = None
                workflow["status"] = "running"
                self._save(workflow)

            if all(s["status"] == "done" for s in workflow["steps"]):
                workflow["status"] = "completed"
            elif any(s["status"] == "requires_auth" for s in workflow["steps"]):
                workflow["status"] = "paused"
            else:
                workflow["status"] = "paused"
            self._save(workflow)
            return self._result(workflow, None, workflow["status"])

    def _execute_step(self, workflow, step, merged, confirmed, trusted,
                      request_id, timeout):
        action = step["action"]
        if isinstance(action, str):
            tool = get_registry().get(action)
            if tool is None:
                return "failed", (
                    f"tool '{action}' is not registered (definition may "
                    f"predate a restart)"
                )
            flags = {}
            if _is_risky(action):
                flags = {
                    "confirmed": confirmed,
                    "trusted": trusted,
                    "request_id": request_id,
                }
            result = get_registry().invoke(action, **merged, **flags)
            if result.get("status") in ("denied", "confirm_required", "unavailable"):
                return "requires_auth", result.get("message", "action requires confirmation")
            if not result.get("success", False):
                return "failed", result.get("message", f"{action} failed")
            return "done", result
        name = getattr(action, "__name__", None) or action.__class__.__name__
        if _is_risky(action):
            allowed, reason = CONFIRMATION.gate(
                name, "", confirmed=confirmed, trusted=trusted,
                request_id=request_id,
            )
            if not allowed:
                return "requires_auth", reason
        try:
            op, kind, value = BoundedOperation.run(
                lambda: action(**merged), timeout=float(timeout)
            )
        except Exception as exc:
            return "failed", repr(exc)
        if kind == "interrupted":
            return "failed", f"step '{step['id']}' exceeded {timeout}s budget"
        if kind == "error":
            return "failed", f"{value}"
        return "done", value

    def _result(self, workflow, step_id, status, message="", requires_confirmation=False):
        return {
            "workflow_id": workflow["id"],
            "name": workflow["name"],
            "run_id": workflow.get("run_id"),
            "status": status,
            "step_id": step_id,
            "message": message,
            "requires_confirmation": requires_confirmation,
            "completed": sum(
                1 for s in workflow["steps"] if s["status"] == "done"
            ),
            "steps": [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "status": s["status"],
                    "result": s.get("result"),
                    "reason": s.get("reason"),
                }
                for s in workflow["steps"]
            ],
        }

    # ------------------------------------------------------------------
    def abort(self, workflow_id, reason="aborted by user"):
        with self._lock:
            workflow = self._fetch(workflow_id)
            workflow["status"] = "aborted"
            workflow.setdefault("audit", []).append({
                "at": time.time(), "event": "aborted", "reason": str(reason),
            })
            self._save(workflow)
            return copy.deepcopy(workflow)


__all__ = ["WorkflowEngine", "_is_risky", "_topo_order"]