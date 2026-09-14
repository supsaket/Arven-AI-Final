"""Multi-step planning and execution (row 05 / 37).

* ``plan_steps`` top-level split: commas first, then " and " between verbs;
  subfolder/path lists ("src and tests") are never split.
* ``MultiStepRunner`` executes steps through the ToolRegistry, stopping the
  chain on hard failure or continuing with partial-failure reports.
"""

import re

from brain.intent import detect
from core.reference import context_refs
from core.upgrade import strip_arven_prefix

_VERB_STARTERS = {"open", "close", "create", "delete", "move", "copy", "rename",
                  "read", "write", "search", "run", "start", "launch", "list"}


def _split_and(part):
    """Split a part on ' and ' ONLY when it joins two actions (verb follows).

    Subfolder/path lists ("src and tests", "a and b inside c") stay intact.
    """
    lower = part.lower()
    segments = []
    last = 0
    i = 0
    while True:
        idx = lower.find(" and ", i)
        if idx == -1:
            break
        after = part[idx + 5:].strip()
        first_after = after.split(" ", 1)[0].lower()
        is_boundary = bool(first_after) and first_after in _VERB_STARTERS
        if is_boundary:
            segments.append(part[last:idx])
            last = idx + 5
            i = idx + 5
        else:
            i = idx + 4
    segments.append(part[last:])
    return [s.strip() for s in segments if s.strip()]


def plan_steps(request):
    """Split a request into an ordered list of step strings."""
    text = strip_arven_prefix(request)
    if not text.strip():
        return []

    # Split on commas first (each comma part is a distinct step boundary).
    comma_parts = [p.strip() for p in re.split(r",", text) if p.strip()]
    steps = []
    for part in comma_parts:
        steps.extend(_split_and(part))
    return [s for s in steps if s.strip()]


def _is_path_token(token):
    """'src and tests' style lists are not separate actions."""
    lowered = token.lower()
    return bool(re.match(r"^[a-z0-9_\-\\./ ]+$", lowered)) and \
        not lowered.split()[0] in _VERB_STARTERS if " " in lowered else True


def looks_like_step_start(token):
    first = str(token).strip().lower().split(" ", 1)[0]
    return first in _VERB_STARTERS


class MultiStepRunner:

    def __init__(self, registry=None, refs=None):
        from tools.builder import get_registry
        self.registry = registry or get_registry()
        self.refs = refs or context_refs

    # ------------------------------------------------------------------
    def run(self, request, stop_on_failure=True, confirmed=False):
        steps = plan_steps(request)
        results = []
        failure = None
        for index, step in enumerate(steps, start=1):
            result = self._execute_step(step, confirmed=confirmed)
            results.append({"step": step, "index": index, "result": result})
            if not result.get("success", False):
                failure = result
                if stop_on_failure:
                    break
        if failure and stop_on_failure:
            return {"success": False, "steps": steps, "results": results,
                    "failed_step": step, "message": failure.get("message", "step failed")}
        return {"success": not any(r["result"].get("success") is False
                                   for r in results),
                "steps": steps, "results": results,
                "message": "Executed all steps."}

    def _execute_step(self, step, confirmed=False):
        tool_name, payload = self._parse_step(step)
        if tool_name is None:
            return {"success": False, "action": step,
                    "message": f"Unsupported step: {step}"}
        return self.registry.invoke(tool_name, confirmed=confirmed, **payload)

    def _parse_step(self, step):
        lowered = step.lower().strip()
        # create folder <path> (possibly with subfolders)
        match = re.match(r"^create\s+(?:a\s+)?folder\s+(.+)$", lowered)
        if match:
            return "create_folder", {"path": match.group(1).strip()}
        match = re.match(r"^create\s+(?:a\s+)?file\s+(.+)$", lowered)
        if match:
            return "create_file", {"path": match.group(1).strip()}
        match = re.match(r"^write\s+(?:to\s+)?(.+)$", lowered)
        if match:
            return "write_file", {"path": match.group(1).strip()}
        match = re.match(r"^read\s+(?:file\s+)?(.+)$", lowered)
        if match:
            return "read_file", {"path": match.group(1).strip()}
        match = re.match(r"^open\s+(.+)$", lowered)
        if match:
            return "open_app", {"app": match.group(1).strip()}
        match = re.match(r"^rename\s+(.+)$", lowered)
        if match:
            return None  # needs options; handled by rename parser
        return None, None


__all__ = ["MultiStepRunner", "plan_steps"]