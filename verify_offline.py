"""Offline mode verification — deterministic local functions without Ollama."""
from tools.builder import build_registry

reg = build_registry()
print("=== OFFLINE MODE VERIFICATION (deterministic local functions) ===")

# These tools are fully local and must work regardless of Ollama
tests = [
    ("date_time", {}),
    ("system_info", {}),
    ("running_processes", {}),
    ("list_memories", {}),
    ("memory_search", {"query": "python"}),
    ("proactive_status", {}),
    ("comm_status", {}),
    ("tts_status", {}),
]

for name, kwargs in tests:
    r = reg.invoke(name, **kwargs)
    status = "PASS" if r.get("success") else "FAIL"
    action = r.get("action", name)
    print(f"  [{status}] {action}: {r.get('message', '')[:70]}")

# Browser navigate (offline-safe default browser open — we won't actually open)
bp = reg.get("browser_navigate")
print(f"\n  browser_navigate available: {bp.available}")
print("  browser backend (Playwright): ", end="")
bs = reg.invoke("browser_status")
print(f"backend_available={bs.get('backend_available')}")

# Structured error for a destructive op without confirmation
r = reg.invoke("delete_file", path="C:/nonexistent/fake.txt")
print(f"\n  delete_file (untrusted): status={r.get('status')}")

print("\n=== done ===")
