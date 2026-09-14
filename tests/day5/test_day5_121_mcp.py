"""Feature 121 — MCP layer: real protocol, guarded calls, denial proof.

The echo server logs every tools/call to ARVEN_ECHO_LOG and has a marker tool
that physically writes a file. Denial tests prove a DENIED tool never reached
the server (call-log delta == 0) and never produced the marker.
"""

import json
import os
import sys

import pytest

from core import mcp_layer

_ECHO_CMD = [sys.executable, "-m", "core._mcp_echo_server"]


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    hub = mcp_layer.McpHub(data_file=str(tmp_path / "mcp_hub.json"))
    monkeypatch.setenv("ARVEN_ECHO_LOG", str(tmp_path / "echo_calls.jsonl"))
    yield hub
    hub.shutdown()


def _log_lines(tmp_path):
    path = tmp_path / "echo_calls.jsonl"
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in
            open(path, encoding="utf-8").read().splitlines() if line]


def _connect(hub):
    return hub.connect("echo", _ECHO_CMD[0], args=_ECHO_CMD[1:], timeout=15)


def test_initialize_handshake_and_tools(hub):
    out = _connect(hub)
    assert out["success"] is True
    assert out["protocol"] == "2024-11-05"
    assert out["tools"] == 4          # int count, per server contract
    assert out["server_info"]["name"] == "arven-echo"


def test_authorize_and_guarded_call(hub):
    _connect(hub)
    hub.authorize("echo", ["json_sum"])
    out = hub.call("echo", "json_sum", {"a": 3, "b": 4})
    assert out["success"] is True
    assert out["text"] == "7"
    assert hub.is_authorized("echo", "json_sum") is True


def test_denied_call_never_reaches_server(hub, tmp_path):
    _connect(hub)
    hub.authorize("echo", ["json_sum"])
    before = len(_log_lines(tmp_path))
    denied = hub.call("echo", "echo", {"text": "secret"})
    assert denied["status"] == "DENIED"
    after = len(_log_lines(tmp_path))
    assert after == before              # no tools/call ever arrived


def test_denied_marker_never_written(hub, tmp_path):
    _connect(hub)
    marker = tmp_path / "marker.txt"
    hub.authorize("echo", ["json_sum"])
    denied = hub.call("echo", "marker", {"path": str(marker)})
    assert denied["status"] == "DENIED"
    assert marker.exists() is False


def test_authorized_marker_writes_file(hub, tmp_path):
    _connect(hub)
    marker = tmp_path / "marker.txt"
    hub.authorize("echo", ["marker"])
    out = hub.call("echo", "marker", {"path": str(marker)})
    assert out["success"] is True
    assert marker.read_text(encoding="utf-8") == "EXECUTED_BY_MCP_SERVER\n"


def test_revoke_all_revokes_everything(hub, tmp_path):
    _connect(hub)
    hub.authorize("echo", ["json_sum", "echo"])
    hub.authorize("echo", [])           # [] == revoke all
    before = len(_log_lines(tmp_path))
    out = hub.call("echo", "json_sum", {"a": 1, "b": 1})
    assert out["status"] == "DENIED"
    assert len(_log_lines(tmp_path)) == before


def test_register_high_risk_facade(hub):
    _connect(hub)
    hub.authorize("echo", ["json_sum"])
    facade = hub.register("echo", "json_sum")
    assert facade["success"] is True
    assert facade["name"].startswith("mcp_echo_")
    assert facade["risk"] == "high"
    state = hub.status()
    assert facade["name"] in state["registered_facades"]


def test_bad_server_connect_fails_honestly(hub):
    out = hub.connect("broken", "cmd_that_does_not_exist_xyz",
                      args=["--bad"], timeout=5)
    assert out["success"] is False
    assert out.get("last_error")


def test_unknown_tool_fails_honestly(hub):
    out = hub.call("nope", "nope", {})
    assert out["status"] in ("DENIED", "error", "invalid_argument")


def test_discovery_reads_json_configs(tmp_path):
    server_dir = tmp_path / "servers"
    server_dir.mkdir()
    (server_dir / "mcp.json").write_text(json.dumps({
        "mcpServers": {"demo": {"command": "python",
                                "args": ["-m", "core._mcp_echo_server"]}}}),
        encoding="utf-8")
    out = mcp_layer.discover_servers([str(server_dir)])
    assert out["discovered"]  # list of candidate specs, none spawned
    entry = out["discovered"][0]
    assert entry["valid"] is True
    assert entry["name"] == "demo"
    assert entry["command"] == "python"