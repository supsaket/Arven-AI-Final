"""Tool registry contract (row 23) — registration, validation, gates."""

from tools.builder import get_registry
from tools.registry import Tool, ToolRegistry, ToolError


class TestRegistration:

    def test_duplicate_registration_rejected(self):
        registry = ToolRegistry()

        def handler(**kwargs):
            return {"success": True}

        registry.register(Tool("dup", handler, category="Test"))
        try:
            registry.register(Tool("dup", handler, category="Test"))
        except ToolError:
            pass
        else:
            raise AssertionError("duplicate registration must fail")
        assert len(registry.names()) == 1

    def test_register_and_get(self):
        registry = ToolRegistry()

        def handler(**kwargs):
            return {"success": True}

        registry.register(Tool("probe", handler, category="Test"))
        assert registry.has("probe")
        assert "probe" in registry.names()
        assert "Test" in registry.categories()

    def test_find_by_keyword(self):
        registry = get_registry()
        assert any("date" in name for name in registry.find("date"))


class TestInvocation:

    def test_unknown_tool(self):
        registry = get_registry()
        outcome = registry.invoke("no_such_tool")
        assert outcome["status"] == "error"
        assert outcome["success"] is False

    def test_missing_required_argument(self):
        registry = get_registry()
        outcome = registry.invoke("read_file")
        assert outcome["status"] == "invalid_argument"

    def test_undeclared_argument_rejected(self):
        registry = get_registry()
        outcome = registry.invoke("date_time", bogus_argument=1)
        assert outcome["status"] == "invalid_argument"

    def test_high_risk_needs_confirmation(self):
        registry = get_registry()
        outcome = registry.invoke("run_shell", command="echo hi",
                                  confirmed=False)
        assert outcome["status"] == "confirm_required"

    def test_destructive_needs_confirmation(self):
        registry = get_registry()
        outcome = registry.invoke("delete_file", path="x.txt",
                                  confirmed=False)
        assert outcome["status"] == "confirm_required"

    def test_safe_tool_runs(self):
        registry = get_registry()
        outcome = registry.invoke("date_time")
        assert outcome["success"] is True


class TestDescribe:

    def test_describe_has_metadata(self):
        registry = get_registry()
        info = registry.describe("date_time")
        assert info["name"] == "date_time"
        assert info["parameters"] is not None

    def test_status_of(self):
        registry = get_registry()
        status = registry.status_of("date_time")
        assert status in ("available", "unavailable")

    def test_capabilities(self):
        registry = get_registry()
        caps = registry.capabilities(use_sets=False)
        assert "file" in caps
        assert "web" in caps


class TestTool:

    def test_schema_shape(self):
        def handler(app):
            return {"success": True}

        tool = Tool("open_x", handler, category="Apps", risk="low",
                    parameters=[{"name": "app", "required": True, "hint": "str"}])
        schema = tool.schema()
        assert schema["name"] == "open_x"
        assert schema["description"]
        assert any(p["name"] == "app" for p in schema["parameters"])

    def test_signature_parameters_inferred(self):
        def handler(app, level=1):
            return {"success": True}

        tool = Tool("x", handler, category="Apps", risk="low",
                    parameters=[{"name": "app", "required": True, "hint": "str"}])
        inferred = {p["name"]: p for p in tool._parameters}
        assert inferred["app"]["required"] is True
        assert inferred["level"]["required"] is False