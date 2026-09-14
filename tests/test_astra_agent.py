"""Astra agent framework contract (row 19) — routing and honest unknown."""

from brain.astra_agent import (
    AstraEngine,
    astra_command_matching,
    astra_engine,
    astra_token,
    get_astra_agents,
    run_astra_command,
)


class TestAgents:

    def test_agents_collection(self):
        agents = get_astra_agents()
        assert isinstance(agents, list)
        assert "health" in agents
        assert "root" in agents

    def test_each_agent_has_precise_command(self):
        for agent in get_astra_agents():
            assert agent.strip()


class TestToken:

    def test_token_strips_command_name(self):
        assert astra_token("health status") == "health"
        assert astra_token("memory search") == "memory"
        assert astra_token("") == ""

    def test_matching(self):
        agents = get_astra_agents()
        assert astra_command_matching("health please", agents) is True
        assert astra_command_matching("gandalf list", agents) is False


class TestRun:

    def test_unknown_agent_honest(self):
        result = run_astra_command("gandalf list")
        assert result["success"] is False
        assert "unknown" in result["message"]

    def test_health_agent_runs(self):
        result = run_astra_command("health")
        assert result["success"] is True
        assert "result" in result

    def test_importance_of_bounded_operation(self):
        outcome = astra_engine.run("health")
        assert "result" in outcome

    def test_engine_list(self):
        assert astra_engine.list_agents()

    def test_engine_unknown(self):
        result = AstraEngine().run("vivaldi")
        assert result["success"] is False