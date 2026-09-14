"""Agent contract (row 05) — multi-action split, create parsing, locations."""

from brain.agent import ActionParser, Agent


class TestSplitActions:

    def test_multiple_apps(self):
        parser = ActionParser()
        actions = parser.split_actions("open notepad and calculator and youtube")
        assert len(actions) == 3
        assert all("open" in action.lower() for action in actions)

    def test_repeated_verb_not_duplicated(self):
        parser = ActionParser()
        actions = parser.split_actions("open notepad and open calculator")
        # 'open notepad' and 'open calculator' are distinct, but the head verb
        # is not duplicated with itself
        lowered = [a.lower() for a in actions]
        assert "open notepad" in lowered
        assert "open calculator" in lowered

    def test_mixed_verbs(self):
        parser = ActionParser()
        actions = parser.split_actions("open notepad and close calculator")
        assert len(actions) == 2
        assert any(a.lower().startswith("open") for a in actions)
        assert any(a.lower().startswith("close") for a in actions)


class TestCreateParsing:

    def test_create_file(self, tmp_path):
        parser = ActionParser()
        parsed = parser.parse_create("create file notes.txt")
        assert parsed["kind"] == "file"
        assert parsed["target"] == "notes.txt"

    def test_create_folder(self):
        parser = ActionParser()
        parsed = parser.parse_create("create folder projects")
        assert parsed["kind"] == "folder"

    def test_desktop_location_resolved(self):
        parser = ActionParser()
        parsed = parser.parse_create("create folder projects on desktop")
        resolved = parser.resolve_location(parsed)
        assert resolved is not None
        from pathlib import Path
        assert Path(resolved).name.lower() in ("desktop",)

    def test_downloads_location_resolved(self):
        parser = ActionParser()
        parsed = parser.parse_create("create folder project in downloads")
        resolved = parser.resolve_location(parsed)
        assert "ownloads" in resolved.lower()

    def test_create_folder_command_rejects_file(self):
        parser = ActionParser()
        assert parser.parse_create_folder("create file a.txt") is None


class TestAgentPlan:

    def test_plan_returns_low_level_commands(self):
        agent = Agent()
        plan = agent.plan("open notepad and calculator")
        assert plan

    def test_plan_create_file(self):
        agent = Agent()
        plan = agent.plan("create file hello.txt")
        assert any("create_file" in command for command in plan)

    def test_parser_exposes_reference_manager(self):
        parser = ActionParser()
        parser.refs.track_opened("demo", name="demo")
        assert parser.refs.resolve("it")["status"] in ("resolved", "ambiguous")