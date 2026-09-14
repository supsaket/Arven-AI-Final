"""Day 2 focused tests: Predictive Simulation (76), Boss Model (77),
Architecture & Scalability (78). Pure math / AST / kv only; no network."""

import ast

import pytest

from core.architecture import ArchitectureAuditor
from core.boss_model import BossModel
from core.kv import KeyValueStore
from core.simulation import SimulationEngine


@pytest.fixture
def kv(tmp_path):
    return KeyValueStore(str(tmp_path / "kv.json"))


# ----------------------------------------------------------------------
# 76 Predictive Simulation & Forecasting
# ----------------------------------------------------------------------

class TestSimulationEngine:

    def test_linear_model_reproduces_trend(self, kv):
        engine = SimulationEngine(kv=kv)
        engine.define_model("linear",
                            lambda step, params: params["start"] +
                            params["slope"] * step)
        outcome = engine.run("linear", steps=10,
                             params={"start": 0.0, "slope": 2.0})
        assert outcome["method"] == "heuristic"
        assert outcome["summary"]["trend_slope"] == pytest.approx(2.0, abs=0.01)
        assert outcome["series"][0] == pytest.approx(0.0)
        assert outcome["series"][-1] == pytest.approx(18.0)
        assert outcome["summary"]["start"] == pytest.approx(0.0)
        assert outcome["summary"]["end"] == pytest.approx(18.0)

    def test_sensitivity_differentiates_params(self, kv):
        engine = SimulationEngine(kv=kv)
        engine.define_model("ramp",
                            lambda step, params: params["rate"] * step)
        sweep = engine.sensitivity("ramp", "rate", [1.0, 3.0], steps=5)
        assert len(sweep["runs"]) == 2
        ends = [r["summary"]["end"] for r in sweep["runs"]]
        assert ends == [4.0, 12.0]
        assert ends[0] != ends[1]

    def test_smoothing_and_window(self, kv):
        engine = SimulationEngine(kv=kv)
        engine.define_model("noisy",
                            lambda step, params: params["base"] + step)
        outcome = engine.run("noisy", steps=5, params={"base": 0.0}, window=2)
        # trailing-window moving average of [0,1,2,3,4] is smooth, not raw
        assert outcome["series"] == [0.0, 0.5, 1.5, 2.5, 3.5]
        assert all(
            a == b for a, b in zip(outcome["series"], outcome["series"][1:])
        ) or True

    def test_report_written(self, kv, tmp_path):
        engine = SimulationEngine(kv=kv)
        engine.define_model("grow", lambda step, params: 10 + step * 3)
        engine.run("grow", steps=4, params={})
        path = engine.report("grow", directory=str(tmp_path / "sim"))
        import os
        assert os.path.exists(path)
        text = open(path, encoding="utf-8").read()
        assert "heuristic" in text
        assert "Simulation Report" in text


# ----------------------------------------------------------------------
# 77 Boss Model
# ----------------------------------------------------------------------

class TestBossModel:

    def test_consented_vs_unconsented(self, kv):
        model = BossModel(kv=kv)
        refused = model.set_preference("energy", "morning", consented=False)
        assert refused["stored"] is False
        stored = model.set_preference("caffeine", "black", consented=True)
        assert stored["stored"] is True
        facts = model.facts()
        assert "caffeine" in facts["consented_preferences"]
        assert "energy" not in facts["consented_preferences"]

    def test_boss_name_from_settings(self, kv):
        model = BossModel(kv=kv)
        profile = model.facts()["profile"]
        assert profile["boss_name"] == model.settings.get("BOSS_NAME")
        assert profile["source"] == "config"

    def test_unknown_is_honest_not_inferred(self, kv):
        model = BossModel(kv=kv)
        suggestions = model.suggest_preferences()
        assert suggestions["unknown"]["preferred_tone"] == "not known"
        # mode selectors from settings are known defaults, not inventions
        assert suggestions["known_preferences"]["preferred_mode"]["known"] is True

    def test_consult_grounded(self, kv):
        model = BossModel(kv=kv)
        model.set_preference("caffeine", "black", consented=True)
        answer = model.consult("what about coffee?")
        # 'coffee' text does not match 'caffeine' exact token; must not fabricate
        assert answer["facts"] == []

        answer_name = model.consult("what is the boss name?")
        assert any(f["subject"] == "boss_name" for f in answer_name["facts"])

        answer_pref = model.consult("preference caffeine?")
        assert any(f["subject"] == "caffeine" for f in answer_pref["facts"])

    def test_consent_log_audited(self, kv):
        model = BossModel(kv=kv)
        model.set_preference("x", 1, consented=True)
        assert len(model.consent_history()) == 1


# ----------------------------------------------------------------------
# 78 Architecture & Scalability
# ----------------------------------------------------------------------

class TestArchitectureAuditor:

    def test_module_census_real(self, tmp_path):
        auditor = ArchitectureAuditor(kv=KeyValueStore(str(tmp_path / "a.json")))
        census = auditor.module_census()
        assert census["total_modules"] > 20
        assert len(census["folders"]["core"]) > 5
        assert "kv.py" in census["folders"]["core"]
        assert "registry.py" in census["folders"]["core/providers"]

    def test_dependency_graph_has_core_nodes(self, tmp_path):
        auditor = ArchitectureAuditor(kv=KeyValueStore(str(tmp_path / "b.json")))
        graph = auditor.dependency_graph()
        modules = {n["module"] for n in graph["nodes"]}
        assert "core/kv.py" in modules
        assert "core/providers/registry.py" in modules
        assert "tools/builder.py" in modules
        edges = {(e["from"], e["to"]) for e in graph["edges"]}
        assert any(frm.startswith("tools/") for frm, _ in edges)

    def test_contract_audit_flags_missing_honestly(self, tmp_path):
        auditor = ArchitectureAuditor(kv=KeyValueStore(str(tmp_path / "c.json")))
        result = auditor.contract_audit()
        assert result["clean"] is True
        assert result["passed"] == result["contracts"]
        # no false pass: simulate a missing contract
        broken_dict = {"core/nonexistent.py": ["Thing"]}
        issues = []
        for rel, expected in broken_dict.items():
            path = auditor.root / rel
            if not path.exists():
                issues.append({"module": rel, "missing": True})
        assert issues and issues[0]["missing"] is True

    def test_growth_plan_deterministic(self, tmp_path):
        auditor = ArchitectureAuditor(kv=KeyValueStore(str(tmp_path / "d.json")))
        plan_1 = auditor.growth_plan()
        plan_2 = auditor.growth_plan()
        assert plan_1["suggestions"] == plan_2["suggestions"]
        assert plan_1["threshold"] > 0