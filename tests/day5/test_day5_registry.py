"""Day 5 — registry integrity for features 112-122 tool sets."""

import pytest

from core.features import list_features

_NEW_TOOLS = [
    # 112 async
    "async_engine", "async_submit", "async_status", "async_result",
    "async_cancel", "async_wait", "async_recover",
    # 113 steering
    "steer_mission", "steering_queue", "steering_status",
    # 114 reasoning
    "reasoning_estimate", "reasoning_set", "reasoning_status",
    # 115 computer use
    "computer_use_status", "computer_use_observe", "computer_use_act",
    "computer_use_verify", "computer_use_workflow",
    # 116 cad
    "cad_detect", "cad_make", "cad_inspect", "cad_validate", "cad_export",
    "cad_reconstruct",
    # 117 pcb
    "pcb_status", "pcb_board", "pcb_drc", "pcb_export",
    "pcb_fabrication_check",
    # 118 webapp
    "webapp_status", "webapp_create", "webapp_build", "webapp_inspect",
    "webapp_qa",
    # 119 scientific
    "sci_detect", "sci_compute", "sci_validate", "sci_analyze", "sci_workflow",
    "sci_report", "sci_methods",
    # 120 artifact
    "art_status", "art_inspect", "art_generate", "art_validate", "art_ensure",
    # 121 mcp
    "mcp_status", "mcp_discover", "mcp_connect", "mcp_authorize", "mcp_call",
    "mcp_register",
    # 122 context
    "ctx_detect", "ctx_budget", "ctx_process", "ctx_document",
    "ctx_checkpoint", "ctx_restore",
]


def test_all_new_tools_registered(names):
    for tool in _NEW_TOOLS:
        assert tool in names, tool


def test_new_tool_shapes_valid(registry):
    for tool in _NEW_TOOLS:
        spec = registry.get(tool)
        assert spec is not None, tool
        assert spec.name == tool
        assert spec.risk in ("low", "medium", "high")
        assert spec.backend == "local"
        assert callable(spec.function)
        schema = spec.schema()
        assert schema["name"] == tool
        for param in schema["parameters"]:
            assert {"name", "required", "hint"} <= set(param)


def test_risk_gates_are_sane(registry):
    high = {"webapp_create", "mcp_connect", "mcp_authorize", "mcp_call",
            "mcp_register", "async_submit", "computer_use_act",
            "computer_use_workflow"}
    medium = {"art_generate", "steer_mission", "pcb_board", "pcb_drc",
              "pcb_export", "pcb_fabrication_check", "mcp_discover",
              "async_cancel", "async_recover", "art_ensure"}
    for tool in high:
        assert registry.get(tool).risk == "high", tool
    for tool in medium:
        assert registry.get(tool).risk == "medium", tool


def test_no_duplicate_registry_names(names):
    assert len(names) == len(set(names))


def test_catalog_rows_112_122_tools_reconcile(registry):
    names = set(registry.names())
    ids = {r["id"] for r in list_features()}
    assert ids == set(range(1, 124))
    for fid in range(112, 124):
        row = next(r for r in list_features() if r["id"] == fid)
        for tool in row["tools"]:
            assert tool in names, f"feature {fid} tool {tool} missing"


def test_total_cardinality(registry, names):
    assert len(names) == 436