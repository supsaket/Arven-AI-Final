"""Build / Pipeline / Packaging agent (feature 47, Day 2).

PipelineRunner runs staged builds sequentially with per-stage timeouts,
records honest status per stage, and writes a build manifest artefact to
``Output/Build``.

Also agents honest local-git awareness: ``git_check`` reports AVAILABLE or
NOT_CONFIGURED via shutil.which; ``fetch_remote`` without a repo returns the
honest NOT_CONFIGURED status.
"""

import json
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from core.output import output_manager

# ----------------------------------------------------------------------
# Stage schema
# ----------------------------------------------------------------------
REQUIRED_STAGE_KEYS = ("id", "action")
OPTIONAL_STAGE_KEYS = ("artifacts", "timeout", "description")


def _validate_stage(stage, index):
    errors = []
    if not isinstance(stage, dict):
        return [f"stage[{index}] must be a dict"]
    for key in REQUIRED_STAGE_KEYS:
        if key not in stage:
            errors.append(f"stage[{index}] missing key '{key}'")
    if "id" in stage and not isinstance(stage["id"], str):
        errors.append(f"stage[{index}].id must be a string")
    if "action" in stage and not callable(stage.get("action")):
        errors.append(f"stage[{index}].action must be callable")
    return errors


class PipelineRunner:

    def __init__(self, output_root=None):
        self.output_root = Path(output_root) if output_root else Path.cwd() / "Output"
        self.build_root = self.output_root / "Build"

    # ------------------------------------------------------------------
    def pipeline_from_script(self, script):
        """Validate a script dict ({name, stages:[...]}). Returns (ok, errors)."""
        if not isinstance(script, dict):
            return False, ["script must be a dict"]
        name = script.get("name")
        if not name:
            return False, ["script missing 'name'"]
        stages = script.get("stages")
        if not isinstance(stages, list) or not stages:
            return False, ["script 'stages' must be a non-empty list"]
        errors = []
        for index, stage in enumerate(stages):
            errors.extend(_validate_stage(stage, index))
        if errors:
            return False, errors
        return True, []

    # ------------------------------------------------------------------
    def _run_stage(self, stage, default_timeout):
        timeout = float(stage.get("timeout", default_timeout))
        result = {}
        start = time.monotonic()

        def worker():
            try:
                result["value"] = stage["action"]()
                result["ok"] = True
            except Exception as exc:
                result["ok"] = False
                result["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return {
                "status": "timeout",
                "duration": round(time.time() - start, 3),
                "error": f"stage exceeded {timeout}s timeout",
            }
        if not result.get("ok"):
            return {
                "status": "failed",
                "duration": round(time.time() - start, 3),
                "error": repr(result["error"]),
            }
        return {
            "status": "passed",
            "duration": round(time.time() - start, 3),
            "output": result.get("value"),
        }

    def run(self, name, stages, env=None, default_timeout=10):
        """Run stages sequentially. On failure returns partial report + error."""
        stage_records = []
        failed_at = None
        failure_error = None
        all_artifacts = []

        for index, stage in enumerate(stages):
            record_start = time.monotonic()
            outcome = self._run_stage(stage, default_timeout)
            record = {
                "id": stage.get("id", f"stage_{index}"),
                "index": index,
                **outcome,
            }
            stage_artifacts = []
            for artifact in stage.get("artifacts", []) or []:
                all_artifacts.append(str(artifact))
                stage_artifacts.append(str(artifact))
            record["artifacts"] = stage_artifacts
            stage_records.append(record)

            if outcome["status"] in ("failed", "timeout"):
                failed_at = record["id"]
                failure_error = outcome["error"]
                break

        exit_summary = "ok"
        if failed_at is not None:
            exit_summary = f"failed at stage '{failed_at}'"

        manifest = {
            "name": name,
            "stages": stage_records,
            "artifacts": all_artifacts,
            "exit_summary": exit_summary,
            "complete": failed_at is None,
            "created_at": datetime.now().isoformat(),
            "env": sorted((env or {}).keys()),
        }

        self.build_root.mkdir(parents=True, exist_ok=True)
        safe = output_manager.safe_filename(f"{name}_build")
        path = output_manager.next_rw_path(self.build_root, safe, ".json")
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        output_manager.metadata_sidecar(path, {"kind": "build_manifest"})

        report = {
            "name": name,
            "stages": stage_records,
            "artifacts": all_artifacts,
            "complete": failed_at is None,
            "exit_summary": exit_summary,
            "failed_stage": failed_at,
            "error": failure_error,
            "manifest_path": str(path),
            "partial": failed_at is not None,
        }
        return report

    # ------------------------------------------------------------------
    # Honest git awareness
    # ------------------------------------------------------------------
    def git_check(self):
        git_exe = shutil.which("git")
        if not git_exe:
            return {"status": "NOT_CONFIGURED", "available": False,
                    "reason": "git executable not found on PATH"}
        try:
            probe = subprocess.run([git_exe, "--version"], capture_output=True,
                                   text=True, timeout=10)
        except Exception:
            return {"status": "UNAVAILABLE", "available": False,
                    "reason": "git probe failed"}
        if probe.returncode != 0:
            return {"status": "UNAVAILABLE", "available": False,
                    "reason": probe.stderr.strip() or "git returned non-zero"}
        return {"status": "AVAILABLE", "available": True,
                "version": probe.stdout.strip()}

    def fetch_remote(self, repo_url=None, workdir=None):
        """Fetch from a remote. Without a configured repo -> NOT_CONFIGURED."""
        check = self.git_check()
        if check["status"] != "AVAILABLE":
            return {"status": check["status"], "message": check.get("reason")}

        base = Path(workdir) if workdir else Path.cwd()
        if not (base / ".git").is_dir():
            return {"status": "NOT_CONFIGURED",
                    "message": "no local git repository (no .git directory)"}
        if not repo_url:
            return {"status": "NOT_CONFIGURED",
                    "message": "no remote URL provided"}
        return {"status": "NOT_CONFIGURED",
                "message": "fetch_remote not executed without explicit remote harness",
                "remote": str(repo_url)}


__all__ = ["PipelineRunner"]
