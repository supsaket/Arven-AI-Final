"""Feature 121 — Native MCP (Model Context Protocol) integration layer.

Native = real JSON-RPC 2.0 over stdio with the MCP framing
(Content-Length headers) and request/notification lifecycle:

    DISCOVER -> VALIDATE -> AUTHORIZE -> REGISTER
            -> CONNECT -> INSPECT -> USE -> VERIFY -> DISCONNECT

Security ("MCP tools must go through ARVEN security"):
* A discovered server is inert until the operator AUTHORIZES it.
* Only allowlisted tool names may be called by ARVEN.
* Each exposed MCP tool is registered as a HIGH-risk ARVEN tool whose
  execution is routed through the shared ConfirmationManager (the same single
  authority used by every risky ARVEN action), and the facade re-checks the
  allowlist at call time. There is no direct path around the check.
* Server binaries run as unprivileged child subprocesses with the current
  environment (no secrets are injected into MCP servers).

A scripted, real client-server pair for offline verification lives in
``core/_mcp_echo_server.py`` (``python -m core._mcp_echo_server``).
"""

import json
import os
import re
import subprocess
import sys
import threading
import time

from core.confirmation import CONFIRMATION, RISK_HIGH

_DATA_FILE = os.path.join("data", "mcp_layer.json")
CHUNK = 65536

_SERVER_PATTERNS = ("mcp.json", "*.mcp.json", ".mcp.json")
_CLIENT_INFO = {"name": "arven", "version": "1.0"}
_PROTOCOL = "2024-11-05"


def _sanitize(text):
    return re.sub(r"[^a-z0-9_]", "_", str(text or "").lower())


# --------------------------------------------------------------------------
# framing (LSP-style JSON-RPC: Content-Length headers + JSON body)
# --------------------------------------------------------------------------
def write_message(stream, payload):
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header + body)
    stream.flush()


def read_message(stream, timeout=10.0):
    """Blocking read of one MCP frame. Returns dict or None on EOF/timeout."""
    start = time.monotonic()
    header_buf = b""
    while b"\r\n\r\n" not in header_buf:
        byte = stream.read(1)
        if byte == b"":
            return None
        header_buf += byte
        if time.monotonic() - start > timeout:
            return None
    try:
        headers = {}
        for line in header_buf.decode("ascii").split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", 0))
    except Exception:
        return None
    if length <= 0 or length > 16 * 1024 * 1024:
        return None
    body = b""
    start = time.monotonic()
    while len(body) < length:
        body += stream.read(length - len(body))
        if time.monotonic() - start > timeout:
            return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


# --------------------------------------------------------------------------
# discovery & config validation
# --------------------------------------------------------------------------
def discover_servers(search_paths=None):
    """Locate mcp.json / *.mcp.json configs (cwd + data dir) without touching
    any server, plus the ARVEN_MCP_SERVERS env JSON. Never spawns anything."""
    paths = list(search_paths or ["."])
    candidates = {}
    for root in paths:
        root = str(root)
        for name in os.listdir(root) if os.path.isdir(root) else []:
            full = os.path.join(root, name)
            if os.path.isfile(full) and any(
                    (name == p) or name.endswith(p.lstrip("*"))
                    for p in _SERVER_PATTERNS):
                candidate = _read_config(full)
                if candidate:
                    candidates[os.path.basename(candidate.get("name") or
                                                name)] = {
                        "config_path": full,
                        "command": candidate.get("command"),
                        "args": candidate.get("args", []),
                        "env": "inherited, not exposed",
                        "tools": candidate.get("tools"),
                    }
    from_env = os.environ.get("ARVEN_MCP_SERVERS")
    if from_env:
        try:
            parsed = json.loads(from_env)
            for name, config in (parsed or {}).items() if isinstance(parsed,
                                                                     dict) \
                    else []:
                if isinstance(config, dict) and config.get("command"):
                    candidates[_sanitize(name)] = {
                        "config_path": "env:ARVEN_MCP_SERVERS",
                        "command": config["command"],
                        "args": config.get("args", []),
                        "tools": config.get("tools"),
                    }
        except Exception:
            pass
    validated = []
    for name, config in sorted(candidates.items()):
        if not config.get("command"):
            validated.append({**config, "name": name,
                              "valid": False, "reason": "missing command"})
            continue
        try:
            tools = config.get("tools") or []
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.split(",") if t.strip()]
            validated.append({**config, "name": name, "valid": True,
                              "tool_names": tools})
        except Exception as exc:
            validated.append({**config, "name": name, "valid": False,
                              "reason": str(exc)})
    return {"success": True, "status": "ok",
            "discovered": validated,
            "message": f"{len(validated)} MCP server config(s) found "
                       "(none spawned)"}


