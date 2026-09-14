"""Feature 121 tools — Native MCP Integration Layer surface.

Every exposed MCP tool is registered as a HIGH-risk ARVEN tool and every
call re-checks the allowlist + shared confirmation gate. DENIED calls reach
the ARVEN security layer and never reach the MCP server.
"""

from functools import lru_cache
import json

from tools.day2_tools import _safe, _parse_json, _parse_list

_mcp_tools = []


def _add(name, risk, category, description, parameters, target):
    spec = {"name": name, "risk": risk, "category": category,
            "backend": "local", "available": True,
            "description": description,
            "function": _safe(target),
            "parameters": [{"name": p[0], "required": p[1], "hint": p[2]}
                           for p in parameters]}
    _mcp_tools.append(spec)


@lru_cache(maxsize=1)
def _mcp():
    import core.mcp_layer as layer
    return layer


def _solve_kw(**kw):
    return kw


def _mcp_status(**kw):
    return _mcp()._HUB.status()


def _mcp_discover(**kw):
    return _mcp().discover_servers(_parse_list(kw.get("paths")) or ["."])


def _mcp_connect(**kw):
    name = str(kw.get("name") or "").strip()
    command = kw.get("command") or ""
    args = _parse_list(kw.get("args")) if kw.get("args") else []
    if not name or not command:
        return {"success": False, "status": "invalid_argument",
                "message": "name and command are required (JSON-RPC over stdio)"}
    timeout = int(_safe(kw.get("timeout"))(kw) or 15)
    return _mcp()._HUB.connect(name, command, args, timeout=timeout)


def _mcp_authorize(**kw):
    name = str(kw.get("name") or "").strip()
    raw = kw.get("tools")
    if raw is None:
        tools = None
    elif isinstance(raw, str):
        tools = [t.strip() for t in raw.split(",") if t.strip()]
    else:
        tools = _parse_list(raw)
    return _mcp()._HUB.authorize(name, tools)


def _mcp_call(**kw):
    name = str(kw.get("name") or "").strip()
    tool = str(kw.get("tool") or "").strip()
    args = _parse_json(kw.get("args")) if kw.get("args") else {}
    if not isinstance(args, dict):
        return {"success": False, "status": "invalid_argument",
                "message": "args must be a JSON object",
                "security": True, "feature_id": 121, "operation": "mcp/call"}
    return _mcp()._HUB.call(name, tool, args)


def _mcp_register(**kw):
    name = str(kw.get("name") or "").strip()
    tool = str(kw.get("tool") or "").strip()
    template = _parse_json(kw.get("argument_template")) if kw.get(
        "argument_template") else {}
    return _mcp()._HUB.register(name, tool, template or None)


# --- Feature 121 ----------------------------------------------------------
_add("mcp_status", "low", "mcp",
     "MCP hub report: connections, exposed tools, allowlist, registered "
     "facades",
     [], _mcp_status)
_add("mcp_discover", "medium", "mcp",
     "Discover mcp.json / *.mcp.json server configs without spawning them",
     [("paths", False, "JSON list of search paths; default ['.']")],
     _mcp_discover)
_add("mcp_connect", "high", "mcp",
     "Spawn an MCP server over stdio + real JSON-RPC initialize handshake "
     "and inspect its tools",
     [("name", True, "server name"),
      ("command", True, "executable for the MCP server"),
      ("args", False, "JSON list of server argv"),
      ("timeout", False, "handshake timeout in seconds")],
     _mcp_connect)
_add("mcp_authorize", "high", "mcp",
     "Explicitly authorize an allowlist of the server's tools (nothing "
     "callable sight-unseen)",
     [("name", True, "server name"),
      ("tools", False, "JSON list of tool names; default = all exposed")],
     _mcp_authorize)
_add("mcp_call", "high", "mcp",
     "Guarded tools/call: DENIED unless connected AND allowlisted; goes "
     "through ARVEN security/confirmation",
     [("name", True, "server name"),
      ("tool", True, "MCP tool name"),
      ("args", False, "JSON arguments object")],
     _mcp_call)
_add("mcp_register", "high", "mcp",
     "Expose an authorized MCP tool as a HIGH-risk ARVEN tool facade",
     [("name", True, "server name"),
      ("tool", True, "MCP tool name"),
      ("argument_template", False, "JSON param->argument mapping")],
     _mcp_register)


TOOLS = _mcp_tools

__all__ = ["TOOLS"]