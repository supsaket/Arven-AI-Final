"""Recovery + confirmation production verification."""
from tools.builder import build_registry
from core.recovery import run_tool_with_recovery, classify, RecoveryAction

reg = build_registry()

print("=== RECOVERY PRODUCTION VERIFICATION ===")

# 1. Safe tool executes successfully WITH recovery wrapper
r = run_tool_with_recovery(
    reg.get("date_time").function,
    kwargs={},
    destructive=False,
    action="date_time",
)
print(f"date_time (recovery): status={r.get('status')}, success={r.get('success')}")

# 2. Failure path — invoke a tool that returns structured failure (not configured email)
r2 = reg.invoke("email_search", query="x")
print(f"email_search (not configured): status={r2.get('status')}")

# 3. Confirmation denial for HIGH_RISK send
r3 = reg.invoke("email_send", to="a@b.com", subject="x", body="y")
print(f"email_send (untrusted): status={r3.get('status')}")

# 4. Trusted but not confirmed — provider rejects
r4 = reg.invoke("email_send", trusted=True, to="a@b.com", subject="x", body="y")
print(f"email_send (trusted, unconfirmed): status={r4.get('status')}")

# 5. Unknown tool
r5 = reg.invoke("no_such_tool")
print(f"unknown tool: status={r5.get('status')}")

# 6. Duplicate execution guard — invoke same didn't run in parallel, but test guard acquire
g = reg.guard
key = ("date_time", "[]")
acquired = g.acquire(key)
print(f"ExecutionGuard acquire (should be True): {acquired}")
if acquired:
    free = g.release(key)
    print(f"ExecutionGuard release (should be True): {free}")

print("\n=== done ===")
