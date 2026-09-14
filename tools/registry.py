"""Tool registry — reliable registration, discovery and execution.

Contract (from verify_registry.py / nodeids):

* ``Tool`` : ``name``, ``category``, ``backend``, ``risk``, ``available``,
  ``confirm_required``, ``function``, ``schema()`` (``{"parameters": [...],
  "risk": ..., "confirm_required": bool, "backend": str}``), ``status()``.
* ``ToolRegistry`` : ``register``, ``get``, ``names``, ``all``, ``invoke``,
  ``describe``, ``find``, ``status_of``, ``capabilities``, ``guard``,
  ``duplicate registration raises``, ``invalid/undeclared/missing args
  rejected``, ``unavailable backend denied``, ``confirm_required denied``,
  ``exceptions wrapped as failures``.
"""

import inspect

from core.confirmation import CONFIRMATION
from core.recovery import ExecutionGuard
from core.safety import RISK_HIGH, RISK_DESTRUCTIVE


class ToolError(Exception):
    pass


class Tool:

    def __init__(self, name, function, category="generic", backend="local",
                 risk=RISK_HIGH, confirm_required=None, available=True,
                 description="", parameters=None, validators=None):
        if not name or not isinstance(name, str):
            raise ToolError("tool name must be a non-empty string")
        if not callable(function):
            raise ToolError(f"tool {name}: function must be callable")

        self.name = name
        self.function = function
        self.category = category
        self.backend = backend
        self.risk = risk
        self.description = description or name
        self._parameters = parameters or []
        self.validators = validators or []

        if confirm_required is None:
            confirm_required = risk in (RISK_HIGH, RISK_DESTRUCTIVE)
        self.confirm_required = bool(confirm_required)
        self.available = bool(available)

        if self._conforms_to_signature():
            self._parameters = self._infer_parameters()
        else:
            self._parameters = self._coerce_parameters()

    # ------------------------------------------------------------------
    # Parameter schema
    # ------------------------------------------------------------------
    def _conforms_to_signature(self):
        try:
            sig = inspect.signature(self.function)
            expected = [p.name for p in sig.parameters.values()]
        except (TypeError, ValueError):
            return False
        declared = [p.get("name") for p in self._parameters]
        return bool(declared) and set(expected) >= set(declared)

    def _coerce_parameters(self):
        coerced = []
        for param in self._parameters:
            entry = dict(param)
            entry.setdefault("name", "")
            entry.setdefault("required", True)
            entry.setdefault("hint", "")
            if entry["name"] and entry["name"] not in [p.get("name") for p in coerced]:
                coerced.append(entry)
        return coerced

    def _infer_parameters(self):
        try:
            sig = inspect.signature(self.function)
        except (TypeError, ValueError):
            return []
        params = []
        for name, p in sig.parameters.items():
            if name in ("self", "cls", "kwargs", "args"):
                continue
            entry = {
                "name": name,
                "required": p.default is inspect.Parameter.empty,
                "hint": f"type={p.annotation.__name__ if p.annotation is not inspect.Parameter.empty else 'any'}",
            }
            params.append(entry)
        return params

    def schema(self):
        return {
            "name": self.name,
            "parameters": self._parameters,
            "risk": self.risk,
            "confirm_required": self.confirm_required,
            "backend": self.backend,
            "description": self.description,
        }

    def status(self):
        if not self.available:
            return "unavailable"
        return "available"

    def run(self, **kwargs):
        return self.function(**kwargs)


