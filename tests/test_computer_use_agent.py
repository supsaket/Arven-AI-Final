"""Computer use agent contract (row 13) — capability gating, observations."""

from brain.computer_use_agent import ComputerUseAgent, _REQUIRED_CAPABILITIES


class FakeDriver:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def perform(self, action, step, dry_run=False):
        self.calls.append(action)
        if not self.ok:
            return {"success": False, "message": "driver failed"}
        return {"success": True, "message": f"{action} done"}


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def invoke(self, tool, **kwargs):
        self.calls.append((tool, kwargs))
        return {"success": True, "message": tool}


class TestCapabilityGate:

    def test_missing_capability_reported_not_simulated(self):
        agent = ComputerUseAgent(
            registry=FakeRegistry(), driver=FakeDriver(),
            capabilities={"keyboard_mouse": False, "display": False},
        )
        for step in [{"action": "mouse_move", "x": 1, "y": 2},
                     {"action": "type", "text": "hi"}]:
            result = agent.run(step, dry_run=True)
            assert result["success"] is False

    def test_required_capabilities_mapped(self):
        assert "mouse_move" in _REQUIRED_CAPABILITIES
        assert "type" in _REQUIRED_CAPABILITIES


class TestRegistryRouting:

    def test_open_app_routes_to_registry(self):
        registry = FakeRegistry()
        agent = ComputerUseAgent(registry=registry, driver=FakeDriver())
        result = agent.run({"action": "open_app", "app": "notepad"}, dry_run=True)
        assert any(tool == "open_app" for tool, _ in registry.calls)

    def test_capture_screen_routes_to_registry(self):
        registry = FakeRegistry()
        agent = ComputerUseAgent(registry=registry, driver=FakeDriver())
        agent.run({"action": "capture_screen"}, dry_run=True)
        assert any(tool == "capture_screen" for tool, _ in registry.calls)


class TestObservations:

    def test_observations_before_and_after(self):
        agent = ComputerUseAgent(registry=FakeRegistry(), driver=FakeDriver())
        result = agent.run({"action": "type", "text": "hi"}, dry_run=True)
        assert result["observations"]["before"] is not None
        assert result["observations"]["after"] is not None
        assert result["observations"]["steps"] != []

    def test_step_failure_isolated(self):
        agent = ComputerUseAgent(registry=FakeRegistry(), driver=FakeDriver(ok=False))
        outcome = agent.run({"action": "mouse_move", "x": 1, "y": 2}, dry_run=True)
        assert outcome["success"] is False


class TestParsing:

    def test_empty_request_returns_help(self):
        agent = ComputerUseAgent(registry=FakeRegistry(), driver=FakeDriver())
        result = agent.run("   ", dry_run=True)
        assert result["help"]
        assert "actions" in result["help"]

    def test_parse_open_and_type(self):
        agent = ComputerUseAgent(registry=FakeRegistry(), driver=FakeDriver())
        steps = agent.parse_plan("open notepad and type hello")
        assert steps[0]["action"] == "open_app"
        assert steps[1]["action"] == "type"
        assert steps[1]["text"] == "hello"

    def test_unsupported_action_reported(self):
        agent = ComputerUseAgent(registry=FakeRegistry(), driver=FakeDriver())
        result = agent.run({"action": "fly"}, dry_run=True)
        assert result["success"] is False