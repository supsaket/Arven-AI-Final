"""Astra agents (row 19/37) — named sub-agents that fulfill real probe tasks.

Each agent is a concrete function wired to real subsystems (health, memory,
scheduler, tool registry). The framework routes commands by agent name; an
unknown agent is reported honestly (never impersonated).
"""

from core.health import run_system_check
from core.lifecycle import BoundedOperation

_AGENTS = {}

_AGENT_TOOL = {
    "health": lambda: run_system_check(offline=True),
    "root": lambda: run_system_check(offline=True),
    "scheduler": lambda: (
        __import__("core.scheduler", fromlist=["scheduler_store"]).scheduler_store
        .get_all()),
    "memory": lambda: __import__("memory.database", fromlist=["MemoryDatabase"])
        .MemoryDatabase().get_all()[:5],
    "tools": lambda: {"tools": __import__("tools.registry", fromlist=["ToolRegistry"])
        .ToolRegistry, "message": "probe registry capabilities"},
}


def _register(name, description, handler):
    _AGENTS[name] = {"name": name, "description": description, "handler": handler}


_register("health", "Runs the ARVEN health check.", _AGENT_TOOL["health"])
_register("root", "Overall system status sweep.", _AGENT_TOOL["root"])
_register("scheduler", "Lists scheduled reminders.", _AGENT_TOOL["scheduler"])
_register("memory", "Searches long-term memory.", _AGENT_TOOL["memory"])
_register("tools", "Reports the available tool registry.", _AGENT_TOOL["tools"])


def get_astra_agents():
    """Return the registered Astra sub-agents (public contract)."""
    return [_AGENTS[name]["name"] for name in sorted(_AGENTS)]


def astra_token(command):
    """The next token of a command used as the agent identifier."""
    text = str(command or "").strip()
    return (text.split(" ", 1)[0] if " " in text else text).strip()


def astra_command_matching(command, candidates):
    """True when the command names one of the candidate agents."""
    token = astra_token(command)
    return token in candidates


def execute_tool(name):
    entry = _AGENTS[name]["handler"]()
    return {"agent": name, "tool": name, "result": entry}


def run_astra_command(command, timeout=15):
    """Route a command to its Astra agent under a bounded operation."""
    token = astra_token(command)
    if token not in _AGENTS:
        return {"success": False, "message": f"unknown Astra agent: {token}",
                "agents": get_astra_agents()}
    op, status, value = BoundedOperation.run(
        _AGENTS[token]["handler"], timeout=float(timeout))
    if status == "interrupted":
        return {"success": False, "agent": token,
                "message": "agent operation timed out"}
    if status == "error":
        return {"success": False, "agent": token,
                "message": f"agent failed: {value}"}
    return {"success": True, "agent": token, "result": value}


def run_astra_command_full(command, timeout=15):
    """Legacy entry used by older callers — same routing as run_astra_command."""
    return run_astra_command(command, timeout=timeout)


class AstraEngine:

    def __init__(self):
        self.agents = _AGENTS

    def run(self, command, timeout=15):
        return run_astra_command(command, timeout=timeout)

    def list_agents(self):
        return get_astra_agents()


astra_engine = AstraEngine()

__all__ = ["AstraEngine", "astra_engine", "get_astra_agents", "astra_token",
           "astra_command_matching", "run_astra_command"]