class ToolRegistry:

    def __init__(self):
        self._tools = {}
        self._aliases = {}
        self.guard = ExecutionGuard()
        self._capabilities = set()

    # ------------------------------------------------------------------
    # Registration / discovery
    # ------------------------------------------------------------------
    def register(self, tool, allow_replace=False):
        if not isinstance(tool, Tool):
            raise ToolError("register() requires a Tool instance")
        if tool.name in self._tools and not allow_replace:
            raise ToolError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool
        for kw in self._keyword(tool):
            self._capabilities.add(kw)
        return tool

    def _keyword(self, tool):
        words = set()
        for piece in tool.name.replace("-", "_").split("_"):
            if piece:
                words.add(piece.lower())
        for word in str(tool.category).lower().split():
            if word:
                words.add(word)
        return words

    def get(self, name):
        return self._tools.get(name) or self._tools.get(self._aliases.get(name))

    def has(self, name):
        return self.get(name) is not None

    def names(self):
        return sorted(self._tools.keys())

    def all(self):
        return [self._tools[n] for n in sorted(self._tools.keys())]

    def categories(self):
        cats = {}
        for tool in self._tools.values():
            cats[tool.category] = cats.get(tool.category, 0) + 1
        return dict(sorted(cats.items()))

    def describe(self, name=None):
        if name is None:
            return [self.describe(n) for n in self.names()]
        tool = self.get(name)
        if tool is None:
            return {"name": name, "error": "unknown tool"}
        return tool.schema()

    def status_of(self, name):
        tool = self.get(name)
        if tool is None:
            return "unavailable"
        return tool.status()

    def find(self, keyword):
        needle = str(keyword).lower()
        return sorted(
            n for n in self._tools
            if needle in n.lower() or needle in str(self._tools[n].category).lower()
        )

    def capabilities(self, use_sets=True):
        if use_sets:
            return set(self._capabilities)
        return sorted(self._capabilities)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def invoke(self, tool_name, *args, **kwargs):
        tool = self.get(tool_name)

        if tool is None:
            return self._fail(tool_name, "unknown tool", "error")

        if not tool.available:
            return self._fail(tool_name, f"{tool_name} backend is unavailable", "unavailable")

        declared = {p.get("name") for p in tool._parameters}
        provided = set(kwargs.keys())

        for extra in provided - declared:
            if extra not in ("confirmed", "trusted", "request_id"):
                return self._fail(
                    tool_name, f"undeclared argument '{extra}' for {tool_name}", "invalid_argument"
                )

        for param in tool._parameters:
            pname = param.get("name")
            if param.get("required") and pname not in kwargs:
                return self._fail(tool_name, f"missing required argument '{pname}'", "invalid_argument")
            if pname in kwargs:
                try:
                    kwargs[pname] = self._coerce(kwargs[pname], param)
                except (TypeError, ValueError) as exc:
                    return self._fail(tool_name, f"invalid argument '{pname}': {exc}", "invalid_argument")

        for validator in tool.validators:
            try:
                valid, reason = validator(tool_name, kwargs) if callable(validator) else (True, "")
            except Exception as exc:
                return self._fail(tool_name, f"validation error: {exc}", "error")
            if not valid:
                return self._fail(tool_name, reason or f"{tool_name} rejected", "denied")

        trusted = bool(kwargs.pop("trusted", False))
        request_id = kwargs.pop("request_id", None)
        confirmed = bool(kwargs.pop("confirmed", False))

        if tool.confirm_required and not confirmed:
            return self._fail(tool_name, f"{tool_name} requires confirmation", "confirm_required")

        if tool.risk in (RISK_HIGH, RISK_DESTRUCTIVE):
            allowed, reason = CONFIRMATION.gate(
                tool,
                confirmed=confirmed,
                trusted=trusted,
                request_id=request_id,
            )
            if not allowed:
                return self._fail(tool_name, reason, "denied")

        key = self._run_key(tool_name, sorted(kwargs.items()))
        if not self.guard.acquire(key, timeout=0.5):
            return self._fail(tool_name, "tool is already executing", "denied")
        try:
            try:
                result = tool.function(**kwargs)
            except Exception as exc:
                return self._fail(tool_name, f"{tool_name} error: {exc}", "error")
            finally:
                self.guard.release(key)
            return self._wrap(tool_name, result)
        except Exception as exc:
            return self._fail(tool_name, f"{tool_name} error: {exc}", "error")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _run_key(self, name, items):
        from json import dumps
        return (name, dumps(items, default=str, sort_keys=True))

    def _coerce(self, value, param):
        hint = param.get("hint", "")
        if "int" in hint and isinstance(value, str):
            return int(value.strip())
        if "float" in hint and isinstance(value, str):
            return float(value.strip())
        if "bool" in hint and isinstance(value, str):
            return str(value).lower() in ("1", "true", "yes")
        return value

    def _wrap(self, name, result):
        if isinstance(result, dict):
            merged = dict(result)
            merged.setdefault("status", "ok")
            merged.setdefault("success", True)
            merged.setdefault("action", name)
            merged.setdefault("message", "ok")
            return merged
        return {
            "status": "ok",
            "success": bool(result) if result is not None else True,
            "action": name,
            "message": "ok",
            "result": result,
        }

    def _fail(self, name, message, status="error"):
        return {
            "status": status,
            "success": False,
            "action": name,
            "message": message,
        }


__all__ = ["Tool", "ToolRegistry", "ToolError"]