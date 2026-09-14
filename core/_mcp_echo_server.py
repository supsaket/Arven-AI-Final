"""Feature 121 — scripted MCP stdio JSON-RPC server (offline verification).

Run:   python -m core._mcp_echo_server

A genuine Model-Context-Protocol stdio server: Content-Length framing,
``initialize`` handshake, ``notifications/initialized``, ``tools/list``,
``tools/call`` and ``ping``. Used by tests/day5 and the CLI self-test for
features 112-122 so MCP integration is verified offline, deterministically,
without external MCP servers.
"""

import json
import os
import sys

TOOLS = [
    {"name": "echo", "description": "returns the text argument unchanged",
     "inputSchema": {"type": "object", "properties": {"text": {
         "type": "string", "description": "text to echo"}},
         "required": ["text"]}},
    {"name": "json_sum", "description": "adds two integer arguments",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "integer"},
                                                     "b": {"type": "integer"}},
                     "required": ["a", "b"]}},
    {"name": "marker", "description": "writes a marker file (proves the "
     "server really ran the tool)",
     "inputSchema": {"type": "object", "properties": {"path": {"type":
         "string", "description": "file path to touch"}},
         "required": ["path"]}},
    {"name": "status", "description": "reports deterministic server state",
     "inputSchema": {"type": "object", "properties": {}}},
]

CALL_LOG = os.environ.get("ARVEN_ECHO_LOG")


def read_message():
    header = b""
    while b"\r\n\r\n" not in header:
        byte = sys.stdin.buffer.read(1)
        if byte == b"":
            return None
        header += byte
    headers = {}
    for line in header.decode("ascii").split("\r\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", 0))
    body = b""
    while len(body) < length:
        body += sys.stdin.buffer.read(length - len(body))
    return json.loads(body.decode("utf-8"))


def write_message(payload):
    body = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(
        f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


def log_call(name, arguments):
    if CALL_LOG:
        try:
            with open(CALL_LOG, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"tool": name,
                                         "arguments": arguments}) + "\n")
        except Exception:
            pass


def main():
    while True:
        message = read_message()
        if message is None:
            break
        request_id = message.get("id")
        if request_id is None:
            continue
        method = message.get("method")
        params = message.get("params") or {}
        if method == "initialize":
            write_message({
                "jsonrpc": "2.0", "id": request_id,
                "result": {"protocolVersion": "2024-11-05",
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "arven-echo",
                                          "version": "1.0"}}})
        elif method == "tools/list":
            write_message({"jsonrpc": "2.0", "id": request_id,
                           "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            log_call(name, arguments)
            if name == "echo":
                content = [{"type": "text",
                            "text": "echo:" + str(
                                arguments.get("text", ""))}]
                is_error = False
            elif name == "json_sum":
                total = int(arguments.get("a", 0)) + int(arguments.get("b", 0))
                content = [{"type": "text", "text": str(total)}]
                is_error = False
            elif name == "marker":
                path = str(arguments.get("path", ""))
                try:
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write("EXECUTED_BY_MCP_SERVER\n")
                    content = [{"type": "text", "text": "marked"}]
                    is_error = False
                except Exception as exc:
                    content = [{"type": "text", "text": f"marker failed: {exc}"}]
                    is_error = True
            elif name == "status":
                content = [{"type": "text", "text": "READY"}]
                is_error = False
            else:
                content = [{"type": "text",
                            "text": f"unknown tool: {name}"}]
                is_error = True
            write_message({"jsonrpc": "2.0", "id": request_id,
                           "result": {"content": content, "isError": is_error}})
        elif method == "ping":
            write_message({"jsonrpc": "2.0", "id": request_id,
                           "result": {}})
        else:
            write_message({"jsonrpc": "2.0", "id": request_id,
                           "error": {"code": -32601,
                                     "message": "method not found"}})


if __name__ == "__main__":
    main()