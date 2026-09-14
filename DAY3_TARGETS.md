# ARVEN AI — DAY 3 TARGETS

111-feature scope unchanged. Feature 38 (GUI) FROZEN (`arven_gui.py`, `arven_3d.py`).
Day 1 (1-37) and Day 2 (39-108) remain finalized baselines. Day 3 works on the
**implementation maturity and integration gaps** required by the existing 111-feature
architecture: real terminal-first orchestration, gated execution everywhere, and
the cross-cutting test greenhouses (persistence, restart, recovery, security,
confirmation, offline, failure modes, concurrency) that the Day-2 engines still lack.

## Baseline facts (verified, Day 2 end-state)

- Registry: 366 tools (46 Day 1 + 298 Day 2 + 22 Day 3: 8 capability/features +
  7 engineering + 7 orchestrator). Verified by `verify_registry.py` /
  `verify_all_111.py`.
- Full regression: 1146 passed / 0 failed / 0 errors (incl. `tests/day4`).
- `verify_offline.py`, `verify_recovery.py` PASS. GUI files untouched (mtime 2026-09-05).
- `data/arven_memory.db` = 20480 bytes, content unchanged (tests hermetic).

## Day 3 inspection findings (real gaps found during audit)

1. `app.py --text` imports `main` which does NOT exist → no working terminal entry point.
2. No end-to-end chain: USER REQUEST -> intent -> plan -> confirmation -> tool ->
   execution -> memory/event/audit -> user-visible result. Regulated engines exist
   but are islands.
3. `core/planner.py` (feature 74) is a pure coordinator: `plan_*` tools never execute
   a plan against the tool registry; no replan-on-failure loop with real execution.
4. `core/missions.py` `run_step(fn=tool_name)` resolves `tool.function` DIRECTLY:
   it bypasses the registry guard (availability, parameter validation, and the
   confirmation gate). AUTHORIZATION > EXECUTION requires a gated dispatch path.
5. `core/cyber_toolkit.py` `scan()` with tool `local`/`file` always audits
   `Path.cwd()` instead of the authorized target path — real defect.
6. Neither planner, event responder, cyber evidence ledger, undo transactions, nor
   missions have restart/persistence/offline/negative/concurrency coverage in the
   Day-2 regression (engines persist via KeyValueStore but that was never proven).

---

## Target 1 — Terminal Command Chain & Orchestration
- **Feature numbers**: 51 (Personal Assistant/Buddy), 58 (Command Execution &
  Autonomy Loop), 89 (Global Command & Control).
- **Current state**: engines/coordinator exists (`core/advisor.py`, `core/command_center.py`,
  `world_actions.py`); no terminal orchestration path; `app.py --text` broken.
- **Weaknesses**: no user request -> intent -> tool -> result chain; no terminal entry.
- **Dependencies**: `tools.builder` registry, `core/confirmation.CONFIRMATION`,
  `core.kv`, `core/missions.py`, `core/event_response.py`, `core/planner.py`,
  `memory/database.py` (injectable).
- **Required work**: new `core/terminal_engine.py` `TerminalEngine`: intent keyword
  resolution over registry capabilities, authorization/classification via
  `core/safety`, confirmation bridging through `CONFIRMATION` (mint -> approve ->
  invoke with pending request_id; never auto-trust destructive), execute via
  `registry.invoke`, record memory/event/audit; `mission()` runner with gated tool
  dispatch; `status()`/`health()` rollup.
- **Acceptance criteria**: `ask()` returns honest full-chain trace; gated tools
  return `confirm_required` when not authorised and execute when approved;
  unknown intents return `NO_MATCH`; mission steps dispatch through the confirmation
  gate; all state survives restart (persistence proven by tests).
- **Final evidence**: `core/terminal_engine.py`, `tests/day3/test_day3_terminal.py`,
  `test_day3_integration.py`, CLI transcripts in `report_day3_final.md`.

## Target 2 — Planner -> Registry Execution & Replan Loop (feature 74)
- **Feature number**: 74 (Dynamic Planning & Replanning).
- **Current state**: `create_plan/status/list/replan/complete/deprecate` exist and are
  FINAL at Day 2; no step actually executes against the registry.
- **Weaknesses**: steps are inert strings/dicts; replan is manual; no restart-resume.
- **Dependencies**: `core/planner.py`, `tools.builder` registry, `core/confirmation`,
  `core/lifecycle.BoundedOperation`, `core/event_response.py`.
