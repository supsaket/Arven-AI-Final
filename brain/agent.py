"""Agent — command parsing and multi-action planning (row 05).

* splits multi-action requests ("open notepad and calculator and youtube")
  without duplicating a repeated verb
* parses create-file / create-folder commands and resolves desktop/downloads
  locations through the real known-folders helper
* instantiates and uses the ContextReferenceManager for "it/that" targets
"""

import re

from core.paths import _known_folder, normalize_path
from core.reference import ContextReferenceManager
from core.upgrade import strip_arven_prefix

VERBS = ["open", "close", "launch", "start", "run", "execute", "search",
         "create", "delete", "move", "copy", "rename", "read", "write"]

_FOLDER_LOCATIONS = {
    "desktop": lambda: _known_folder("DESKTOP"),
    "downloads": lambda: _known_folder("DOWNLOADS"),
    "documents": lambda: _known_folder("DOCUMENTS"),
}


class ActionParser:

    def __init__(self):
        self.refs = ContextReferenceManager()

    # ------------------------------------------------------------------
    def split_actions(self, request):
        """Return a list of distinct commands (no repeated-verb duplicates)."""
        text = strip_arven_prefix(request)
        parts = [p.strip() for p in re.split(r"\band\b|,", text) if p.strip()]
        actions = []
        pending_verb = None

        for part in parts:
            lower = part.lower()
            first = lower.split(" ", 1)[0] if " " in lower else lower
            if first in VERBS:
                pending_verb = first
                actions.append(part)
                continue
            if pending_verb and actions and (first not in VERBS):
                # "notepad" after "open notepad and calculator" -> inherit verb,
                # but never duplicate the head command.
                if not actions[-1].lower().strip().endswith(part.lower().strip()):
                    actions.append(f"{pending_verb} {part}")
                continue
            actions.append(part)

        seen = set()
        unique = []
        for action in actions:
            key = re.sub(r"\s+", " ", action.lower().strip())
            if key not in seen:
                seen.add(key)
                unique.append(action.strip())
        return [u for u in unique if u]

    # ------------------------------------------------------------------
    def parse_create(self, request):
        """parse 'create file X' / 'create folder Y {on desktop|in downloads}'."""
        text = strip_arven_prefix(request).strip()
        lowered = text.lower()
        rest = None
        if lowered.startswith(("create ", "make ")):
            rest = text[len(lowered.split()[0]):].strip()
        if rest is None:
            return None
        location = ""
        for loc in ("on desktop", "on the desktop", "in downloads",
                    "in the downloads", "in documents", "in the documents"):
            if loc in rest.lower():
                location = loc.split()[-1]
                rest = re.sub(loc, "", rest, flags=re.IGNORECASE).strip()
                break
        if rest.lower().startswith(("folder ", "file ")):
            kind, name = rest.split(" ", 1)
            kind = kind.lower()
        else:
            kind, name = "file", rest
        name = name.strip().strip("'\"")
        return {"kind": kind, "target": name, "location": location}

    def resolve_location(self, parsed):
        """Resolve the location token to an absolute path when provided."""
        location = parsed.get("location")
        if location and location in _FOLDER_LOCATIONS:
            return str(_FOLDER_LOCATIONS[location]())
        if parsed.get("location") == "desktop":
            return str(_known_folder("DESKTOP"))
        return None

    def parse_create_folder(self, request):
        parsed = self.parse_create(request)
        if parsed and parsed["kind"] == "folder":
            return parsed
        if parsed and parsed["kind"] == "file":
            return None
        return parsed if parsed else None


class Agent:

    def __init__(self):
        self.parser = ActionParser()

    def plan(self, request):
        """Return the list of low-level actions to execute."""
        parsed = self.parser.parse_create(request)
        if parsed is not None:
            return [self._create_command(parsed)]
        return self.parser.split_actions(request)

    def _create_command(self, parsed):
        verb = "create_folder" if parsed["kind"] == "folder" else "create_file"
        return f"{verb} {parsed['target']}"


agent = Agent()

__all__ = ["Agent", "ActionParser", "agent"]