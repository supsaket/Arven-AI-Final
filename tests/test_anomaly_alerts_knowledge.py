"""Focused Day 2 tests: features 57, 58, 65, 66, 71, 70.

All kv/DB paths are temp; nothing touches user data or the GUI modules.
"""

import sqlite3
from datetime import datetime, timedelta

from core.alerts import AlertManager, SEVERITY_ORDER, SEVERITY_INDEX
from core.anomaly import AnomalyEngine
from core.assimilation import AssimilationEngine
from core.fact_check import FactChecker
from core.knowledge_graph import KnowledgeGraph
from core.kv import KeyValueStore
from core.memory_lifecycle import MemoryLifecycle
from memory.database import MemoryDatabase


class TestAnomalyEngine:

    def test_zscore_spike(self, tmp_path):
        engine = AnomalyEngine(str(tmp_path / "anomaly.json"), window_size=4)
        for value in [10, 9, 11, 10, 10, 30]:
            engine.ingest("cpu", value)
        result = engine.detect("cpu")
        assert result["state"] == "active"
        spikes = [a for a in result["anomalies"] if a["kind"] == "point"]
        assert spikes
        assert spikes[-1]["value"] == 30.0
        assert spikes[-1]["severity"] == "critical"

    def test_threshold(self, tmp_path):
        engine = AnomalyEngine(str(tmp_path / "anomaly.json"))
        engine.set_bounds("srv", min_value=0, max_value=15)
        for value in [5, 10, 30]:
            engine.ingest("srv", value)
        result = engine.detect("srv")
        threshold = [a for a in result["anomalies"] if a["kind"] == "threshold"]
        assert any(a["value"] == 30.0 for a in threshold)

    def test_trend(self, tmp_path):
        engine = AnomalyEngine(str(tmp_path / "anomaly.json"), window_size=4)
        engine.configure("ramp", trend_limit=0.5)
        for value in [1, 2, 3, 4, 5, 6, 7, 8]:
            engine.ingest("ramp", value)
        result = engine.detect("ramp")
        trend = [a for a in result["anomalies"] if a["kind"] == "trend"]
        assert trend

    def test_rule(self, tmp_path):
        engine = AnomalyEngine(str(tmp_path / "anomaly.json"))
        engine.add_rule("guarded", "too_big", lambda value, history, sid: value > 100)
        for value in [10, 20, 200]:
            engine.ingest("guarded", value)
        result = engine.detect("guarded")
        rule = [a for a in result["anomalies"] if a["kind"] == "rule"]
        assert any(a["name"] == "too_big" for a in rule)

    def test_stationary(self, tmp_path):
        engine = AnomalyEngine(str(tmp_path / "anomaly.json"), window_size=4)
        for _ in range(8):
            engine.ingest("flat", 5.0)
        report = engine.report("flat")
        assert report["state"] == "stationary"
        assert report["by_kind"] == {}

    def test_insufficient_data(self, tmp_path):
        engine = AnomalyEngine(str(tmp_path / "anomaly.json"), window_size=5)
        engine.ingest("tiny", 1.0)
        engine.ingest("tiny", 2.0)
        result = engine.detect("tiny")
        assert result["state"] == "insufficient_data"
        assert result["anomalies"] == []

    def test_persisted_restore(self, tmp_path):
        path = str(tmp_path / "anomaly.json")
        first = AnomalyEngine(path, window_size=3)
        for value in [10, 11, 10, 40]:
            first.ingest("disk", value)
        first.detect("disk")
        second = AnomalyEngine(path, window_size=3)
        result = second.detect("disk")
        assert result["state"] == "active"
        assert any(a["kind"] == "point" and a["value"] == 40.0 for a in result["anomalies"])