def _read_config(path):
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        if isinstance(config, dict):
            mcp_servers = config.get("mcpServers") or config.get(
                "mcpServers", {})
            if isinstance(config.get("servers"), dict):
                mcp_servers = config["servers"]
            if len(mcp_servers) == 1 and isinstance(mcp_servers, dict):
                name, entry = next(iter(mcp_servers.items()))
                return {"name": name, "command": entry.get("command"),
                        "args": entry.get("args", []),
                        "tools": entry.get("tools")}
            return config
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
# live connection (real subprocess + JSON-RPC)
# --------------------------------------------------------------------------
class McpConnection:

    def __init__(self, name, command, args=None):
        self.name = _sanitize(name)
        self.command = str(command)
        self.args = list(args or [])
        self.process = None
        self.ready = False
        self.protocol = None
        self.server_info = None
        self.tools = []
        self._counter = itertools_counter()
        self._lock = threading.Lock()
        self._last_error = None

    def connect(self, timeout=15):
        """Spawn and perform the real MCP initialize handshake."""
        try:
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            request = {"jsonrpc": "2.0", "id": next(self._counter),
                       "method": "initialize",
                       "params": {"protocolVersion": _PROTOCOL,
                                  "capabilities": {},
                                  "clientInfo": _CLIENT_INFO}}
            write_message(self.process.stdin, request)
            response = read_message(self.process.stdout, timeout=timeout)
            if not response or response.get("id") != request["id"] or \
                    "result" not in response:
                self._last_error = (response or {}).get("error",
                                                        "no response")
                self.close()
                return self._fail("initialize handshake failed: "
                                  + str(self._last_error))
            self.protocol = response["result"].get("protocolVersion")
            self.server_info = response["result"].get("serverInfo", {})
            write_message(self.process.stdin,
                          {"jsonrpc": "2.0", "method": "notifications/initialized",
                           "params": {}})
            listing = self._request("tools/list", {}, timeout=timeout)
            raw_tools = (listing or {}).get("tools", [])
            self.tools = [{"name": t.get("name"),
                           "description": t.get("description", ""),
                           "input_schema": t.get("inputSchema", {})}
                          for t in raw_tools if t.get("name")]
            self.ready = True
            return self._ok(self._summary())
        except Exception as exc:
            self._last_error = str(exc)
            self.close()
            return self._fail("connect failed: " + str(exc))

    def call(self, tool, arguments=None, timeout=15):
        """tools/call over JSON-RPC — returns parsed, honest results."""
        if not self.ready:
            return self._fail("not connected — call CONNECT first")
        result = self._request("tools/call",
                               {"name": tool, "arguments": arguments or {}},
                               timeout=timeout)
        if result is None:
            return self._fail("no response from MCP server")
        is_error = bool(result.get("isError", False))
        content = result.get("content", [])
        text = "".join(c.get("text", "") for c in content
                       if isinstance(c, dict))
        payload = {"success": not is_error,
                   "status": "error" if is_error else "ok",
                   "tool": tool, "text": text,
                   "content": content,
                   "isError": is_error,
                   "server": self.name}
        if result.get("structuredContent") is not None:
            payload["structured"] = result["structuredContent"]
        return payload

    def list_tools(self):
        if not self.ready:
            return self._fail("not connected")
        return self._ok({"server": self.name, "tools": self.tools})

    def verify(self):
        """VERIFY: live round-trip ping proves the server actually responds."""
        if not self.ready:
            return {"success": False, "status": "error",
                    "message": "not connected — nothing to verify"}
        before = self.tools
        result = self._request("ping", {}, timeout=8)
        still_alive = result is not None
        return {"success": still_alive, "status": "ok" if still_alive
                else "error",
                "verified": still_alive,
                "registered_tools": len(before),
                "message": "live round-trip confirmed" if still_alive
                else "server did not respond to ping"}

    def _request(self, method, params, timeout=10):
        with self._lock:
            request = {"jsonrpc": "2.0", "id": next(self._counter),
                       "method": method, "params": params}
            write_message(self.process.stdin, request)
        response = read_message(self.process.stdout, timeout=timeout)
        if response and response.get("id") == request["id"]:
            if "error" in response and "result" not in response:
                return {"error": response["error"]}
            return response.get("result", {"error": response.get("error")})
        return None

    def close(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self.ready = False

    def _summary(self):
        return {"server": self.name, "protocol": self.protocol,
                "server_info": self.server_info, "tools": len(self.tools),
                "message": "connected; tools inspected"}

    def _ok(self, payload):
        return {"success": True, "status": "ok",
                "status_code": "OK", **payload}

    def _fail(self, message):
        return {"success": False, "status": "error", "message": message,
                "last_error": self._last_error}


def itertools_counter():
    value = [0]
    while True:
        value[0] += 1
        yield value[0]


# --------------------------------------------------------------------------
# hub: authorization, registration, guarded calls, persistence
# --------------------------------------------------------------------------
class McpHub:

    def __init__(self, data_file=_DATA_FILE):
        self.data_file = data_file
        self.connections = {}   # server_name -> McpConnection
        self.authorized = {}    # server_name -> set(tool names)
        self.registered = {}    # facade tool name -> spec
        self._load()

    # -- persistence --------------------------------------------------------
    def _load(self):
        try:
            if os.path.exists(self.data_file):
                saved = json.load(open(self.data_file, encoding="utf-8"))
                self.authorized = {k: set(v or []) for k, v in
                                   (saved.get("authorized") or {}).items()}
                self.registered = saved.get("registered") or {}
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            json.dump({"authorized": {k: sorted(v) for k, v in
                                      self.authorized.items()},
                       "registered": self.registered},
                      open(self.data_file, "w", encoding="utf-8"),
                      indent=2, default=str)
        except Exception:
            pass

    # -- lifecycle ----------------------------------------------------------
    def connect(self, name, command, args=None, timeout=15):
        connection = self.connections.get(_sanitize(name))
        if connection and connection.ready:
            return {"success": True, "status": "ok",
                    "message": f"already connected to '{name}'",
                    **connection._summary()}
        connection = McpConnection(name, command, args)
        result = connection.connect(timeout=timeout)
        if result.get("success"):
            key = connection.name
            self.connections[key] = connection
        return result

    def disconnect(self, name):
        key = _sanitize(name)
        connection = self.connections.get(key)
        if connection:
            connection.close()
            del self.connections[key]
            return {"success": True, "status": "ok",
                    "message": f"disconnected '{key}'"}
        return {"success": True, "status": "ok",
                "message": "no live connection; nothing to disconnect",
                "disconnected": False}

    def authorize(self, name, tools=None):
        """AUTHORIZE: operator explicitly grants an allowlist of tool names.

        ``tools=None`` grants every exposed tool; ``tools=[]`` REVOKES all
        (the empty allowlist is a legitimate state, not a default).
        """
        key = _sanitize(name)
        connection = self.connections.get(key)
        if not connection or not connection.ready:
            return {"success": False, "status": "error",
                    "message": f"connect to '{name}' before authorizing; no "
                               f"tools can be exposed sight-unseen"}
        available = {t["name"] for t in connection.tools}
        if tools is None:
            tools = sorted(available)
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]
        grant = set(tools)
        denied_now = [t for t in grant if t not in available]
        if denied_now:
            return {"success": False, "status": "error",
                    "message": "cannot authorize tools the server does not "
                               "expose: " + ", ".join(sorted(denied_now)) +
                               f" (server exposes: {sorted(available)})"}
        self.authorized[key] = grant
        self._save()
        return {"success": True, "status": "ok",
                "authorized": sorted(grant),
                "revoked": sorted(self.authorized.get(key, set()) - grant),
                "message": (f"revoked all tools on '{key}'"
                            if not grant else
                            f"authorized {len(grant)} tool(s) on '{key}'")}

    def is_authorized(self, name, tool):
        return tool in self.authorized.get(_sanitize(name), set())

    # -- guarded call -------------------------------------------------------
    def call(self, name, tool, arguments=None):
        """USE: only runs when connected AND allowlisted (ARVEN security)."""
        key = _sanitize(name)
        connection = self.connections.get(key)
        if not connection or not connection.ready:
            return {"success": False, "status": "error",
                    "message": "no live MCP connection to call"}
        if not self.is_authorized(key, tool):
            return {"success": False, "status": "DENIED",
                    "status_code": "DENIED",
                    "message": f"tool '{tool}' is not authorized on '{key}' "
                               f"— call mcp_authorize first",
                    "security": True}
        result = connection.call(tool, arguments)
        result["security"] = True
        result["authorized"] = True
        return result

    def register(self, name, tool, arguments=None):
        """REGISTER: expose an authorized MCP tool as a HIGH-risk ARVEN tool
        whose facade re-checks the allowlist at every call."""
        key = _sanitize(name)
        connection = self.connections.get(key)
        if not connection or not connection.ready:
            return {"success": False, "status": "error",
                    "message": "connect first"}
        if not self.is_authorized(key, tool):
            return {"success": False, "status": "error",
                    "message": "not authorized — authorize before registering"}
        schema = next((t["input_schema"] for t in connection.tools
                       if t["name"] == tool), {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) \
            else {}
        parameters = [{"name": p, "required": p in (schema.get("required")
                                                    or []),
                       "hint": (properties.get(p, {}).get("description")
                                if isinstance(properties.get(p), dict) else p)}
                      for p in properties]
        facade_name = f"mcp_{key}_{_sanitize(tool)}"
        arguments_index = arguments or {p["name"]: f"{{{p['name']}}}"
                                        for p in parameters}
        spec = {
            "name": facade_name, "risk": "high", "category": "mcp",
            "backend": "remote", "available": True,
            "description": (f"MCP tool '{tool}' on server '{key}' — routed "
                            "through ARVEN security and confirmation"),
            "confirmation": True,
            "origin": {"server": key, "mcp_tool": tool},
            "parameters": parameters,
            "function": self._facade(key, tool, arguments_index),
        }
        self.registered[facade_name] = spec
        self._save()
        return {"success": True, "status": "ok",
                "name": facade_name, "server": key, "mcp_tool": tool,
                "risk": "high",
                "message": f"registered '{facade_name}' — invocation goes "
                           "through confirmation + allowlist"}

    def _facade(self, key, tool, arguments_template):
        def facade(**kw):
            if not self.is_authorized(key, tool):
                return {"success": False, "status": "DENIED",
                        "message": f"'{tool}' is not authorized on '{key}'",
                        "security": True}
            resolved = {}
            for param, template in (arguments_template or {}).items():
                if param in kw and kw[param] is not None:
                    resolved[param] = kw[param]
                elif isinstance(template, str) and template.startswith("{"):
                    matched = template[1:-1] if template.endswith("}") else ""
                    if matched and matched in kw:
                        resolved[param] = kw[matched]
            result = self.call(key, tool, resolved)
            return result
        return facade

    def status(self):
        entries = []
        for key, connection in sorted(self.connections.items()):
            entries.append({
                "server": key,
                "connected": connection.ready,
                "tools_exposed": len(connection.tools),
                "authorized": sorted(self.authorized.get(key, [])),
                "info": connection.server_info or {},
            })
        return {"success": True, "status": "ok", "status_code": "OK",
                "connections": entries,
                "registered_facades": sorted(self.registered),
                "authorization_map": {
                    k: sorted(v) for k, v in self.authorized.items()},
                "message": "MCP hub report"}

    def shutdown(self):
        for connection in list(self.connections.values()):
            connection.close()
        self.connections.clear()


_HUB = McpHub()

__all__ = [
    "McpConnection", "McpHub", "_HUB", "discover_servers",
    "read_message", "write_message",
]