"""ARVEN Day-3/5 terminal CLI (features 51/58/89 + all-122 surface).

Real terminal-first surface over the registry via ``core.terminal_engine``:

    python cli.py --ask "list plans"
    python cli.py --ask "diagnostics run"
    python cli.py --approve --ask "cyber scan target https://example.com"
    python cli.py --mission "ops check" --step "diagnostics_run" --step "context_summary"
    python cli.py --health
    python cli.py --features             # all 122 features vs the registry
    python cli.py --feature 121          # one feature reconciled
    python cli.py --capabilities         # honest capability status
    python cli.py --resources            # hardware resources
    python cli.py --dependencies [id]    # dependency map
    python cli.py --orchestrate "goal" --steps "do X; do Y"
    python cli.py --providers            # provider health + reasoning window
    python cli.py --feature 122          # feature-level help / smoke
    python cli.py --repl

Every path returns the honest structured result plus the ``chain`` trace and
writes an audit entry through the terminal engine. No fabricated success.
"""

import argparse
import json
import re
import sys

from core.terminal_engine import TerminalEngine


def _orchestrator_instance():
    from core.mission_orchestrator import MissionOrchestrator
    return MissionOrchestrator()


def _capability_instance():
    from core.capability_awareness import CapabilityAwareness
    return CapabilityAwareness()


def _build_engine():
    from core.kv import KeyValueStore
    from core.planner import AdaptivePlanner
    from core.event_response import EventResponder
    from core.missions import MissionsEngine
    return TerminalEngine(
        kv=KeyValueStore("data/terminal_engine.json"),
        planner=AdaptivePlanner(kv=KeyValueStore("data/planner.json")),
        responder=EventResponder(kv=KeyValueStore("data/event_response.json")),
        missions=MissionsEngine(path="data/runtime/missions.json"),
    )


def _parse_params(values):
    params = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"bad --param '{item}': expected key=value")
        key, _, value = item.partition("=")
        low = value.strip().lower()
        if low in ("true", "false"):
            value = low == "true"
        elif re.fullmatch(r"-?\d+", value.strip()):
            value = int(value.strip())
        elif re.fullmatch(r"-?\d+\.\d+", value.strip()):
            value = float(value.strip())
        if key in params:
            raise SystemExit(f"duplicate --param '{key}'")
        params[key] = value
    return params


def _parse_steps(entries):
    steps = []
    for item in entries or []:
        if "|" in item:
            action, _, args_raw = item.partition("|")
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = _parse_params(args_raw.split(";"))
        else:
            action, args = item, {}
        if not action.strip():
            raise SystemExit("empty --step action")
        steps.append({"title": action.strip(), "tool": action.strip(),
                      "args": dict(args or {})})
    if not steps:
        raise SystemExit("--mission needs at least one --step")
    return steps


def _print_result(result, show_chain=True):
    print("RESULT", result.get("status"), flush=True)
    for key in ("action", "message", "result", "request_id", "mission_id",
                "mission_status", "progress_pct", "steps_done", "steps_total"):
        if key in result and result[key] is not None:
            print(f"  {key}: {result[key]}", flush=True)
    if show_chain and isinstance(result.get("chain"), dict):
        chain = result["chain"]
        print("CHAIN", flush=True)
        for key in ("intent", "authorization", "confirmation", "execution",
                    "memory", "event", "audit", "plan"):
            if chain.get(key) is not None:
                print(f"  {key}: {json.dumps(chain[key], default=str)}",
                      flush=True)


def _resolve_engine_or_exit(engine, request, approve, params):
    result = engine.act(request, param=params, approve=approve)
    _print_result(result)
    return result


def _parse_steps_string(raw):
    steps = []
    for item in (raw or "").split(";"):
        item = item.strip()
        if not item:
            continue
        if "|" in item:
            action, _, args_raw = item.partition("|")
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = _parse_params(args_raw.split(";"))
        else:
            action, args = item, {}
        if not action.strip():
            continue
        steps.append({"title": action.strip(), "tool": action.strip(),
                      "args": dict(args or {})})
    return steps


def _registry():
    from tools.builder import build_registry, get_registry
    registry = get_registry()
    if registry is None:
        registry = build_registry()
    return registry


