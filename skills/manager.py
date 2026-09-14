"""Skill / plugin system (row 22).

A skill is a directory beneath ``skills/``:
* ``skills/<name>/skill.py`` with a plain ``run(context: dict) -> dict``
  function — the executable entry point
* optional ``manifest.json`` describing the skill

A skill whose directory has no ``skill.py`` entry is NOT executable.
Discovery is isolated: a broken skill loads as unavailable, never crashes.
"""

import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


class Skill:

    def __init__(self, name, directory, manifest=None, entry=None):
        self.name = name
        self.directory = directory
        self.manifest = manifest or {}
        self.entry = entry  # path to skill.py or None

    @property
    def executable(self):
        return self.entry is not None and self.entry.exists()

    def describe(self):
        return {
            "name": self.name,
            "executable": self.executable,
            "description": self.manifest.get("description", ""),
            "version": self.manifest.get("version", ""),
            "entry": str(self.entry) if self.entry else None,
        }

    def run(self, context=None):
        if not self.executable:
            return {"success": False, "skill": self.name,
                    "message": "skill has no executable entry (" + str(self.entry) + ")"}
        module = self._load_module()
        if module is None:
            return {"success": False, "skill": self.name,
                    "message": "skill entry could not be loaded"}
        func = getattr(module, "run", None)
        if not callable(func):
            return {"success": False, "skill": self.name,
                    "message": "skill entry has no run(context) function"}
        try:
            result = func(context or {})
            return result if isinstance(result, dict) else \
                {"success": True, "skill": self.name, "result": result}
        except Exception as exc:
            return {"success": False, "skill": self.name,
                    "message": f"skill error: {exc}"}

    def _load_module(self):
        try:
            spec = importlib.util.spec_from_file_location(
                f"arven_skill_{self.name}", self.entry)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception:
            return None


class SkillManager:

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else BASE / "skills"
        self._cache = {}

    def discover(self):
        skills = {}
        if not self.directory.exists():
            return skills
        for folder in self.directory.iterdir():
            if not folder.is_dir() or folder.name.startswith((".", "_")):
                continue
            skills[folder.name] = self._load_skill(folder.name, folder)
        self._cache = skills
        return skills

    def _load_skill(self, name, folder):
        manifest = {}
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        entry = folder / "skill.py"
        entry = entry if entry.exists() else None
        return Skill(name, folder, manifest, entry)

    def list(self):
        return [{"name": name, "executable": skill.executable}
                for name, skill in sorted(self.discover().items())]

    def get(self, name):
        self.discover()
        return self._cache.get(name)

    def run(self, name, context=None):
        skill = self.get(name)
        if skill is None:
            return {"success": False, "skill": name, "message": "unknown skill"}
        return skill.run(context)


skill_manager = SkillManager()

__all__ = ["Skill", "SkillManager", "skill_manager"]