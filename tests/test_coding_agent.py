"""Coding agent contract (row 14) — scoped, safe, truthful."""

import inspect

from brain.coding_agent import CodingAgent, coding_agent
from core.clarification import ClarificationRequired


class TestSafeCreation:

    def test_create_file_in_scope(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "hello.py"
        outcome = agent.create_file(str(path), "print('hi')")
        assert outcome["success"] is True
        assert path.exists()

    def test_no_overwrite_unless_confirmed(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "exists.py"
        path.write_text("old", encoding="utf-8")
        outcome = agent.create_file(str(path), "new")
        assert outcome["success"] is False

    def test_overwrite_with_confirm(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "exists.py"
        path.write_text("old", encoding="utf-8")
        outcome = agent.create_file(str(path), "new", confirm=True)
        assert outcome["success"] is True


class TestInspect:

    def test_inspect_file(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "code.py"
        path.write_text("line1\nline2\n", encoding="utf-8")
        outcome = agent.inspect_file(str(path))
        assert outcome["success"] is True
        assert outcome["lines"] == 2

    def test_inspect_project(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        (tmp_path / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "b.py").write_text("y", encoding="utf-8")
        outcome = agent.inspect_project()
        assert outcome["success"] is True
        assert outcome["count"] >= 2

    def test_inspect_missing_file(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        outcome = agent.inspect_file(str(tmp_path / "nope.py"))
        assert outcome["success"] is False


class TestModify:

    def test_modify_makes_backup(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "edit.py"
        path.write_text("original", encoding="utf-8")
        outcome = agent.modify(str(path), "changed")
        assert outcome["success"] is True
        assert (tmp_path / "edit.py.bak").exists()

    def test_dangerous_refused(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "edit.py"
        path.write_text("original", encoding="utf-8")
        outcome = agent.modify(str(path), "rm -rf everything on disk")
        assert outcome["success"] is False


class TestScope:

    def test_resolve_tracks_scope(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        allowed = agent.resolve(str(tmp_path / "inside.py"))
        assert allowed["allowed"] is True

    def test_resolve_refuses_outside(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        outside = tmp_path.parent.parent.parent / "outside.py"
        outcome = agent.resolve(str(outside))
        assert outcome["allowed"] is False


class TestVerification:

    def test_failed_test_not_claimed_fixed(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        outcome = agent.verify(["py -m pytest failing_test.py"])
        assert outcome["success"] is False
        assert outcome["claimed_fixed"] is False

    def test_truthful_result_struct(self, tmp_path):
        agent = CodingAgent(scope=tmp_path,
                            runner=lambda cmd: {"returncode": 0, "output": ""})
        outcome = agent.verify(["true"])
        assert outcome["success"] is True
        assert outcome["results"][0]["passed"] is True


class TestRunAndClarify:

    def test_run_parses_inspect(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "code.py"
        path.write_text("x = 1", encoding="utf-8")
        outcome = agent.run(f"inspect file {path}")
        assert outcome["success"] is True

    def test_clarification_when_ambiguous(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        try:
            agent.run("inspect that")
        except ClarificationRequired as exc:
            assert "file" in exc.question.lower()
        else:
            raise AssertionError("expected ClarificationRequired")

    def test_structured_report_lists_changed_files(self, tmp_path):
        agent = CodingAgent(scope=tmp_path)
        path = tmp_path / "track.py"
        path.write_text("a", encoding="utf-8")
        agent.modify(str(path), "b")
        assert str(path) in agent._changes
        changed = sorted(agent._changes)
        assert len(changed) == 1
        assert "track.py" in changed[0]


class TestNoRawSubprocess:

    def test_agent_never_shells_out_directly(self):
        source = inspect.getsource(coding_agent.__class__)
        assert "import subprocess" not in source
        assert "os.system" not in source