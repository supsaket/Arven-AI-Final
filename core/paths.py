"""Central path normalization for ARVEN.

The ActionEngine resolves every user-supplied target through
:func:`normalize_path` so open/create/rename/copy/move commands agree on one
definition of a path. Kept intentionally free of heavy imports so any module
can call it.
"""

import os
import re
from pathlib import Path

_KNOWN_FOLDERS = {
    "desktop": "DESKTOP",
    "documents": "DOCUMENTS",
    "downloads": "DOWNLOADS",
    "pictures": "PICTURES",
    "music": "MUSIC",
    "videos": "VIDEOS",
}


def _known_folder(name):
    """Resolve a well-known Windows user-folder name to an absolute path."""
    try:
        import ctypes.wintypes
        from ctypes import windll, wintypes

        csidl = {
            "DESKTOP": 0x0000,
            "DOCUMENTS": 0x0005,
            "DOWNLOADS": 0x000C,
            "PICTURES": 0x0027,
            "MUSIC": 0x000D,
            "VIDEOS": 0x000E,
        }[name.upper()]

        buf = wintypes.create_unicode_buffer(260)
        if windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf):
            raise OSError("SHGetFolderPathW failed")
        return Path(buf.value)
    except Exception:
        try:
            return Path(os.environ.get("USERPROFILE", Path.home())) / name.lower()
        except Exception:
            return Path.home() / name


def normalize_path(value, base_dir=None):
    """Return an absolute ``Path`` for ``value``.

    Rules (in order):

    * ``~`` and ``%USERPROFILE%`` references are expanded.
    * A bare well-known folder name (``desktop``, ``downloads``, ``documents``,
      ``pictures``, ``music``, ``videos``) resolves to the real shell folder.
    * An absolute path (drive letter or UNC or rooted) is used as-is.
    * Anything else is resolved relative to ``base_dir`` (default: ARVEN root).
    * Path traversal outside ``base_dir`` for relative inputs is rejected.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    base = base.resolve()

    if value is None:
        raise ValueError("normalize_path requires a value")

    text = str(value).strip()
    if not text:
        raise ValueError("normalize_path requires a non-empty value")

    text = os.path.expandvars(os.path.expanduser(text))

    parts = text.split(os.sep if os.sep in text else "/")
    first = parts[0] if parts else ""

    if len(parts) == 1 and first.lower() in _KNOWN_FOLDERS:
        return _known_folder(first.lower()).resolve()

    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()

    candidate = base / text
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate.absolute()
    if resolved != base and base not in resolved.parents:
        raise ValueError(
            f"Path '{text}' escapes the base directory and is not allowed"
        )
    return resolved