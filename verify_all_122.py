"""verify_all_122.py — reconcile EVERY feature (1..122) against real code.

Same rules as verify_all_111.py, extended to the full catalog plus the
features 112-122 CLI surface:

  identity     rows 1..122, no missing/duplicate ids
  entrypoint   every listed tool registered + available; every listed module
               imports; CLI flags referenced exist in cli.py
  executable   every feature 112..122 has a registered cli --test-feature
               demo tool (verified live by tests/day5/test_day5_terminal.py)
  status vs    38 is FROZEN (GUI deliberately untouched)
  acceptance

Exit code: 0 only when every feature passes (FROZEN counts as pass).
No fabricated success: a missing tool/module/flag is a FAIL.
"""

import importlib
import os
import sys

from core.features import list_features
from tools.builder import build_registry

ROOT = os.path.dirname(os.path.abspath(__file__))
FROZEN_IDS = {38}
REQUIRED_CLI_FLAGS = [
    "--features", "--feature", "--test-feature", "--providers",
    "--capabilities", "--resources", "--dependencies", "--orchestrate",
    "--steps",
]


def _cli_flags():
    src = ""
    with open(os.path.join(ROOT, "cli.py"), encoding="utf-8") as fh:
        src = fh.read()
    missing = [flag for flag in REQUIRED_CLI_FLAGS if flag not in src]
    return missing


_CLI_SRC = None


def _cli_src():
    global _CLI_SRC
    if _CLI_SRC is None:
        with open(os.path.join(ROOT, "cli.py"), encoding="utf-8") as fh:
            _CLI_SRC = fh.read()
    return _CLI_SRC


def _module_imports(module):
    mod = module.replace("/", ".").replace(".py", "")
    try:
        importlib.import_module(mod)
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _demo_tools():
    """Map cli._feature_demo cases (112..122) to their registered tool names."""
    import re
    with open(os.path.join(ROOT, "cli.py"), encoding="utf-8") as fh:
        src = fh.read()
    pairs = re.findall(r"(\d+):\s*\(\"([a-z0-9_]+)\"", src)
    return {int(k): v for k, v in pairs}


def main():
    rows = sorted([r for r in list_features() if r["id"] <= 122],
                  key=lambda r: r["id"])
    ids = [r["id"] for r in rows]
    d1, d2 = sorted(set(ids)), list(range(1, 123))
    identity_fail = (ids != d2) or len(ids) != 122
    identity_notes = []
    if set(ids) != set(d2):
        identity_notes.append("missing/bad ids: "
                              + str(sorted(set(d2) - set(ids))))
    if len(ids) != len(set(ids)):
        identity_notes.append("duplicate ids")

    reg = build_registry()
    names = set(reg.names())
    tools = {t.name: t for t in reg.all()}

    cli_missing = _cli_flags()
    if cli_missing:
        print("CLI", "FAIL", "missing flags:", ",".join(cli_missing))

    frozen_files = ["main.py", "arven_gui.py", "arven_3d.py"]
    frozen_ok = all(os.path.exists(os.path.join(ROOT, f)) for f in frozen_files)

    demo = _demo_tools()
    exec_fail = []
    for fid in range(112, 123):
        demo_tool = demo.get(fid)
        if demo_tool is None:
            exec_fail.append(f"{fid}:no-demo-tool")
        elif demo_tool not in names:
            exec_fail.append(f"{fid}:{demo_tool}-missing")

    print("=== verify_all_122 ===")
    print(f"rows parsed: {len(rows)} ids 1..122:"
          f"{'OK' if not identity_fail else 'FAIL'}")
    if identity_notes:
        print("  ", "; ".join(identity_notes))

    failures = 0
    lines = {r["id"]: None for r in rows}
    for row in rows:
        fid = row["id"]
        tools_list = list(row["tools"])
        reasons = []

        if fid in FROZEN_IDS:
            reasons.append("FROZEN GUI")
            if not frozen_ok:
                reasons.append("frozen files missing")
            status = "PASS"
            print_line = f"{fid:03d} | FROZEN | {row['name']}"
        elif tools_list:
            missing = [t for t in tools_list if t not in names]
            unavailable = [t for t in tools_list
                           if t in names and not tools[t].available]
            status = "PASS" if not missing and not unavailable else "FAIL"
            if missing:
                reasons.append("tools missing: " + ",".join(missing))
            if unavailable:
                reasons.append("tools unavailable: " + ",".join(unavailable))
            print_line = f"{fid:03d} | REGISTERED | {row['name']}"
        else:
            bad = [m for m in row["modules"] if _module_imports(m)]
            status = "PASS" if not bad else "FAIL"
            if bad:
                reasons.append("modules fail: " + "; ".join(bad))
            print_line = f"{fid:03d} | FRAMEWORK-OK | {row['name']}"

        entrypoints = row.get("entrypoints") or []
        for ep in (entrypoints if isinstance(entrypoints, list)
                   else [entrypoints]):
            if "cli --" in ep:
                flag = ep.split("cli ")[1].split()[0].strip()
                if flag.startswith("-") and flag not in _cli_src():
                    reasons.append(f"cli flag missing: {flag}")
        lines[fid] = (status, print_line, reasons,
                      f"{len(tools_list)} tools" if tools_list
                      else f"{len(row['modules'])} modules")
        if status == "FAIL":
            failures += 1

    for fid in sorted(lines):
        status, title, reasons, evidence = lines[fid]
        badge = "ok  " if status == "PASS" else "FAIL"
        print(f"  {badge} {title}")
        for reason in reasons:
            print(f"          ! {reason}")

    if exec_fail:
        print("  FAIL executable demos:", ", ".join(exec_fail))
    else:
        print("  executable demos 112..122: all registered")

    cli_fail = 1 if cli_missing else 0
    intent_fail = 1 if identity_fail else 0
    frozen_fail = 0 if frozen_ok else 1
    total_fail = failures + cli_fail + intent_fail + frozen_fail \
        + (1 if exec_fail else 0)

    print("---")
    print(f"features:   {len(rows)} rows, FAIL rows: {failures}")
    print(f"registry:   {len(names)} tools "
          f"(catalog refs: {len(set(t for r in rows for t in r['tools']))})")
    print(f"cli flags:  {'OK' if not cli_missing else 'FAIL ' + ','.join(cli_missing)}")
    print(f"frozen:     {'OK' if not frozen_fail else 'FAIL (GUI must stay frozen)'}")
    print(f"identity:   {'OK' if not intent_fail else 'FAIL'}")
    print("RESULT", "PASS" if total_fail == 0 else "FAIL")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())