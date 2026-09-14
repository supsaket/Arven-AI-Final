"""File management tools.

Safety: create/read/write/search are low/medium; ``delete_file`` /
``delete_folder`` are DESTRUCTIVE (confirmation required, never auto-trusted).

All paths are normalized through ``core.paths`` so users may use folder names
like "downloads" and relative paths.
"""

from pathlib import Path

from core.paths import normalize_path

BASE = Path(__file__).resolve().parent.parent


def _resolve(path):
    return normalize_path(str(path), base_dir=str(BASE))


def create_file(path, content="", **kwargs):
    target = _resolve(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return {"success": False, "action": "create_file",
                    "message": f"{path} already exists — refusing to overwrite."}
        target.write_text(str(content), encoding="utf-8")
        return {"success": True, "action": "create_file",
                "path": str(target), "message": f"Created {path}."}
    except Exception as exc:
        return {"success": False, "action": "create_file", "message": f"create_file error: {exc}"}


def read_file(path, **kwargs):
    target = _resolve(path)
    if not target.exists() or not target.is_file():
        return {"success": False, "action": "read_file",
                "message": f"Could not find {path}."}
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"success": True, "action": "read_file", "path": str(target),
                "content": content[:10000], "content_length": len(content),
                "message": f"Read {path}."}
    except Exception as exc:
        return {"success": False, "action": "read_file", "message": f"read_file error: {exc}"}


def write_file(path, content, **kwargs):
    target = _resolve(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return {"success": True, "action": "write_file", "path": str(target),
                "message": f"Wrote {path}."}
    except Exception as exc:
        return {"success": False, "action": "write_file", "message": f"write_file error: {exc}"}


def append_to_file(path, content, **kwargs):
    target = _resolve(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(str(content))
        return {"success": True, "action": "append_to_file", "path": str(target),
                "message": f"Appended to {path}."}
    except Exception as exc:
        return {"success": False, "action": "append_to_file",
                "message": f"append_to_file error: {exc}"}


def delete_file(path, **kwargs):
    target = _resolve(path)
    if not target.exists():
        return {"success": False, "action": "delete_file",
                "message": f"Could not find {path}."}
    try:
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        return {"success": True, "action": "delete_file", "path": str(target),
                "message": f"Deleted {path}."}
    except Exception as exc:
        return {"success": False, "action": "delete_file", "message": f"delete_file error: {exc}"}


def delete_folder(path, **kwargs):
    import shutil
    target = _resolve(path)
    if not target.exists():
        return {"success": False, "action": "delete_folder",
                "message": f"Could not find {path}."}
    try:
        shutil.rmtree(target)
        return {"success": True, "action": "delete_folder", "path": str(target),
                "message": f"Deleted folder {path}."}
    except Exception as exc:
        return {"success": False, "action": "delete_folder",
                "message": f"delete_folder error: {exc}"}


def list_files(path="", **kwargs):
    directory = _resolve(path or "")
    if not directory.exists():
        return {"success": False, "action": "list_files",
                "message": f"Could not find {path or 'current directory'}."}
    try:
        entries = sorted(
            ({"name": e.name, "is_dir": e.is_dir(), "size": e.stat().st_size
              if e.is_file() else None}
             for e in directory.iterdir()),
            key=lambda e: (not e["is_dir"], e["name"].lower()),
        )
        return {"success": True, "action": "list_files", "path": str(directory),
                "entries": entries, "count": len(entries),
                "message": f"Listed {len(entries)} entries in {path or '.':s}."}
    except Exception as exc:
        return {"success": False, "action": "list_files", "message": f"list_files error: {exc}"}


def search_files(query, path="", **kwargs):
    directory = _resolve(path or "")
    if not directory.exists():
        return {"success": False, "action": "search_files",
                "message": f"Could not find {path or 'current directory'}."}
    needle = str(query).lower()
    matches = []
    try:
        for root, _, files in os.walk(str(directory)):
            for name in files:
                if needle in name.lower():
                    matches.append(str(Path(root) / name))
                if len(matches) >= 100:
                    break
            if len(matches) >= 100:
                break
    except Exception as exc:
        return {"success": False, "action": "search_files", "message": f"search_files error: {exc}"}
    return {"success": True, "action": "search_files", "query": query,
            "matches": matches, "count": len(matches), "message": f"Found {len(matches)} matches."}


import os  # noqa: E402

TOOLS = [
    {"name": "create_file", "function": create_file, "category": "File", "backend": "local",
     "risk": "medium",
     "parameters": [{"name": "path", "required": True, "hint": "str"},
                    {"name": "content", "required": False, "hint": "str"}]},
    {"name": "read_file", "function": read_file, "category": "File", "backend": "local",
     "risk": "low", "parameters": [{"name": "path", "required": True, "hint": "str"}]},
    {"name": "write_file", "function": write_file, "category": "File", "backend": "local",
     "risk": "medium",
     "parameters": [{"name": "path", "required": True, "hint": "str"},
                    {"name": "content", "required": True, "hint": "str"}]},
    {"name": "append_to_file", "function": append_to_file, "category": "File", "backend": "local",
     "risk": "medium",
     "parameters": [{"name": "path", "required": True, "hint": "str"},
                    {"name": "content", "required": True, "hint": "str"}]},
    {"name": "delete_file", "function": delete_file, "category": "File", "backend": "local",
     "risk": "destructive", "parameters": [{"name": "path", "required": True, "hint": "str"}]},
    {"name": "delete_folder", "function": delete_folder, "category": "File", "backend": "local",
     "risk": "destructive", "parameters": [{"name": "path", "required": True, "hint": "str"}]},
    {"name": "list_files", "function": list_files, "category": "File", "backend": "local",
     "risk": "low",
     "parameters": [{"name": "path", "required": False, "hint": "str"}]},
    {"name": "search_files", "function": search_files, "category": "File", "backend": "local",
     "risk": "low",
     "parameters": [{"name": "query", "required": True, "hint": "str"},
                    {"name": "path", "required": False, "hint": "str"}]},
]