- **Required work**: new `core/plan_execution.py` `PlanRunner`: `run(plan_id)` walks
  planned steps, dispatches `step["tool"]` (+`args`) through `registry.invoke` with a
  per-step timeout, marks steps complete on success, replans via `replace_step` with
  declared fallbacks on failure, escalates when no fallback exists, emits events,
  `resume(plan_id)` continues later (restart recovery).
- **Acceptance criteria**: plan steps execute real registered tools; confirm-gated
  steps honour CONFIRMATION (auto-approve only when requested); blocked steps trigger
  replan; `resume` re-runs only remaining planned steps; interruption becomes an
  honest failure/replan event.
- **Final evidence**: `core/plan_execution.py`, `tests/day3/test_day3_integration.py`,
  `test_day3_persistence.py`, `test_day3_recovery.py`.

## Target 3 — Mission <-> Gated Tool Execution (features 50/54)
- **Feature numbers**: 50/54 (Task/Mission Manager, Personal Mission Manager).
- **Current state**: `run_step(fn=tool_name)` bypasses registry gates.
- **Weaknesses**: a step invoking a high-risk tool via tool-name resolution never
  passes the confirmation gate; failed tool results (dict with success=False) are
  recorded as DONE.
- **Dependencies**: `core/missions.py`, `tools.builder` registry, `core/confirmation`.
- **Required work**: provide an invoker callback used by `TerminalEngine.mission()`
  that routes every step through `registry.invoke` with confirmation-handling and
  raises on failure so `run_step` correctly marks the step FAILED; drive a full
  mission within the chain; a failed dependency must block dependent steps (already
  engine behavior — now proven against real tool dispatch).
- **Acceptance criteria**: mission steps run real tools; a failing tool marks the
  step FAILED (not DONE); high-risk steps require confirmation; mission state
  survives restart; summary/progress correct.
- **Final evidence**: `core/terminal_engine.py`, `tests/day3/test_day3_recovery.py`,
  `test_day3_persistence.py`.

## Target 4 — Event Response End-to-End Hardening (feature 92)
- **Feature number**: 92 (Real-Time Event Response).
- **Current state**: register/ingest/history/stats FINAL; dispatch wired at Day 2.
- **Weaknesses**: no proof a handler actually executes a registered tool end-to-end
  with outcome captured; no persistence-restart proof; sparse negative coverage.
- **Dependencies**: `core/event_response.py`, `tools.builder`.
- **Required work**: tests only (code change only if tests expose a real defect):
  real low-risk tool dispatch returning the wrapped outcome; dedup window; cooldown
  suppression; high-severity escalation with no handler; bad-severity rejection;
  handlers/history surviving restart on the same kv path.
- **Acceptance criteria**: all hardening tests pass; every negative path returns a
  safe deterministic response.
- **Final evidence**: `tests/day3/test_day3_integration.py`,
  `test_day3_persistence.py`, `test_day3_failure_modes.py`.

## Target 5 — Undo / Transaction Recovery Hardening (feature 102)
- **Feature number**: 102 (Universal Undo / Transaction Recovery).
- **Current state**: begin/op/commit/rollback/status FINAL; pre-images in kv.
- **Weaknesses**: no restart proof; no negative coverage (commit-on-rolled-back ops,
  unknown txn id, op on closed txn, partial-failure rollback honesty).
- **Dependencies**: `core/undo.py`, `core/kv`.
- **Required work**: tests only: write -> commit -> reconstruct engine on same path
  -> transaction still committed; rollback restores every pre-image; simulated
  storage failure surfaces `keys_failed` honestly (never a falsely green rollback).
- **Acceptance criteria**: all hardening tests pass; honest partial-failure reports.
- **Final evidence**: `tests/day3/test_day3_recovery.py`, `test_day3_persistence.py`,
  `test_day3_failure_modes.py`.

## Target 6 — Cyber Authorization & File-Audit Fix (feature 60)
- **Feature number**: 60 (Security Guardian & Cybersecurity Toolkit).
- **Current state**: scopes, discovery, explanation, gated scan, evidence ledger FINAL.
- **Weaknesses**: `scan(target=path, tool=local/file)` audits `Path.cwd()` instead of
  the target. No authorization-negative, offline-honesty, or ledger-restart tests.
