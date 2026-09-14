"""Day 3 lifecycle state tracker — machine-readable, evidence-backed.

Writes ``day3_state.json`` at the repository root. States follow the exact
Day-3 state machine:

TO_ADD -> WORK -> IN_PROGRESS -> WORK -> USABLE -> TEST -> STRONG
        -> COMPLETE -> FINAL

Allowed forward transitions; any state after IN_PROGRESS may return to WORK
when defects are found. TIMESTAMPS ARE NEVER FABRICATED: start/end markers are
written only at the moment the transition command runs.

Usage:

    python day3_lifecycle.py init
    python day3_lifecycle.py advance T1 WORK "message"
    python day3_lifecycle.py link T1 "core/terminal_engine.py" "evidence"
    python day3_lifecycle.py show
    python day3_lifecycle.py verify
"""

import json
import sys
from datetime import datetime

_STATE_FILE = "day3_state.json"

_ORDER = [
    "TO_ADD", "WORK", "IN_PROGRESS", "WORK", "USABLE",
    "TEST", "STRONG", "COMPLETE", "FINAL",
]

_DEFAULTS = [
    ("T1", "Terminal Command Chain & Orchestration", "51/58/89"),
    ("T2", "Planner -> Registry Execution & Replan", "74"),
    ("T3", "Mission <-> Gated Tool Execution", "50/54"),
    ("T4", "Event Response End-to-End Hardening", "92"),
    ("T5", "Undo / Transaction Recovery Hardening", "102"),
    ("T6", "Cyber Authorization & File-Audit Fix", "60"),
    ("T7", "Backup Integrity & Restore Refusal", "61"),
    ("T8", "Terminal CLI + Restored Text Entry", "51/58/89"),
    ("T9", "Cross-Cutting Test Suite + Tracker", "architecture"),
]


def _now():
    return datetime.now().isoformat()


def index_of(state):
    if state not in _ORDER:
        raise ValueError(f"unknown lifecycle state {state}")
    return _ORDER.index(state)


def _load():
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"created_at": None, "targets": {}}


def _save(document):
    with open(_STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
    return True


def blank_target(target_id, name, features):
    return {
        "feature": target_id,
        "name": name,
        "features": features,
        "state": "TO_ADD",
        "started_at": None,
        "updated_at": None,
        "implementation": [],
        "tests": [],
        "failures": [],
        "evidence": [],
        "limitations": [],
        "finalized_at": None,
    }


def init():
    document = {"created_at": _now(), "targets": {}}
    for target_id, name, features in _DEFAULTS:
        document["targets"][target_id] = blank_target(
            target_id, name, features)
        document["targets"][target_id]["started_at"] = _now()
        document["targets"][target_id]["updated_at"] = _now()
    _save(document)
    return document


def advance(target_id, state, message=""):
    document = _load()
    targets = document.setdefault("targets", {})
    target = targets.get(target_id)
    if target is None:
        raise ValueError(f"unknown target {target_id}")
    current = target["state"]
    allowed = True
    if targets.get(target_id, {}).get("state", "TO_ADD") == "FINAL":
        raise ValueError(f"{target_id} is FINAL — changes need a new cycle")
    if current == state:
        pass
    elif current == "TO_ADD" and state == "WORK":
        pass
    elif current in ("IN_PROGRESS", "USABLE", "TEST", "STRONG",
                     "COMPLETE", "WORK") and state in ("WORK", "IN_PROGRESS",
                                                       "USABLE", "TEST",
                                                       "STRONG", "COMPLETE",
                                                       "FINAL"):
        # Allowed when the new state is strictly forward OR a documented
        # failure bounce back to WORK / IN_PROGRESS.
        if state in ("WORK", "IN_PROGRESS"):
            allowed = current != "WORK" or state == "IN_PROGRESS"
        else:
            allowed = index_of(state) > index_of(current)
    else:
        allowed = False
    if not allowed:
        raise ValueError(
            f"illegal transition {target_id}: {current} -> {state}")
    target["state"] = state
    target["updated_at"] = _now()
    if state == "FINAL":
        target["finalized_at"] = _now()
    if message:
        target["failures"].append({"state": state, "at": _now(),
                                   "note": message})
    _save(document)
    return target


def link(target_id, what, kind="evidence"):
    document = _load()
    target = document["targets"].get(target_id)
    if target is None:
        raise ValueError(f"unknown target {target_id}")
    key = "evidence" if kind == "evidence" else "tests"
    bucket = target.setdefault(key, [])
    for existing in bucket:
        if existing.get("path") == what:
            return existing              # path-level dedupe
    entry = {"path": what, "at": _now()}
    bucket.append(entry)
    target["updated_at"] = _now()
    _save(document)
    return entry


def record_failure(target_id, note):
    document = _load()
    target = document["targets"].get(target_id)
    if target is None:
        raise ValueError(f"unknown target {target_id}")
    target["failures"].append({"state": target["state"], "at": _now(),
                               "note": note})
    target["updated_at"] = _now()
    _save(document)
    return True


def record_limitation(target_id, note):
    document = _load()
    target = document["targets"].get(target_id)
    if target is None:
        raise ValueError(f"unknown target {target_id}")
    entry = {"note": note, "at": _now()}
    if entry not in target["limitations"]:
        target["limitations"].append(entry)
    _save(document)
    return True


def verify():
    document = _load()
    errors = []
    for target_id, target in document.get("targets", {}).items():
        state = target.get("state")
        if state not in _ORDER:
            errors.append(f"{target_id}: bad state {state}")
        started = target.get("started_at")
        updated = target.get("updated_at")
        if not started or not updated:
            errors.append(f"{target_id}: missing timestamps")
        if state == "FINAL" and not target.get("finalized_at"):
            errors.append(f"{target_id}: FINAL without finalized_at")
    return {"valid": not errors, "errors": errors,
            "targets": len(document.get("targets", {}))}


def show():
    document = _load()
    print(f"Day 3 state  (created {document.get('created_at')})")
    for target_id, target in document.get("targets", {}).items():
        print(
            f"  {target_id:<3} {target['state']:<12} "
            f"{target['name']} (features {target['features']}) "
            f"evidence={len(target.get('evidence', []))} "
            f"tests={len(target.get('tests', []))} "
            f"failures={len(target.get('failures', []))}"
        )
    return document


def main(argv):
    if not argv:
        show()
        return 0
    command = argv[0]
    if command == "init":
        init()
        print("day3_state.json initialized")
    elif command == "advance":
        target_id, state = argv[1], argv[2]
        message = argv[3] if len(argv) > 3 else ""
        advance(target_id, state, message)
        print(f"{target_id} -> {state}")
    elif command == "link":
        target_id, what = argv[1], argv[2]
        kind = argv[3] if len(argv) > 3 else "evidence"
        link(target_id, what, kind)
        print(f"linked {kind}: {what}")
    elif command == "failure":
        target_id, note = argv[1], argv[2]
        record_failure(target_id, note)
        print(f"recorded failure for {target_id}")
    elif command == "limitation":
        target_id, note = argv[1], argv[2]
        record_limitation(target_id, note)
        print(f"recorded limitation for {target_id}")
    elif command == "verify":
        result = verify()
        print(json.dumps(result))
        return 0 if result["valid"] else 1
    elif command == "show":
        show()
    else:
        print("unknown command", command)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

__all__ = ["init", "advance", "link", "record_failure",
           "record_limitation", "verify", "show", "_ORDER"]