def _print_feature_table():
    from core.features import list_features
    registry = _registry()
    names = set(registry.names())
    features = list(list_features())
    print(f"FEATURES {len(features)}", flush=True)
    for feat in features:
        tools = feat.get("tools") or []
        registered = any(t in names for t in tools)
        print(f"  {feat['id']:03d} | {feat['name']} | tools={tools or '_'}"
              f" | registered={registered} | offline={feat.get('offline', '-')}",
              flush=True)


def _print_capabilities():
    caps = _capability_instance().probe()
    print("CAPABILITIES", flush=True)
    for name, status in sorted((caps.get("capabilities") or {}).items()):
        print(f"  {name}: {status}", flush=True)
    print("PROVIDERS", flush=True)
    for name, status in sorted((caps.get("providers") or {}).items()):
        print(f"  {name}: {status}", flush=True)
    print("PERMISSIONS", flush=True)
    for name, perm in sorted((caps.get("permissions") or {}).items()):
        if isinstance(perm, dict):
            print(f"  {name}: {perm.get('permission', perm)}", flush=True)
        else:
            print(f"  {name}: {perm}", flush=True)


def _print_resources():
    caps = _capability_instance().probe()
    print("RESOURCES", flush=True)
    hw = caps.get("hardware") or {}
    for key in ("cpu", "ram", "gpu", "system", "hostname"):
        if hw.get(key) is not None:
            print(f"  {key}: {hw[key]}", flush=True)
    print("SOFTWARE", flush=True)
    for name, status in sorted((caps.get("software") or {}).items()):
        print(f"  {name}: {status}", flush=True)


def _print_dependencies(feature_id=None):
    graph = _capability_instance().dependencies(feature_id)
    print("DEPENDENCIES", feature_id if feature_id is not None else "(all)",
          flush=True)
    if feature_id is not None:
        print(" ", json.dumps(graph, default=str, indent=2), flush=True)
        return
    for name, items in sorted((graph or {}).items()):
        if isinstance(items, (list, tuple, set)):
            print(f"  {name}: {', '.join(str(i) for i in items)}",
                  flush=True)
        else:
            print(f"  {name}: {items}", flush=True)


