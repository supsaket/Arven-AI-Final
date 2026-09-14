"""Day 4 — Feature 109: Resource & Capability Awareness + feature_status.

Real probes only: hardware/software/providers/permissions/capabilities come
from the live machine; nothing is invented. ``feature_status`` reconciles a
feature against the live registry (single source of truth).
"""

from core.capability_awareness import CapabilityAwareness

_KNOWN_STATUSES = {
    "available", "unavailable", "not_configured", "not_installed",
    "not_detected", "unverified", "failed", "offline", "requires_auth",
    "requires_permission", "limited",
}


def test_probe_snapshot_shape(tmp_path):
    caps = CapabilityAwareness(kv_path=str(tmp_path / "cap.json"))
    snapshot = caps.probe(force=True)
    for key in ("hardware", "software", "providers", "permissions",
                "capabilities"):
        assert key in snapshot
    assert snapshot["capabilities"]
    unknown = set(str(v).lower() for v in snapshot["capabilities"].values()) \
        - _KNOWN_STATUSES
    assert unknown == set(), f"unknown capability statuses: {unknown}"


def test_probe_cache_then_refresh(tmp_path):
    engine = CapabilityAwareness(kv_path=str(tmp_path / "cache.json"))
    assert engine.probe()["cached"] is False
    assert engine.probe()["cached"] is True
    assert engine.refresh()["cached"] is False


def test_restore_from_persisted_snapshot(tmp_path):
    path = str(tmp_path / "restore.json")
    CapabilityAwareness(kv_path=path).probe(force=True)
    restored = CapabilityAwareness(kv_path=path).restore()
    assert restored["restored"] is True
    assert restored["snapshot"]["capabilities"]


def test_graph_answers_all_nine_questions(tmp_path):
    graph = CapabilityAwareness(kv_path=str(tmp_path / "graph.json")).graph()
    for question in ("what_exists", "what_is_available",
                     "what_needs_configuration", "what_is_unavailable",
                     "what_resources", "what_software", "what_dependencies",
                     "what_permissions", "what_to_fix"):
        assert question in graph, question
    assert graph["what_exists"]["catalog_total"] == 123
    assert graph["what_exists"]["registry_tools"] == 436
    assert graph["what_resources"]["resources"]["cores"] >= 1


def test_graph_single_question(tmp_path):
    engine = CapabilityAwareness(kv_path=str(tmp_path / "graph1.json"))
    out = engine.graph("what_is_available")
    assert out["question"] == "what_is_available"
    assert "capabilities" in out["answer"]


def test_dependencies_catalog_and_feature(tmp_path):
    engine = CapabilityAwareness(kv_path=str(tmp_path / "deps.json"))
    whole = engine.dependencies()
    from core.features import list_features
    unique_refs = len({t for r in list_features() for t in r["tools"]})
    assert whole["feature_count"] == 123
    assert whole["tool_refs"] == unique_refs
    row = engine.dependencies(110)
    assert row["feature_id"] == 110
    assert "eng_calculate" in row["tools"]


def test_registry_capability_software(registry):
    out = registry.invoke("capability_software")
    assert out["status"] == "ok"
    assert out["success"] is True
    assert isinstance(out["data"]["software"], dict)
    assert out["data"]["available"] == sorted(out["data"]["available"])


def test_registry_capability_graph(registry):
    out = registry.invoke("capability_graph", question="what_exists")
    assert out["success"] is True
    assert out["data"]["answer"]["catalog_total"] == 123


def test_registry_feature_status_full(registry):
    out = registry.invoke("feature_status", feature_id=110)
    assert out["success"] is True
    assert out["status"] == "ok"
    assert out["name"] == \
        "Autonomous Engineering, Prototyping & Spatial Visualization"
    assert out["tools_registered"] == 7
    assert out["tools_missing"] == []


def test_registry_feature_status_unknown_id(registry):
    out = registry.invoke("feature_status", feature_id=0)
    assert out["status"] == "invalid_argument"
    assert out["success"] is False
    missing = registry.invoke("feature_status")
    assert missing["status"] == "invalid_argument"