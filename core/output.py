"""Output management — safe, collision-free artefact writing.

* ``safe_filename`` sanitises names for the filesystem
* ``next_rw_path`` returns a fresh path without overwriting anything
* metadata sidecar (``.json``) records provenance next to every artefact
* ``structured_records`` journal of produced artefacts
* ``cleanup`` removes ONLY old files matching criteria (never everything)
* supported directories keep writes inside organised folders
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
_SUPPORTED_DIRS = ["output", "Output", "reports", "logs", "Logs", "screenshots", "Screenshots"]


def _dir_root(label):
    return Path(label) if Path(label).is_absolute() else BASE / label


class OutputManager:

    def __init__(self, root=None):
        self.root = Path(root) if root else BASE

    # ------------------------------------------------------------------
    def safe_filename(self, name):
        cleaned = str(name).strip().replace(" ", "_")
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", cleaned)
        cleaned = cleaned.strip(". ")
        return cleaned or "unnamed"

    def unique_filenames(self, directory, basename, count=2, suffix=""):
        names = []
        used = set()
        for _ in range(max(1, int(count))):
            name = self._next_name(directory, basename, suffix, used)
            used.add(name)
            names.append(name)
        return names

    def _next_name(self, directory, basename, suffix, used=None):
        used = used or set()
        base = self.safe_filename(basename)
        candidate = base + suffix
        index = 2
        while candidate in used or (Path(directory) / candidate).exists():
            candidate = f"{base}_{index}{suffix}"
            index += 1
        return candidate

    def next_rw_path(self, directory, basename, suffix="", overwrite=False):
        """Return a Path that is safe to write. Never overwrites by default."""
        directory = Path(directory)
        if overwrite:
            return directory / (self.safe_filename(basename) + suffix)
        name = self._next_name(directory, basename, suffix)
        return directory / name

    # ------------------------------------------------------------------
    def supported_directories(self):
        return list(_SUPPORTED_DIRS)

    def _ensure(self, directory):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def metadata_sidecar(self, target_path, extra=None):
        data = {
            "filename": Path(target_path).name,
            "created_at": datetime.now().isoformat(),
            "type": "ARVEN_OUTPUT",
            **(extra or {}),
        }
        sidecar = Path(target_path).with_suffix(Path(target_path).suffix + ".json")
        sidecar.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(sidecar)

    def write(self, directory, filename, content, overwrite=False, metadata=None):
        directory = self._ensure(directory)
        path = self.next_rw_path(directory, filename, "", overwrite=overwrite)
        encoding = "utf-8"
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding=encoding)
        sidecar = self.metadata_sidecar(path, metadata)
        return {"path": str(path), "sidecar": sidecar}

    def structured_records(self):
        """Journal of artefacts produced in this session."""
        records = []
        for label in ("Output", "Logs", "Screenshots"):
            directory = self.root / label
            if not directory.exists():
                continue
            for path in directory.glob("*"):
                if path.is_file():
                    records.append({
                        "name": path.name,
                        "path": str(path),
                        "size": path.stat().st_size,
                    })
        records.sort(key=lambda r: r["name"].lower())
        return records

    # ------------------------------------------------------------------
    def cleanup(self, directory, max_age_seconds=None, limit=None, criteria=None):
        """Remove ONLY files that match an explicit criteria."""
        directory = self._ensure(directory)
        removed = []
        now = time.time()
        for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime):
            if not path.is_file():
                continue
            keep = True
            if max_age_seconds is not None:
                keep = (now - path.stat().st_mtime) <= float(max_age_seconds)
            if criteria is not None:
                keep = keep and bool(criteria(path))
            if not keep:
                path.unlink()
                removed.append(str(path))
                if limit is not None and len(removed) >= int(limit):
                    break
        return removed


output_manager = OutputManager()

__all__ = ["OutputManager", "output_manager", "safe_filename"]