- **Dependencies**: `core/cyber_toolkit.py`, `core/kv`.
- **Required work**: fix `_file_audit` target handling inside `scan()` so an
  authorized existing path is audited (README contract: local/file scan on an
  authorized local path); tests for unscoped target -> AUTHORIZATION_REQUIRED,
  offline DNS/TLS -> honest FAILED evidence, ledger survives restart, external
  tools reported NOT_INSTALLED honestly.
- **Acceptance criteria**: authorized local file/dir scan audits the target itself;
  unauthorized targets refused; evidence recorded without secrets; restart keeps
  scopes + ledger.
- **Final evidence**: `core/cyber_toolkit.py` (fix), `tests/day3/test_day3_security.py`,
  `test_day3_offline.py`, `test_day3_persistence.py`.

## Target 7 — Backup Integrity & Restore Refusal (feature 61)
- **Feature number**: 61 (Automatic Backup & Recovery).
- **Current state**: snapshot/list/verify/rotate/restore FINAL; restore already gated.
- **Weaknesses**: no negative tests for tampered snapshots forcing restore refusal,
  missing snapshot, rotate-never-deletes, restore-writes-only-to-target_dir.
- **Dependencies**: `core/backup.py`.
- **Required work**: tests only: tamper -> `verify` FAILED -> `restore` refused;
  unknown snap_id -> FAILED; `rotate` archives and keeps dirs (nothing deleted);
  restore copies only into explicit target.
- **Acceptance criteria**: all hardening tests pass; no behavior change.
- **Final evidence**: `tests/day3/test_day3_recovery.py`, `test_day3_security.py`.

## Target 8 — Terminal CLI + Restored Text Entry
- **Feature numbers**: 51/58/89 terminal surface (entry points).
- **Current state**: `app.py --text` broken (imports missing `main`); no CLI.
- **Weaknesses**: no scriptable/REPL terminal over the registry.
- **Dependencies**: `core/terminal_engine.py`, `tools.builder`.
- **Required work**: `cli.py` (`--ask`, `--approve`, `--param`, `--mission`, `--health`,
  `--repl`); `main.py` with `run_text()` so `python app.py --text` works again
  (`app.py` itself is NOT modified).
- **Acceptance criteria**: one-shot `--ask` returns the chain trace; REPL loops;
  `app.py --text` imports and runs; nothing touches the GUI files.
- **Final evidence**: `cli.py`, `main.py`, `tests/day3/test_day3_terminal.py`, demo
  transcripts in `report_day3_final.md`.

## Target 9 — Cross-Cutting Day-3 Test Suite + State Tracker
- **Feature numbers**: architecture-wide (all Day-3 targets).
- **Current state**: no `tests/day3/`; no machine-readable lifecycle tracker;
  Day-2 engines lack persistence/restart/offline/failure/concurrency coverage.
- **Weaknesses**: maturity unproven; lifecycle not machine-checkable.
- **Dependencies**: all targets above.
- **Required work**: `tests/day3/` (lifecycle, integration, registry, terminal,
  persistence, recovery, security, confirmation, offline, failure_modes, restart,
  concurrency, regression); `day3_lifecycle.py` tracker + `day3_state.json`
  (real timestamps, no fabrication).
- **Acceptance criteria**: suite green and hermetic (never touches
  `data/arven_memory.db`); state file valid JSON with legal state transitions.
- **Final evidence**: `tests/day3/*` results in `report_day3_final.md`,
  `day3_state.json`.

---

## Cross-cutting acceptance gates (applied per target at FINAL)

- Registry integration: target's components reachable via `tools.builder.get_registry()`.
- Confirmation: high/destructive never auto-trusted; gated flows through CONFIRMATION.
- Authorization: AUTHORIZATION > EXECUTION (cyber scopes; permission layer).
- Execution: real terminal usage, real output, no fake success.
- Memory/Mission/Event/Audit: relevant chain hooks fire and persist.
- Recovery: STATE A -> action -> STATE B with defined B->A recovery where applicable.
- Persistence: WRITE -> SAVE -> RESTART -> LOAD -> VERIFY.
- Offline: local keeps working; external reports OFFLINE/UNAVAILABLE/NOT_INSTALLED.
- Negative: safe, deterministic responses for malformed input.
- No GUI changes; no feature 112; no new product capability beyond the 111 scope.