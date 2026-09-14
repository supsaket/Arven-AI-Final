"""QA / Quality Control engine (feature 62, Day 2).

QARunner performs real static checks over a target path (AST parse, import
resolution, docstring heuristic, line length, trailing whitespace, TODO count)
and honestly runs pytest via ``py -m pytest``, parsing the summary line into
pass/fail counts. It never fakes a pass.
"""

import ast
import importlib.util
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from core.output import output_manager

# pytest summary line e.g. "1 passed, 1 failed in 0.25s"
_SUMMARY_RE = re.compile(
    r"(\d+)\s+passed|\s(\d+)\s+failed|\s(\d+)\s+error",
    re.IGNORECASE,
)


class QARunner:

    def __init__(self, workspace_root, python="py"):
        self.workspace = Path(workspace_root)
        self.python = python
        self.qa_root = self.workspace / "Output" / "QA"

    # ------------------------------------------------------------------
    # Static source checks
    # ------------------------------------------------------------------
    def syntax_check(self, file):
        path = Path(file)
        if not path.is_file():
            return {"ok": False, "status": "FAILED", "error": "file not found"}
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source)
            return {"ok": True, "status": "AVAILABLE", "error": None}
        except SyntaxError as exc:
            return {"ok": False, "status": "FAILED", "error": f"SyntaxError line {exc.lineno}: {exc.msg}"}
        except Exception as exc:
            return {"ok": False, "status": "FAILED", "error": repr(exc)}

    def imports_resolve(self, file):
        path = Path(file)
        if not path.is_file():
            return {"ok": False, "status": "FAILED", "error": "file not found"}
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            return {"ok": False, "status": "FAILED",
                    "error": f"syntax error blocks import check: {exc.msg}"}
        missing = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if importlib.util.find_spec(top) is None:
                        missing.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if importlib.util.find_spec(top) is None:
                    missing.append(node.module)
        return {"ok": not missing, "status": "AVAILABLE" if not missing else "FAILED",
                "missing": missing}

    def docstrings_present(self, file):
        path = Path(file)
        ok = True
        findings = []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            return {"ok": False, "status": "FAILED",
                    "error": "file unreadable/unsyntactic"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if not doc and node.name != "__init__":
                    ok = False
                    findings.append(f"function '{node.name}' missing docstring")
        return {"ok": ok, "status": "AVAILABLE" if ok else "FAILED",
                "findings": findings}

    def line_length(self, file, max=100):
        path = Path(file)
        long_lines = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {"ok": False, "status": "FAILED", "error": "file unreadable"}
        for number, line in enumerate(lines, start=1):
            if len(line) > int(max):
                long_lines.append({"line": number, "length": len(line)})
        return {"ok": not long_lines,
                "status": "AVAILABLE" if not long_lines else "FAILED",
                "max": int(max), "violations": long_lines}

    def trailing_whitespace(self, file):
        path = Path(file)
        violations = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {"ok": False, "status": "FAILED", "error": "file unreadable"}
        for number, line in enumerate(lines, start=1):
            if line != line.rstrip():
                violations.append({"line": number})
        return {"ok": not violations,
                "status": "AVAILABLE" if not violations else "FAILED",
                "violations": violations}

    def count_todos(self, directory):
        root = Path(directory)
        total = 0
        per_file = {}
        if root.exists():
            for path in root.rglob("*.py"):
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                count = len(re.findall(r"#\s*TODO", text, re.IGNORECASE))
                if count:
                    per_file[str(path)] = count
                    total += count
        return {"count": total, "files": per_file}

    # ------------------------------------------------------------------
    # pytest runner (honest)
    # ------------------------------------------------------------------
    def run_pytest(self, target="tests/test_<name>.py", timeout=120):
        """Run pytest for a specific target and parse the outcome."""
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = self.workspace / target_path
        if not target_path.exists():
            return {"status": "FAILED", "summary": "target not found",
                    "passed": 0, "failed": 0, "error": "target file not found"}

        command = [self.python, "-m", "pytest", str(target_path), "-q"]
        try:
            proc = subprocess.run(command, capture_output=True, text=True,
                                  timeout=int(timeout))
        except subprocess.TimeoutExpired:
            return {"status": "FAILED", "summary": "timed out",
                    "passed": 0, "failed": 0, "error": "pytest timed out"}
        except Exception as exc:
            return {"status": "FAILED", "summary": "runner error",
                    "passed": 0, "failed": 0, "error": repr(exc)}

        combined = proc.stdout + "\n" + proc.stderr
        passed = failed = errors = 0
        for match in _SUMMARY_RE.finditer(combined):
            if match.group(1):
                passed += int(match.group(1))
            if match.group(2):
                failed += int(match.group(2))
            if match.group(3):
                errors += int(match.group(3))

        clean = proc.returncode == 0
        status = "AVAILABLE" if clean else "FAILED"
        return {
            "status": status,
            "returncode": proc.returncode,
            "summary": combined.strip().splitlines()[-1] if combined.strip() else "",
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "error": None if clean else (proc.stderr.strip()[:2000] or "pytest failed"),
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    def report(self, path):
        """Run QA checks over a target path and write a JSON report to Output/QA."""
        target = Path(path)
        results = {
            "target": str(target),
            "created_at": datetime.now().isoformat(),
            "checks": {},
        }
        checks = {}
        checks["syntax"] = self.syntax_check(target)
        checks["imports"] = self.imports_resolve(target)
        checks["docstrings"] = self.docstrings_present(target)
        checks["line_length"] = self.line_length(target)
        checks["trailing_whitespace"] = self.trailing_whitespace(target)
        checks["todos"] = self.count_todos(target.parent if target.parent.exists() else target)
        results["checks"] = checks

        failed = [name for name, c in checks.items() if not c.get("ok", True)]
        results["overall"] = "PASS" if not failed else "FAIL"
        results["failed_checks"] = failed

        self.qa_root.mkdir(parents=True, exist_ok=True)
        safe = output_manager.safe_filename(target.stem)
        out_path = output_manager.next_rw_path(self.qa_root, f"{safe}_qa", ".json")
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        output_manager.metadata_sidecar(out_path, {"kind": "qa_report", "overall": results["overall"]})
        results["report_path"] = str(out_path)
        return results


__all__ = ["QARunner"]