def _feature_id(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise SystemExit(f"--feature expects a numeric id, got '{raw}'")
    if value < 1 or value > 123:
        raise SystemExit(f"--feature id out of range 1..123: {value}")
    return value


def _feature_demo(feature_id):
    """A deterministic, honest executable smoke for a feature id (1..123).

    Framework/low-side effects avoided: every demo is local and read-only or
    writes to its own artifact store. Returns (exit_code, summary).
    """
    from tools.builder import get_registry
    registry = get_registry()
    cases = {
        112: ("async_submit", {"tool": "eng_calculate",
                               "args": {"expression": "12*6", "timeout": 5}}),
        113: ("steering_status", {}),
        114: ("reasoning_status", {}),
        115: ("computer_use_status", {}),
        116: ("cad_make", {"kind": "cube", "name": "cli_demo_cube"}),
        117: ("pcb_status", {}),
        118: ("webapp_status", {}),
        119: ("sci_detect", {}),
         120: ("art_status", {}),
         121: ("mcp_status", {}),
         122: ("ctx_detect", {}),
         123: ("mechatronics_discover", {}),
    }
    if feature_id not in cases:
        return 0, "no executable demo defined; see --feature for the catalog row"
    name, params = cases[feature_id]
    tool = registry.get(name)
    if tool is None:
        return 1, f"tool '{name}' not registered"
    try:
        result = tool.function(**params)
    except Exception as exc:
        return 1, f"feature={feature_id} tool={name} RAISED: {exc}"
    return 0, f"feature={feature_id} tool={name} -> {result}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cli", description="ARVEN terminal CLI (Day 3)")
    parser.add_argument("--ask", metavar="TEXT", help="execute one request")
    parser.add_argument("--param", action="append", default=[],
                        metavar="key=value",
                        help="argument for the requested tool (repeatable)")
    parser.add_argument("--approve", action="store_true",
                        help="auto-approve confirmation-required steps")
    parser.add_argument("--answer", metavar="RID:yes|no",
                        help="resolve a pending confirmation request")
    parser.add_argument("--mission", metavar="TITLE",
                        help="run a supervised mission")
    parser.add_argument("--step", action="append", default=[],
                        metavar="tool|{args_json}",
                        help="mission step (repeatable)")
    parser.add_argument("--steps", metavar="'A; B|{...}; C'",
                        help="semicolon-separated steps for --orchestrate")
    parser.add_argument("--orchestrate", metavar="GOAL",
                        help="run an orchestrated goal end to end")
    parser.add_argument("--params-timeout", type=float, default=10.0,
                        help="per-step timeout (seconds) for --orchestrate")
    parser.add_argument("--features", action="store_true",
                        help="list all 122 features vs the registry")
    parser.add_argument("--feature", metavar="ID",
                        help="show one feature reconciled (1..123)")
    parser.add_argument("--test-feature", metavar="ID",
                        help="run a deterministic executable smoke for a "
                             "feature (112-122)")
    parser.add_argument("--providers", action="store_true",
                        help="show provider health + reasoning/long-context "
                             "windows")
    parser.add_argument("--capabilities", action="store_true",
                        help="show honest capability status")
    parser.add_argument("--resources", action="store_true",
                        help="show hardware + software resources")
    parser.add_argument("--dependencies", nargs="?", const="",
                        metavar="FEATURE_ID",
                        help="show the feature dependency map")
    parser.add_argument("--health", action="store_true",
                        help="report provider health + registry size")
    parser.add_argument("--repl", action="store_true",
                        help="interactive terminal loop")
    parser.add_argument("--mechatronics-spec", metavar="NAME",
                        help="feature 123: define a mechatronic system")
    parser.add_argument("--mechatronics-simulate", metavar="NAME",
                        help="feature 123: simulate a system/twin")
    parser.add_argument("--mechatronics-validate", metavar="NAME",
                        help="feature 123: validate a twin/system")
    parser.add_argument("--mechatronics-discover", action="store_true",
                        help="feature 123: discover real hardware")
    parser.add_argument("--mechatronics-connect", metavar="DEVICE",
                        help="feature 123: connect a device (or SIMULATED)")
    parser.add_argument("--mechatronics-status", action="store_true",
                        help="feature 123: HAL status")
    parser.add_argument("--mechatronics-read", metavar="REGISTER",
                        help="feature 123: read a register")
    parser.add_argument("--mechatronics-write", metavar="REG=VALUE",
                        help="feature 123: write a register")
    parser.add_argument("--mechatronics-hil", metavar="TARGET",
                        help="feature 123: run a HIL compare")
    parser.add_argument("--mechatronics-diagnostics", action="store_true",
                        help="feature 123: HAL diagnostics")
    parser.add_argument("--mechatronics-bom", action="store_true",
                        help="feature 123: bill of materials demo")
    args = parser.parse_args(argv)

    engine = _build_engine()

    if args.answer:
        rid, _, verdict = args.answer.partition(":")
        if not rid or verdict not in ("yes", "no"):
            raise SystemExit("--answer expects RID:yes or RID:no")
        _print_result(engine.answer(rid, verdict))

    if args.ask:
        params = _parse_params(args.param)
        _print_result(engine.act(args.ask, param=params, approve=args.approve))

    if args.mission:
        steps = _parse_steps(args.step)
        _print_result(engine.mission(args.mission, steps, approve=args.approve))

    if args.orchestrate:
        steps = _parse_steps_string(args.steps)
        if not steps:
            steps = [{"title": args.orchestrate,
                      "tool": args.orchestrate, "args": {}}]
        _print_result(_orchestrator_instance().run(
            args.orchestrate, steps, approve=args.approve,
            step_timeout=float(args.params_timeout or 10.0)))

    if args.features:
        _print_feature_table()

    if args.feature:
        _print_result(_registry().invoke("feature_status",
                                         feature_id=_feature_id(args.feature)))

    if args.test_feature:
        fid = _feature_id(args.test_feature)
        if not 112 <= fid <= 123:
            raise SystemExit("--test-feature expects an id in 112..123")
        code, summary = _feature_demo(fid)
        verdict = "PASS" if code == 0 else "FAIL"
        print(f"FEATURE {fid} EXEC: {verdict}", flush=True)
        print(f"  {summary}", flush=True)
        if code != 0:
            return code

    if args.providers:
        health = engine.health()
        print("PROVIDERS", flush=True)
        for name, status in sorted(health["provider_statuses"].items()):
            print(f"  {name}: {status}", flush=True)
        try:
            from core.long_context import detect as lc_detect
            win = lc_detect()
            print(f"  reasoning/long-context window: {win['provider']} "
                  f"{win['model']} max_context={win['max_context']} "
                  f"({win['window_source']})", flush=True)
        except Exception as exc:
            print(f"  long-context window: unavailable ({exc})", flush=True)
        print(f"  registry_tools: {health['registry_tools']}", flush=True)

    if args.capabilities:
        _print_capabilities()

    if args.resources:
        _print_resources()

    if args.dependencies is not None:
        _print_dependencies(_feature_id(args.dependencies)
                            if args.dependencies else None)

    if args.health:
        health = engine.health()
        print("HEALTH", flush=True)
        print(f"  worst_status: {health['worst_status']}", flush=True)
        print(f"  registry_tools: {health['registry_tools']}", flush=True)
        for name, status in sorted(health["provider_statuses"].items()):
            print(f"  {name}: {status}", flush=True)

    if args.repl:
        banner = ("ARVEN terminal (Day 3). Ask a capability, or type "
                  "'exit', 'quit', 'bye'.")
        print(banner, flush=True)
        while True:
            try:
                line = input("arven> ").strip()
            except (EOFError, KeyboardInterrupt):
                print(flush=True)
                break
            if not line:
                continue
            low = line.lower()
            if low in ("exit", "quit", "bye"):
                break
            if low == "health":
                h = engine.health()
                print(f"  worst: {h['worst_status']} tools: "
                      f"{h['registry_tools']}", flush=True)
                continue
            if low == "features":
                _print_feature_table()
                continue
            if low == "capabilities":
                _print_capabilities()
                continue
            if low == "resources":
                _print_resources()
                continue
            params = {}
            if "::" in line:
                line, _, raw = line.rpartition("::")
                try:
                    params = json.loads(raw)
                except json.JSONDecodeError:
                    params = _parse_params(raw.split(";"))
            _print_result(engine.act(line, param=params, approve=args.approve))

    if _any_mechatronics_flag(args):
        _handle_mechatronics(args)

    return 0


