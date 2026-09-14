"""Backups & Data Protection (feature 61, Day 2).

BackupManager owns snapshot creation, integrity verification, archive-only
rotation, and gated restore.

Safety contract:
* ``snapshot`` copies real files (never moves/deletes source data).
* ``rotate`` ARCHIVES old snapshots into ``Backups/_archive`` — it NEVER
  deletes anything.
* ``restore`` is gated by ``CONFIRMATION.gate`` and always writes into an
  explicit ``target_dir``; it never writes over the live store silently.
* ``classify_path`` buckets a path into data/ vs Output/ vs config vs other
  using the ``safety_bag`` classification table.
"""

import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from core.confirmation import CONFIRMATION

# ----------------------------------------------------------------------
# Safety classification table (bucket -> sample path fragments).
# ----------------------------------------------------------------------
SAFETY_BAG = {
    "data": ("data",),
    "output": ("Output", "output", "reports", "logs"),
    "config": ("config", ".config", "settings", "opencode", "arven_gui"),
    "other": (),
}


def _bucket_for(relpath):
    parts = [p.lower() for p in Path(relpath).parts]
    for bucket, seeds in SAFETY_BAG.items():
        for seed in seeds:
            if any(seed in part for part in parts):
                return bucket
    return "other"


def classify_path(path):
    """Classify a path into a safety bucket (data / output / config / other)."""
    return {"bucket": _bucket_for(str(path)), "path": str(path)}


def _sha256(filepath, chunk=65536):
    digest = hashlib.sha256()
    with open(filepath, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class BackupManager:

    def __init__(self, workspace_root, output_root):
        self.workspace = Path(workspace_root)
        self.output_root = Path(output_root)
        self.backup_root = self.workspace / "Backups"
        self.data_root = self.workspace / "data"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _source_files(self):
        """Yield all critical files: workspace data/ + output artefacts."""
        files = []
        roots = []
        if self.data_root.exists():
            roots.append(self.data_root)
        if self.output_root.exists():
            roots.append(self.output_root)
        for root in roots:
            for path in root.rglob("*"):
                if path.is_file():
                    files.append(path)
        return files

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------
    def snapshot(self, label):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^A-Za-z0-9_\-]", "_", str(label)) or "backup"
        snap_dir = self.backup_root / f"{timestamp}_{safe_label}"
        snap_dir.mkdir(parents=True, exist_ok=True)

        copied = []
        manifest_entries = {}
        for source in self._source_files():
            rel = source.relative_to(self.workspace if
                                     str(source).startswith(str(self.workspace))
                                     else source.parent.parent)
            dest = snap_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            copied.append(str(rel))
            manifest_entries[str(rel)] = {"sha256": _sha256(dest), "size": dest.stat().st_size}

        manifest = {
            "id": snap_dir.name,
            "label": safe_label,
            "created_at": datetime.now().isoformat(),
            "files": manifest_entries,
            "count": len(manifest_entries),
        }
        manifest_path = snap_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return {
            "id": snap_dir.name,
            "path": str(snap_dir),
            "label": safe_label,
            "files": copied,
            "count": len(copied),
            "manifest": str(manifest_path),
        }

    # ------------------------------------------------------------------
    # Listing & verification
    # ------------------------------------------------------------------
    def list_snapshots(self):
        if not self.backup_root.exists():
            return []
        snapshots = []
        for entry in sorted(self.backup_root.iterdir()):
            if entry.is_dir() and entry.name != "_archive" and (entry / "manifest.json").exists():
                snapshots.append({
                    "id": entry.name,
                    "path": str(entry),
                    "created_at": entry.stat().st_mtime,
                })
        return snapshots

    def _snapshot_dir(self, snap_id):
        if not snap_id or (".." in str(snap_id)) or os.path.isabs(str(snap_id)):
            return None
        candidate = self.backup_root / snap_id
        if candidate.is_dir() and (candidate / "manifest.json").exists():
            return candidate
        return None

    def verify(self, snap_id):
        snap_dir = self._snapshot_dir(snap_id)
        if snap_dir is None:
            return {"status": "FAILED", "id": snap_id,
                    "message": "snapshot not found", "verified": False}
        try:
            manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"status": "FAILED", "id": snap_id,
                    "message": "manifest unreadable", "verified": False}

        all_ok = True
        mismatches = []
        for rel, meta in manifest.get("files", {}).items():
            target = snap_dir / rel
            if not target.is_file():
                all_ok = False
                mismatches.append({"file": rel, "error": "missing"})
                continue
            actual = _sha256(target)
            if actual != meta.get("sha256"):
                all_ok = False
                mismatches.append({"file": rel, "error": "checksum_mismatch"})

        return {
            "status": "AVAILABLE" if all_ok else "FAILED",
            "id": snap_id,
            "verified": all_ok,
            "files": len(manifest.get("files", {})),
            "mismatches": mismatches,
        }

    # ------------------------------------------------------------------
    # Rotation (archive, never delete)
    # ------------------------------------------------------------------
    def rotate(self, keep=3):
        snapshots = self.list_snapshots()
        # order by creation time (oldest first) regardless of label ordering
        snapshots = sorted(snapshots, key=lambda s: s.get("created_at", 0))
        if len(snapshots) <= int(keep):
            return {"archived": [], "kept": [s["id"] for s in snapshots],
                    "note": "no rotation needed"}

        archive_root = self.backup_root / "_archive"
        excess = snapshots[:len(snapshots) - int(keep)]  # oldest first
        archived = []
        for snap in excess:
            dest = archive_root / snap["id"]
            if dest.exists():
                continue
            shutil.move(snap["path"], str(dest))
            archived.append(snap["id"])

        kept = [s["id"] for s in self.list_snapshots()]
        return {"archived": archived, "kept": kept, "note": "archived (not deleted)"}

    # ------------------------------------------------------------------
    # Restore (gated, into target dir only)
    # ------------------------------------------------------------------
    def restore(self, snap_id, target_dir, confirmed=False, trusted=False,
                request_id=None):
        """Restore a snapshot into an explicit target directory.

        Gated: requires CONFIRMATION approval for this action. Restoration
        always writes into ``target_dir``; it never writes over the live
        data store silently.
        """
        # Dangerous restore requires explicit confirmation — never silent.
        if not confirmed:
            return {"status": "FAILED", "restored": False,
                    "message": "restore refuses: confirmation required before restoring"}
        allowed, reason = CONFIRMATION.gate(
            "restore_backup", confirmed=confirmed, trusted=trusted,
            request_id=request_id)
        if not allowed:
            return {"status": "FAILED", "restored": False,
                    "message": f"restore refused: {reason}"}

        snap_dir = self._snapshot_dir(snap_id)
        if snap_dir is None:
            return {"status": "FAILED", "restored": False,
                    "message": "snapshot not found"}

        verify = self.verify(snap_id)
        if not verify["verified"]:
            return {"status": "FAILED", "restored": False,
                    "message": "snapshot integrity check failed — refusing restore"}

        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
        restored = []
        for rel in manifest.get("files", {}):
            src = snap_dir / rel
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            restored.append(str(rel))

        return {"status": "AVAILABLE", "restored": True, "count": len(restored),
                "target": str(target), "id": snap_id}


__all__ = ["BackupManager", "classify_path", "SAFETY_BAG"]
