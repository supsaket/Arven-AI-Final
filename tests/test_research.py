"""Research agent contract (row 12) — honest multi-source synthesis."""

from brain.research import ResearchAgent, research_agent


def fake_results():
    return [{"title": "A", "snippet": "Growth hit 10% in 2025", "url": "u1"},
            {"title": "B", "snippet": "Growth hit 10% in 2025 too", "url": "u2"}]


class TestQueryExtraction:

    def test_strips_research_prefix(self):
        assert research_agent.extract_query(
            "research global warming") == "global warming"

    def test_strips_look_up_prefix(self):
        assert research_agent.extract_query("look up python") == "python"

    def test_trailing_instruction_stripped(self):
        assert research_agent.extract_query(
            "research climate change and summarize it") == "climate change"

    def test_query_with_and_preserved(self):
        assert research_agent.extract_query(
            "research health and fitness") == "health and fitness"


class TestSearch:

    def test_search_returns_structured_results(self):
        agent = ResearchAgent(
            searcher=lambda q: {"results": fake_results(), "message": "ok"})
        found = agent.search(query="growth")
        assert found["success"] is True
        assert len(found["results"]) == 2

    def test_sources_preserved_per_result(self):
        agent = ResearchAgent(
            searcher=lambda q: {"results": fake_results()})
        found = agent.search(query="growth")
        for result in found["results"]:
            assert result["source"]

    def test_empty_results_are_honest(self):
        agent = ResearchAgent(searcher=lambda q: {"results": [], "count": 0})
        found = agent.search(query="nothing here at all")
        assert found["success"] is False
        assert found["results"] == []

    def test_offline_unreachable_honest(self):
        agent = ResearchAgent(
            searcher=lambda q: {"results": [], "offline": True,
                                "message": "offline"})
        found = agent.search(query="x")
        assert found["offline"] is True
        assert found["success"] is False


class TestSynthesis:

    def test_rule_based_without_llm(self):
        agent = ResearchAgent(
            searcher=lambda q: {"results": fake_results()})
        found = agent.search(query="growth")
        synthesis = agent.synthesize(found["query"], found["results"])
        assert synthesis["rule_based"] is True
        assert synthesis["answer"]
        assert all(src in synthesis["answer"] for src in ("Source 1", "Source 2"))

    def test_injected_model_used(self):
        agent = ResearchAgent(
            searcher=lambda q: {"results": fake_results()},
            model_fn=lambda q, r: "model summary here")
        found = agent.search(query="growth")
        synthesis = agent.synthesize(found["query"], found["results"])
        assert synthesis["answer"] == "model summary here"
        assert synthesis["rule_based"] is False

    def test_synthesis_failure_still_rule_based(self):
        agent = ResearchAgent(
            searcher=lambda q: {"results": fake_results()},
            model_fn=lambda q, r: (_ for _ in ()).throw(RuntimeError("boom")))
        found = agent.search(query="growth")
        synthesis = agent.synthesize(found["query"], found["results"])
        assert synthesis["answer"]
        assert synthesis["success"] is True


class TestConflicts:

    def test_conflict_detected_between_sources(self):
        results = [{"title": "A", "snippet": "Growth hit 10% in 2025", "url": "u1"},
                   {"title": "B", "snippet": "Growth hit 25% in 2025", "url": "u2"}]
        agent = ResearchAgent()
        conflicts = agent.conflicts("growth", results)
        assert len(conflicts) >= 1

    def test_no_conflict_when_agreeing(self):
        results = fake_results()
        agent = ResearchAgent()
        assert agent.conflicts("growth", results) == []


class TestReport:

    def test_report_has_answer_and_sources(self):
        agent = ResearchAgent(searcher=lambda q: {"results": fake_results()})
        report = agent.report(query="growth")
        assert report["success"] is True
        assert report["answer"]
        assert len(report["sources"]) == 2