"""Multi-step planning contract (row 05) — splitting and execution."""

from brain.multi_step import MultiStepRunner, plan_steps


class TestPlanSteps:

    def test_splits_commas_then_and(self):
        steps = plan_steps("open a, close b and open c")
        assert steps == ["open a", "close b", "open c"]

    def test_does_not_split_subfolder_list(self):
        steps = plan_steps("create folder src and tests")
        assert steps == ["create folder src and tests"]

    def test_path_lists_kept_intact(self):
        steps = plan_steps("create folder src and tests and write readme.md")
        assert "create folder src and tests" in steps
        assert "write readme.md" in steps

    def test_empty_request(self):
        assert plan_steps("   ") == []

    def test_arven_prefix_ignored(self):
        steps = plan_steps("Arven, create folder a and open b")
        assert "create folder a" in steps


class TestRunner:

    def test_stop_on_failure(self):
        class FakeRegistry:
            def __init__(self):
                self.calls = []

            def invoke(self, tool, **kwargs):
                self.calls.append(tool)
                if tool == "open_app":
                    return {"success": False, "message": "no app"}
                return {"success": True}

        registry = FakeRegistry()
        runner = MultiStepRunner(registry=registry)
        outcome = runner.run("open missing_app and create file x.txt",
                             stop_on_failure=True)
        assert outcome["success"] is False
        assert "failed_step" in outcome

    def test_partial_failure_continues(self):
        class FakeRegistry:
            def __init__(self):
                self.calls = []

            def invoke(self, tool, **kwargs):
                self.calls.append(tool)
                if tool == "open_app":
                    return {"success": False, "message": "no app"}
                return {"success": True}

        registry = FakeRegistry()
        runner = MultiStepRunner(registry=registry)
        outcome = runner.run("open missing_app and create file x.txt",
                             stop_on_failure=False)
        assert outcome["success"] is False
        assert len(outcome["results"]) == 2