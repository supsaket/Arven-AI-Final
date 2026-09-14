"""Registry builder — assemble every tool module into one registry.

Contract (verify_registry.py / nodeids):

* ``from tools.builder import build_registry`` (single source of truth)
* ``from tools.builder import get_registry`` (module cache)
* returns a ``tools.registry.ToolRegistry`` with ``names()``, ``all()``,
  ``get(name)``, ``invoke(name, **kwargs)`` and shared ``guard``.
"""

from tools.registry import Tool, ToolError


def _modules():
    from tools import apps, browser, documents, files, media, memory_tools
    from tools import proactive_tools, communication_tools
    from tools import android_tools, system, tts_tools, vision_tools, web
    from tools import day2_tools
    from tools import capability_tools, engineering_tools, orchestrator_tools
    from tools import (async_tools, steering_tools, reasoning_tools,
                       computer_use_tools, cad_tools, pcb_tools,
                       webapp_tools, scientific_tools, artifact_tools,
                       mcp_tools, context_tools, mechatronics_tools)
    return [
        system, files, apps, media, web, browser, documents,
        tts_tools, memory_tools, proactive_tools, communication_tools,
        android_tools, vision_tools, day2_tools,
        capability_tools, engineering_tools, orchestrator_tools,
        async_tools, steering_tools, reasoning_tools, computer_use_tools,
        cad_tools, pcb_tools, webapp_tools, scientific_tools,
        artifact_tools, mcp_tools, context_tools, mechatronics_tools,
    ]


def _resolve_risk(risk):
    from core.safety import (
        RISK_SAFE, RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_DESTRUCTIVE,
    )
    map = {
        "safe": RISK_SAFE, "low": RISK_LOW, "medium": RISK_MEDIUM,
        "high": RISK_HIGH, "destructive": RISK_DESTRUCTIVE,
    }
    return map.get(str(risk).lower())


def _available(name, entry):
    import importlib
    module = entry["module"]
    func = getattr(importlib.import_module(module), entry["name"])
    return func


def build_registry(register_async=True):
    from tools.registry import ToolRegistry
    registry = ToolRegistry()

    errors = []
    available_count = 0
    for module in _modules():
        for spec in getattr(module, "TOOLS", []):
            name = spec["name"]
            function = spec["function"]
            risk = _resolve_risk(spec.get("risk", "high"))
            parameters = spec.get("parameters", [])
            if parameters:
                for p in parameters:
                    p.setdefault("required", True)
                    p.setdefault("hint", "")
            try:
                tool = Tool(
                    name=name,
                    function=function,
                    category=spec.get("category", "generic"),
                    backend=spec.get("backend", "local"),
                    risk=risk,
                    available=spec.get("available", True),
                    description=spec.get("description", name),
                    parameters=parameters,
                )
                registry.register(tool)
                if tool.available:
                    available_count += 1
            except ToolError as exc:
                errors.append(str(exc))

    # Build-time integrity: any registration error must surface loudly.
    if errors:
        raise ToolError(f"registry build failed: {'; '.join(errors)}")

    return registry


_registry_cache = None


def get_registry():
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = build_registry()
    return _registry_cache


__all__ = ["build_registry", "get_registry"]