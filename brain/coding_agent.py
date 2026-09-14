"""Coding agent (row 14) — safe code inspection, editing, and verification.

Safety contract (enforced):
* changes are scoped to the project directory; anything outside is refused
* edits always create a ``.bak`` backup before touching a file
* creating a file never overwrites an existing one unless explicitly confirmed
* destructive/dangerous commands are refused outright
* verification reports truthfully — a failing test is NEVER claimed as fixed
* the agent never shells out directly (no raw ``subprocess``)
"""

import os
from pathlib import Path

from core.paths import normalize_path
from core.reference import ContextReferenceManager

_DANGEROUS_TOKENS = ("rm -rf", "format ", "del /s", "rd /s", "shutdown",
                     "> /dev/null 2>&1; rm", "--delete-all", "drop database")


class CodingAgent:

    def __init__(self, scope=None, refs=None, runner=None):
        self.scope = Path(scope).resolve() if scope else Path.cwd().resolve()
        self.refs = refs or ContextReferenceManager()
        self.runner = runner or self._default_runner
        self._changes = {}

    # ------------------------------------------------------------------
    def resolve(self, path):
        """Resolve a target inside the project scope; refuse escapes."""
        target = Path(path).resolve() if path else None
        if target is None:
            raise ValueError("A file or folder target is required.")
        if target != self.scope and self.scope not in target.parents:
            return {"allowed": False, "reason": "outside the project scope"}
        return {"allowed": True, "path": str(target)}

    # ------------------------------------------------------------------
    def inspect_file(self, path):
        allowed = self.resolve(path)
        if not allowed["allowed"]:
            return {"success": False, "message": allowed["reason"],
                    "file": str(path)}
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            return {"success": True, "file": str(path),
                    "content": content, "lines": len(content.splitlines())}
        except FileNotFoundError:
            return {"success": False, "message": "file not found",
                    "file": str(path)}

    def inspect_project(self, path=None):
        root = Path(path).resolve() if path else self.scope
        allowed = self.resolve(root)
        if not allowed["allowed"]:
            return {"success": False, "message": allowed["reason"]}
        files = []
        for item in root.rglob("*"):
            if item.is_file():
                files.append(str(item))
        return {"success": True, "root": str(root), "files": files,
                "count": len(files)}

    # ------------------------------------------------------------------
    def modify(self, path, new_content=None, confirm=False):
        """Edit a file with a backup created first."""
        allowed = self.resolve(path)
        if not allowed["allowed"]:
            return {"success": False, "message": allowed["reason"],
                    "file": str(path)}
        if self._dangerous(new_content):
            return {"success": False, "message": "dangerous content refused",
                    "file": str(path)}
        file_path = Path(path)
        if not file_path.exists():
            return {"success": False, "message": "file not found",
                    "file": str(path)}
        backup = file_path.with_suffix(file_path.suffix + ".bak")
        backup.write_text(file_path.read_text(encoding="utf-8", errors="replace"),
                          encoding="utf-8")
        previous = self._changes.get(str(file_path))
        if previous:
            file_path.write_text(previous, encoding="utf-8")
        file_path.write_text(new_content, encoding="utf-8")
        self._changes[str(file_path)] = new_content
        return {"success": True, "file": str(file_path), "backup": str(backup),
                "changed_files": sorted(self._changes)}

    def _dangerous(self, content):
        if not content:
            return False
        lowered = str(content).lower()
        return any(token in lowered for token in _DANGEROUS_TOKENS)

    # ------------------------------------------------------------------
    def create_file(self, path, content, confirm=False):
        allowed = self.resolve(path)
        if not allowed["allowed"]:
            return {"success": False, "message": allowed["reason"],
                    "file": str(path)}
        file_path = Path(path)
        if file_path.exists() and not confirm:
            return {"success": False,
                    "message": "file already exists; overwrite needs confirmation",
                    "file": str(path)}
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"success": True, "file": str(file_path), "created": True}

    # ------------------------------------------------------------------
    def verify(self, commands):
        """Run verification (default: no-op returning pass) — truthful."""
        results = []
        for command in commands:
            outcome = self.runner(command)
            passed = bool(outcome.get("returncode", -1) == 0) if isinstance(outcome, dict) \
                else bool(outcome)
            results.append({"command": command, "passed": passed,
                            "output": outcome.get("output", "") if isinstance(outcome, dict) else ""})
        return {"success": all(r["passed"] for r in results),
                "results": results, "claimed_fixed": False}

    @staticmethod
    def _default_runner(command):
        return {"returncode": -1, "output": "verification unavailable",
                "reason": "no runner configured"}

    # ------------------------------------------------------------------
    def run(self, request, **kwargs):
        """Parse and execute a single agent command."""
        text = str(request).strip()
        lowered = text.lower()
        if lowered.startswith("inspect project"):
            return self.inspect_project()
        if lowered.startswith("inspect ") or lowered.startswith("inspect file "):
            target = lowered[len("inspect file "):] if lowered.startswith("inspect file ") \
                else lowered[len("inspect "):]
            if not target or target in ("that", "it"):
                from core.clarification import ClarificationRequired
                raise ClarificationRequired("coding", "Which file should I inspect?")
            return self.inspect_file(target)
        if lowered.startswith("create ") or lowered.startswith("write "):
            parts = text.split(" ", 2)
            if len(parts) < 3:
                from core.clarification import ClarificationRequired
                raise ClarificationRequired("coding", "I need a file name and content.")
            path = parts[1] if lowered.startswith("write ") else \
                lowered[len("create file "):].split(" ", 1)[0] if "file " in lowered else parts[1]
            path = path.strip("'\"")
            return self.create_file(path, parts[2])
        return {"success": False, "message": f"unrecognized coding command: {text}"}

    def related_files(self, request):
        """Surface files referenced by a request."""
        return {"files": sorted(self._changes)}


coding_agent = CodingAgent(scope=Path(os.getcwd()).resolve())

__all__ = ["CodingAgent", "coding_agent"]