class TestAlertManager:

    def test_severity_ordering(self, tmp_path):
        assert SEVERITY_ORDER == ["info", "low", "medium", "high", "critical"]
        assert SEVERITY_INDEX["critical"] > SEVERITY_INDEX["medium"]
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        created = manager.create("critical", "boom", "disk full", "hdd")
        assert created["severity"] == "critical"
        import pytest
        with pytest.raises(ValueError):
            manager.create("catastrophic", "x", "y", "z")

    def test_dedup_returns_existing_id_and_count(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        first = manager.create("high", "disk", "80% full", "probe", dedup_key="disk-80")
        second = manager.create("high", "disk", "80% full", "probe", dedup_key="disk-80")
        assert second["id"] == first["id"]
        assert second["deduped"] is True
        assert second["count"] == 2

    def test_ack(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        created = manager.create("low", "warn", "meh", "src")
        assert manager.ack(created["id"]) is True
        assert manager.get(created["id"])["acknowledged"] is True

    def test_close_archives_without_delete(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        created = manager.create("medium", "x", "y", "src")
        assert len(manager.active()) == 1
        assert manager.close(created["id"]) is True
        assert manager.active() == []
        assert len(manager.list()) == 1
        assert manager.get(created["id"])["status"] == "closed"
        assert manager.severity_count()["total"] == 0

    def test_channel_honest_statuses(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        assert set(manager.channels()) == {"local", "email", "push", "sms"}
        assert manager.channel_status("local") == "AVAILABLE"
        assert manager.channel_status("email") == "NOT_CONFIGURED"
        assert manager.channel_status("push") == "NOT_CONFIGURED"
        assert manager.channel_status("sms") == "NOT_CONFIGURED"

    def test_notify_local_delivered(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        created = manager.create("info", "note", "hello", "src")
        result = manager.notify(created["id"])
        assert result["results"]["local"]["delivered"] is True
        assert manager.alert_log()
        assert manager.alert_log()[0]["alert_id"] == created["id"]

    def test_notify_external_never_claims_delivery(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        created = manager.create("high", "urgent", "fire", "src")
        result = manager.notify(created["id"])
        assert result["results"]["email"]["status"] == "NOT_CONFIGURED"
        assert result["results"]["email"]["delivered"] is False
        assert result["results"]["push"]["delivered"] is False
        assert result["results"]["sms"]["delivered"] is False
        assert result["delivered_any"] is True
        assert result["results"]["local"]["delivered"] is True

    def test_severity_count_rollup(self, tmp_path):
        manager = AlertManager(KeyValueStore(str(tmp_path / "alerts.json")))
        manager.create("info", "a", "b", "s")
        manager.create("high", "c", "d", "s")
        manager.create("critical", "e", "f", "s")
        counts = manager.severity_count()
        assert counts["info"] == 1
        assert counts["high"] == 1
        assert counts["critical"] == 1
        assert counts["total"] == 3

    def test_persisted_across_instances(self, tmp_path):
        path = str(tmp_path / "alerts.json")
        AlertManager(KeyValueStore(path)).create("high", "t", "m", "s")
        reopened = AlertManager(KeyValueStore(path))
        assert len(reopened.list()) == 1
        assert reopened.list()[0]["title"] == "t"


class TestKnowledgeGraph:

    def test_add_node_and_neighbors(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        graph.add_node("a", "service")
        graph.add_node("b", "service")
        graph.add_node("c", "device")
        graph.add_edge("a", "b", "related", weight=2.0)
        graph.add_edge("a", "c", "runs_on")
        neighbors = graph.neighbors("a")
        assert {n["node"] for n in neighbors} == {"b", "c"}
        assert graph.neighbors("a", relation="runs_on")[0]["node"] == "c"
        assert graph.neighbors("ghost") == []

    def test_shortest_path_bfs(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        for node in ("a", "b", "c", "d"):
            graph.add_node(node)
        graph.add_edge("a", "b", "links")
        graph.add_edge("a", "c", "links")
        graph.add_edge("b", "d", "links")
        graph.add_edge("c", "d", "links")
        result = graph.shortest_path("a", "d")
        assert result["found"] is True
        assert result["weight"] == 2.0
        assert result["path"][0] == "a" and result["path"][-1] == "d"

    def test_shortest_path_dijkstra_weighted(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        for node in ("a", "b", "c"):
            graph.add_node(node)
        graph.add_edge("a", "b", "path", weight=1.0)
        graph.add_edge("a", "c", "path", weight=10.0)
        graph.add_edge("b", "c", "path", weight=1.0)
        result = graph.shortest_path("a", "c")
        assert result["path"] == ["a", "b", "c"]
        assert result["weight"] == 2.0

    def test_hierarchical_cycle_detection(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        graph.add_node("A", "species")
        graph.add_node("B", "species")
        assert graph.add_edge("A", "B", "is_a")["added"] is True
        rejected = graph.add_edge("B", "A", "is_a")
        assert rejected["added"] is False
        assert rejected["reason"] == "cycle"

    def test_dangling_and_consistency(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        graph.add_node("a")
        graph.add_node("b")
        graph.add_edge("a", "b", "related")
        graph.remove_node("b")
        assert graph.check_consistency()["ok"] is True
        graph.kv.set("graph.edges", {"phantom": {
            "src": "a", "dst": "ghost", "relation": "r", "weight": 1.0,
        }})
        report = graph.check_consistency()
        assert report["ok"] is False
        assert report["dangling_edges"]

    def test_retire_not_delete(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        graph.add_node("x", "entity", {"pinned": True})
        graph.add_node("y", "entity")
        graph.add_edge("x", "y", "related")
        assert graph.remove_node("x") is True
        assert graph.node("x")["retired"] is True
        assert "x" in graph.retired()
        assert graph.summarize()["retired_nodes"] == 1
        graph.add_node("x", "entity", {"pinned": True})
        assert graph.node("x")["retired"] is False
        assert "x" not in graph.retired()
        assert graph.remove_node("nope") is False

    def test_summarize(self, tmp_path):
        graph = KnowledgeGraph(KeyValueStore(str(tmp_path / "graph.json")))
        graph.add_node("r", "room")
        graph.add_node("l", "light")
        graph.add_node("w", "window")
        graph.add_edge("r", "l", "contains")
        graph.add_edge("r", "w", "contains")
        summary = graph.summarize()
        assert summary["nodes"] == 3
        assert summary["edges"] == 2
        assert summary["by_type"]["room"] == 1
        assert summary["by_type"]["light"] == 1
        assert summary["by_relation"]["contains"] == 2

    def test_persisted_restore(self, tmp_path):
        path = str(tmp_path / "graph.json")
        first = KnowledgeGraph(KeyValueStore(path))
        first.add_node("start")
        first.add_node("mid")
        first.add_node("end")
        first.add_edge("start", "mid", "leads")
        first.add_edge("mid", "end", "leads")
        reopened = KnowledgeGraph(KeyValueStore(path))
        result = reopened.shortest_path("start", "end")
        assert result["found"] is True
        assert result["weight"] == 2.0
        assert reopened.summarize()["nodes"] == 3


class TestAssimilation:

    def test_triple_extraction(self, tmp_path):
        engine = AssimilationEngine(KeyValueStore(str(tmp_path / "assim.json")))
        result = engine.assimilate("A cat is a kind of animal. The sky is blue.", "src-1")
        triples = result["triples"]
        assert ("cat", "kind_of", "animal") in triples
        assert ("sky", "is", "blue") in triples
        assert result["extraction"]["source_id"] == "src-1"

    def test_candidate_facts_dedup(self, tmp_path):
        engine = AssimilationEngine(KeyValueStore(str(tmp_path / "assim.json")))
        result = engine.assimilate("Water is wet. Water is wet.", "src-1")
        assert result["triples"].count(("water", "is", "wet")) == 1

    def test_store_provenance(self, tmp_path):
        engine = AssimilationEngine(KeyValueStore(str(tmp_path / "assim.json")))
        result = engine.assimilate("A cat is a kind of animal.", "src-77")
        stored = engine.store(result)
        assert stored["stored"] == 1
        node = engine.graph.node("cat")
        assert node["attrs"]["source_id"] == "src-77"
        assert engine.graph.shortest_path("cat", "animal")["found"] is True

    def test_conflicts_is_is_not(self, tmp_path):
        engine = AssimilationEngine(KeyValueStore(str(tmp_path / "assim.json")))
        engine.record_triple("sun", "is", "star", source_id="s1")
        engine.record_triple("sun", "is_not", "star", source_id="s2")
        conflicts = engine.conflicts()
        assert any(
            c["reason"] == "A is B vs A is not B"
            and c["left"] == ("is", "sun", "star")
            for c in conflicts
        )

    def test_conflicts_depends_on(self, tmp_path):
        engine = AssimilationEngine(KeyValueStore(str(tmp_path / "assim.json")))
        engine.record_triple("app", "depends_on", "db", source_id="s1")
        engine.record_triple("db", "depends_on", "app", source_id="s2")
        conflicts = engine.conflicts()
        assert any(c["reason"] == "A depends_on B vs B depends_on A" for c in conflicts)


class TestFactChecker:

    def test_supported(self):
        checker = FactChecker()
        result = checker.check("water boils at 100 degrees", ["water boils at 100 degrees"])
        assert result["verdict"] == "supported"
        assert 0.5 < result["confidence"] <= 1.0
        assert result["evidence"][0]["supports"] is True

    def test_contradicted(self):
        checker = FactChecker()
        result = checker.check("the sky is blue", ["the sky is not blue"])
        assert result["verdict"] == "contradicted"
        assert result["evidence"][0]["contradicts"] is True
        assert result["evidence"][0]["markers"]

    def test_uncertain_without_sources(self):
        checker = FactChecker()
        result = checker.check("penguins fly like eagles", [])
        assert result["verdict"] == "uncertain"
        assert result["confidence"] <= 0.5

    def test_uncertain_unrelated_source(self):
        checker = FactChecker()
        result = checker.check("penguins fly like eagles", ["mountains are tall and rocky"])
        assert result["verdict"] == "uncertain"

    def test_cross_check_agreement(self):
        checker = FactChecker()
        agreement = checker.cross_check(["water boils at 100", "water boils at 100 exactly"])
        assert agreement["agreement"] >= 0.5
        assert agreement["consistent"] is True

    def test_web_verification_honest(self):
        checker = FactChecker()
        result = checker.verify_web("anything")
        assert result["status"] == "NOT_CONFIGURED"

    def test_audit_trace(self):
        checker = FactChecker()
        checker.check("water boils at 100", ["water boils at 100"])
        checker.check("the sky is blue", ["the sky is not blue"])
        audit = checker.audit()
        assert audit["total_checks"] == 2
        assert audit["external_verification"]["status"] == "NOT_CONFIGURED"
        assert len(audit["checks"]) == 2


class TestMemoryLifecycle:

    def _db(self, tmp_path, name="m.db"):
        return MemoryDatabase(str(tmp_path / name))

    def _lc(self, tmp_path, db, name="life.json"):
        return MemoryLifecycle(db, KeyValueStore(str(tmp_path / name)))

    def _backdate(self, tmp_path, db_path, memory_id, days=365):
        old = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        connection = sqlite3.connect(db_path)
        connection.execute(
            "UPDATE memories SET created_at = ? WHERE id = ?", (old, memory_id)
        )
        connection.commit()
        connection.close()

    def test_age_decays_importance(self, tmp_path):
        db = self._db(tmp_path)
        memory_id = db.add("old fact", importance=7)
        self._backdate(tmp_path, str(tmp_path / "m.db"), memory_id, days=365)
        lifecycle = self._lc(tmp_path, db)
        result = lifecycle.age(decay_rate=0.25)
        assert result["decayed"] == 1
        rows = {row[0]: row for row in db.get_all()}
        assert rows[memory_id][5] < 7

    def test_protected_not_decayed(self, tmp_path):
        db = self._db(tmp_path)
        memory_id = db.add("precious", importance=7)
        self._backdate(tmp_path, str(tmp_path / "m.db"), memory_id, days=365)
        lifecycle = self._lc(tmp_path, db)
        lifecycle.protect(memory_id)
        assert lifecycle.is_protected(memory_id) is True
        lifecycle.age(decay_rate=0.25)
        rows = {row[0]: row for row in db.get_all()}
        assert rows[memory_id][5] == 7

    def test_important_fact_not_decayed(self, tmp_path):
        db = self._db(tmp_path)
        memory_id = db.add("vital rule", importance=8)
        self._backdate(tmp_path, str(tmp_path / "m.db"), memory_id, days=365)
        lifecycle = self._lc(tmp_path, db)
        result = lifecycle.age(decay_rate=1.0)
        assert result["skipped_important"] == 1
        rows = {row[0]: row for row in db.get_all()}
        assert rows[memory_id][5] == 8

    def test_no_delete_guarantee(self, tmp_path):
        db = self._db(tmp_path)
        memory_id = db.add("forgettable detail", importance=1)
        lifecycle = self._lc(tmp_path, db)
        candidates = lifecycle.candidates_for_forgetting(threshold=3)
        assert any(c["id"] == memory_id for c in candidates)
        assert all(c["delete_required"] is False for c in candidates)
        ids = {row[0] for row in db.get_all()}
        assert memory_id in ids

    def test_protected_excluded_from_candidates(self, tmp_path):
        db = self._db(tmp_path)
        memory_id = db.add("keep me", importance=2)
        lifecycle = self._lc(tmp_path, db)
        lifecycle.protect(memory_id)
        candidates = lifecycle.candidates_for_forgetting(threshold=3)
        assert all(c["id"] != memory_id for c in candidates)

    def test_merge_duplicates_suggests(self, tmp_path):
        db = self._db(tmp_path)
        left = db.add("boss likes red")
        right = db.add("boss likes red wine")
        lifecycle = self._lc(tmp_path, db)
        suggestions = lifecycle.merge_duplicates(threshold=0.5)
        assert suggestions
        matched = [s for s in suggestions if set(s["pair"]) == {left, right}]
        assert matched
        assert matched[0]["overlap"] >= 0.5
        assert matched[0]["merge_required"] is False
        assert "boss likes red" in matched[0]["draft_merged"]

    def test_summarize_and_settings_persistence(self, tmp_path):
        db = self._db(tmp_path)
        memory_id = db.add("something to protect", importance=4)
        lifecycle = self._lc(tmp_path, db)
        lifecycle.protect(memory_id)
        lifecycle.age(decay_rate=0.1)
        summary = lifecycle.summarize()
        assert summary["total"] == 1
        assert summary["protected_count"] == 1
        assert summary["last_age"] is not None

        reopened = MemoryLifecycle(db, KeyValueStore(str(tmp_path / "life.json")))
        assert reopened.is_protected(memory_id) is True
        assert reopened.summarize()["protected_count"] == 1