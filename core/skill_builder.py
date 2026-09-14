"""Feature 56 — Skill Creation.

``SkillStore`` defines named skills with a parameter schema and a procedure of
steps whose actions resolve to registered tools or local callables. ``invoke``
validates required/extra parameters, type-coerces arguments, runs each step
under a timeout guard, gates risky actions through the shared confirmation
system, and returns a full execution trace. ``share`` exports a real JSON
definition.
"""

import copy
import json
import threading
import time

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.lifecycle import BoundedOperation
from tools.builder import get_registry

_KEY = "skills.registry"
_DEFAULT_PATH = "data/runtime/skills.json"

ALLOWED_TYPES = {"string", "text", "int", "float", "number", "bool", "any", "list"}

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


class SkillStore:

    def __init__(self, path=None):
        self.path = str(path) if path else _DEFAULT_PATH
        self.store = KeyValueStore(self.path)
        self._verify_callables = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    def _skills(self):
        return dict(self.store.get(_KEY) or {})

    def _save(self, skills):
        self.store.set(_KEY, skills)

    # ------------------------------------------------------------------
    def define(self, name, description="", parameters=None, procedure=None,
               verify=None):
        name = str(name).strip()
        if not name:
            raise ValueError("skill name must be non-empty")
        params = []
        seen = set()
        for raw in (parameters or []):
            param = dict(raw)
            pname = str(param.get("name") or "").strip()
            if not pname:
                raise ValueError("parameter is missing a name")
            if pname in seen:
                raise ValueError(f"duplicate parameter '{pname}'")
            seen.add(pname)
            ptype = str(param.get("type") or "any").strip().lower()
            if ptype not in ALLOWED_TYPES:
                raise ValueError(f"unsupported parameter type '{ptype}'")
            params.append({
                "name": pname,
                "type": ptype,
                "required": bool(param.get("required", True)),
            })
        if not procedure:
            raise ValueError("a skill procedure must contain at least one step")
        proc = []
        for index, raw in enumerate(procedure):
            step_id = (
                str(raw.get("step") or raw.get("title") or "").strip()
                if isinstance(raw, dict) else str(raw)
            )
            if not step_id:
                step_id = f"step_{index}"
            detail = str(raw.get("detail") or "") if isinstance(raw, dict) else ""
            action = raw.get("action") if isinstance(raw, dict) else raw
            if action is None:
                raise ValueError(f"procedure step {index} is missing an action")
            if not isinstance(action, str) and not callable(action):
                raise ValueError(
                    f"procedure step action must be a tool name or a callable"
                )
            if isinstance(action, str) and not get_registry().has(action):
                raise ValueError(f"unknown registered tool '{action}'")
            proc.append({"step": step_id, "detail": detail, "action": action})

        verify_name = None
        if verify is not None:
            if isinstance(verify, str):
                if not get_registry().has(verify):
                    raise ValueError(f"unknown verify tool '{verify}'")
                verify_name = verify
            elif callable(verify):
                verify_name = f"{name}:verify"
                with self._lock:
                    self._verify_callables[verify_name] = verify
            else:
                raise ValueError("verify must be a tool name or a callable")

        skill = {
            "name": name,
            "description": str(description),
            "parameters": params,
            "procedure": proc,
            "verify": verify_name,
            "created_at": time.time(),
        }
        skills = self._skills()
        skills[name] = skill
        self._save(skills)
        return copy.deepcopy(skill)

    def get(self, name):
        skill = self._skills().get(str(name))
        return copy.deepcopy(skill) if skill else None

    def list(self):
        return sorted(self._skills().keys())

    def share(self, name):
        skill = self.get(name)
        if skill is None:
            raise ValueError(f"unknown skill: {name}")
        return json.dumps(skill, indent=2, default=str)

    # ------------------------------------------------------------------
    def _coerce(self, value, param):
        ptype = param["type"]
        try:
            if ptype == "int":
                return int(value)
            if ptype in ("float", "number"):
                return float(value)
            if ptype == "bool":
                if isinstance(value, bool):
                    return value
                return str(value).strip().lower() in ("1", "true", "yes", "on")
            if ptype == "list":
                if isinstance(value, (list, tuple)):
                    return list(value)
                return [value]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"parameter '{param['name']}' requires {ptype}: {exc}"
            )
        return value

    def invoke(self, skill_name, arguments=None, confirmed=False, trusted=False,
               request_id=None, timeout=30.0):
        skill = self.get(skill_name)
        if skill is None:
            raise ValueError(f"unknown skill: {skill_name}")
        declared = {p["name"]: p for p in skill["parameters"]}
        args = dict(arguments or {})
        unexpected = [k for k in args if k not in declared]
        if unexpected:
            raise ValueError(f"unexpected parameter(s): {unexpected}")
        missing = [
            p["name"] for p in skill["parameters"]
            if p["required"] and p["name"] not in args
        ]
        if missing:
            raise ValueError(f"missing required parameter(s): {missing}")
        coerced = {}
        for param in skill["parameters"]:
            if param["name"] in args:
                coerced[param["name"]] = self._coerce(args[param["name"]], param)
            else:
                coerced[param["name"]] = None

        trace = []
        outputs = {}
        for item in skill["procedure"]:
            action = item["action"]
            step_name = item["step"]
            display = (
                action if isinstance(action, str)
                else getattr(action, "__name__", "callable")
            )
            entry = {
                "step": step_name,
                "detail": item["detail"],
                "action": display,
                "status": "pending",
                "message": "",
            }
            risky = _is_risky(action)
            if risky and not (confirmed or trusted or request_id):
                entry["status"] = "requires_auth"
                entry["message"] = "action requires confirmation"
                trace.append(entry)
                continue
            if risky and isinstance(action, str):
                result = get_registry().invoke(
                    action, **coerced,
                    confirmed=confirmed, trusted=trusted,
                    request_id=request_id,
                )
                if result.get("status") in ("denied", "confirm_required", "unavailable"):
                    entry["status"] = "requires_auth"
                    entry["message"] = result.get("message", "action requires confirmation")
                    trace.append(entry)
                    continue
                if not result.get("success", False):
                    entry["status"] = "failed"
                    entry["message"] = result.get("message", f"{action} failed")
                    trace.append(entry)
                    outputs.setdefault(step_name, result)
                    continue
                entry["status"] = "done"
                entry["message"] = "ok"
                outputs.setdefault(step_name, result)
                trace.append(entry)
                continue
            if risky:
                name = getattr(action, "__name__", None) or "callable"
                allowed, reason = CONFIRMATION.gate(
                    name, "", confirmed=confirmed, trusted=trusted,
                    request_id=request_id,
                )
                if not allowed:
                    entry["status"] = "requires_auth"
                    entry["message"] = reason
                    trace.append(entry)
                    continue
            try:
                if isinstance(action, str):
                    result = get_registry().invoke(action, **coerced)
                    if not result.get("success", False):
                        entry["status"] = "failed"
                        entry["message"] = result.get("message", f"{action} failed")
                        trace.append(entry)
                        outputs.setdefault(step_name, result)
                        continue
                    value = result
                else:
                    op, kind, value = BoundedOperation.run(
                        lambda: action(**copy.deepcopy(coerced)),
                        timeout=float(timeout),
                    )
                    if kind == "interrupted":
                        entry["status"] = "failed"
                        entry["message"] = (
                            f"step '{step_name}' exceeded {timeout}s budget"
                        )
                        trace.append(entry)
                        continue
                    if kind == "error":
                        entry["status"] = "failed"
                        entry["message"] = f"{value}"
                        trace.append(entry)
                        continue
                entry["status"] = "done"
                entry["message"] = "ok"
                outputs.setdefault(step_name, value)
            except Exception as exc:
                entry["status"] = "failed"
                entry["message"] = repr(exc)
            trace.append(entry)

        all_done = all(t["status"] == "done" for t in trace)
        any_auth = any(t["status"] == "requires_auth" for t in trace)
        if all_done:
            status = "completed"
        elif any_auth:
            status = "requires_auth"
        else:
            status = "failed"
        return {
            "skill": skill_name,
            "status": status,
            "steps": trace,
            "outputs": outputs,
            "requires_confirmation": any_auth,
        }

    # ------------------------------------------------------------------
    def verify(self, skill_name, evidence=None):
        skill = self.get(skill_name)
        if skill is None:
            raise ValueError(f"unknown skill: {skill_name}")
        verifier = skill.get("verify")
        if not verifier:
            return {"skill": skill_name, "verified": None,
                    "message": "no verifier defined"}
        evidence = dict(evidence or {})
        with self._lock:
            callable_verifier = self._verify_callables.get(verifier)
        if callable_verifier is not None:
            try:
                result = callable_verifier(**evidence)
            except Exception as exc:
                return {"skill": skill_name, "verified": False,
                        "source": "runtime-callable",
                        "message": f"verifier error: {exc}"}
            if isinstance(result, dict):
                verified = bool(result.get("verified", result.get("success", False)))
            else:
                verified = bool(result)
            return {"skill": skill_name, "verified": verified,
                    "source": "runtime-callable"}
        if get_registry().has(verifier):
            result = get_registry().invoke(verifier, **evidence)
            return {"skill": skill_name,
                    "verified": bool(result.get("success", False)),
                    "source": "tool", "message": result.get("message", "ok")}
        return {"skill": skill_name, "verified": False,
                "source": "unavailable",
                "message": "verifier not available after restart (runtime callable)"}


__all__ = ["SkillStore", "_is_risky"]