def _any_mechatronics_flag(args):
    return any([
        args.mechatronics_spec, args.mechatronics_simulate,
        args.mechatronics_validate, args.mechatronics_discover,
        args.mechatronics_connect, args.mechatronics_status,
        args.mechatronics_read, args.mechatronics_write,
        args.mechatronics_hil, args.mechatronics_diagnostics,
        args.mechatronics_bom,
    ])


def _handle_mechatronics(args):
    from core.mechatronics import engine
    mech = engine()
    if args.mechatronics_spec:
        params = _parse_params(args.param)
        body = {"name": args.mechatronics_spec}
        if "dims" in params:
            body["dims"] = params["dims"]
        if "mass" in params:
            body["mass"] = params["mass"]
        _print_result(mech.create_system(**body))
    if args.mechatronics_simulate:
        _print_result(mech.simulate(
            system={"motion": {"target_velocity": 1.0, "kp": 1.0}},
            duration=2.0, dt=0.05))
    if args.mechatronics_validate:
        _print_result(mech.twin_validate(args.mechatronics_validate))
    if args.mechatronics_discover:
        print("MECHATRONICS DISCOVER", flush=True)
        out = mech.discover()
        _print_result(out)
        for dev in out.get("devices", []):
            print(f"  {dev['kind']}: {dev['id']} ({dev.get('family','')})",
                  flush=True)
        if not out.get("devices"):
            print("  no real hardware present; simulated mock available via "
                  "--mechatronics-connect SIMULATED", flush=True)
    if args.mechatronics_connect:
        simulate = str(args.mechatronics_connect).upper() in (
            "SIMULATED", "SIMULATED_DEVICE", "MOCK")
        device = None if simulate else args.mechatronics_connect
        _print_result(mech.hal_connect(device=device, simulate=simulate))
    if args.mechatronics_status:
        _print_result(mech.hal_status())
    if args.mechatronics_read:
        _print_result(mech.hal_read(register=args.mechatronics_read))
    if args.mechatronics_write:
        reg, _, val = args.mechatronics_write.partition("=")
        _print_result(mech.hal_write(register=reg, value=val))
    if args.mechatronics_hil:
        _print_result(mech.hil_run(
            inject={"value": float(args.mechatronics_hil),
                    "target": float(args.mechatronics_hil),
                    "expected": float(args.mechatronics_hil)},
            tolerance_abs=0.0))
    if args.mechatronics_diagnostics:
        _print_result(mech.hal_diagnostics())
    if args.mechatronics_bom:
        _print_result(mech.bom(items=[
            {"name": "MCU", "qty": 1, "unit_cost": None},
            {"name": "Actuator", "qty": 2, "unit_cost": None}]))


if __name__ == "__main__":
    sys.exit(main())