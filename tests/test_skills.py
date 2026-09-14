"""Skill / plugin contract (row 22) — discovery, execution, isolation."""

from skills.manager import Skill, SkillManager


def make_skill(tmp_path, name, code=None, manifest=None):
    folder = tmp_path / name
    folder.mkdir()
    if manifest is not None:
        (folder / "manifest.json").write_text(manifest, encoding="utf-8")
    if code is not None:
        (folder / "skill.py").write_text(code, encoding="utf-8")
    return folder


class TestDiscovery:

    def test_executable_skill_discovered(self, tmp_path):
        make_skill(tmp_path, "weather",
                   code="def run(context):\n    return {'success': True, 'temp': 21}\n",
                   manifest='{"description": "local weather"}')
        manager = SkillManager(directory=tmp_path)
        skills = manager.discover()
        assert "weather" in skills
        assert skills["weather"].executable is True

    def test_missing_entry_not_executable(self, tmp_path):
        folder = make_skill(tmp_path, "broken_dir")
        manager = SkillManager(directory=tmp_path)
        skill = manager.discover()["broken_dir"]
        assert skill.executable is False

    def test_list_and_get(self, tmp_path):
        make_skill(tmp_path, "alpha",
                   code="def run(context):\n    return {'success': True}\n")
        manager = SkillManager(directory=tmp_path)
        assert manager.list()
        assert manager.get("alpha") is not None
        assert manager.get("missing") is None


class TestExecution:

    def test_run_context(self, tmp_path):
        make_skill(tmp_path, "greet",
                   code=("def run(context):\n"
                         "    return {'success': True, 'greeting': 'hi ' + str(context.get('name', ''))}\n"))
        manager = SkillManager(directory=tmp_path)
        outcome = manager.run("greet", context={"name": "saket"})
        assert outcome["success"] is True
        assert outcome["greeting"] == "hi saket"

    def test_run_non_executable_skill(self, tmp_path):
        make_skill(tmp_path, "empty_skill")
        manager = SkillManager(directory=tmp_path)
        outcome = manager.run("empty_skill")
        assert outcome["success"] is False
        assert "no executable entry" in outcome["message"]

    def test_run_unknown_skill(self, tmp_path):
        manager = SkillManager(directory=tmp_path)
        outcome = manager.run("nope")
        assert outcome["success"] is False
        assert "unknown skill" in outcome["message"]

    def test_broken_skill_does_not_crash(self, tmp_path):
        make_skill(tmp_path, "explode",
                   code="raise ImportError('boom')\n")
        manager = SkillManager(directory=tmp_path)
        outcome = manager.run("explode")
        assert outcome["success"] is False
        assert isinstance(outcome["message"], str)


class TestManifest:

    def test_manifest_described(self, tmp_path):
        make_skill(tmp_path, "helper",
                   code="def run(context):\n    return {'success': True}\n",
                   manifest='{"description": "does things", "version": "1.0"}')
        manager = SkillManager(directory=tmp_path)
        desc = manager.get("helper").describe()
        assert desc["description"] == "does things"
        assert desc["version"] == "1.0"
        assert desc["executable"] is True