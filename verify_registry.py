"""ToolRegistry production verification script."""
from tools.builder import build_registry

reg = build_registry()

print("=== TOOLREGISTRY PRODUCTION VERIFICATION ===")
print(f"Total tools: {len(reg.names())}")
print()

# Category breakdown
cats = {}
for t in reg.all():
    c = t.category
    cats[c] = cats.get(c, 0) + 1
print("By category:")
for c, n in sorted(cats.items()):
    print(f"  {c}: {n}")
print()

# Representative tool checks
representative = {
    "Brain/Identity": ["system_info", "date_time"],
    "Memory": ["memory_search", "memory_store", "list_memories"],
    "System": ["system_info", "date_time", "run_shell", "wifi_status"],
    "File": ["create_file", "read_file", "write_file", "delete_file", "search_files"],
    "Web": ["web_search", "fetch_page"],
    "Browser": ["browser_status", "browser_navigate", "browser_search"],
    "Communication": ["comm_status", "email_search", "email_send", "calendar_events"],
    "TTS": ["tts_status", "tts_speak"],
    "Proactive": ["proactive_status", "proactive_suggest"],
    "Android": ["android_status"],
    "IoT": ["iot_status"],
    "Vision": ["image_analyze"],
    "Screen": ["capture_screen"],
    "Media": ["media_command"],
    "Documents": ["read_document"],
    "Apps": ["open_app"],
}

for category, tool_names in representative.items():
    print(f"--- {category} ---")
    for name in tool_names:
        t = reg.get(name)
        if t is None:
            print(f"  {name}: MISSING")
            continue
        s = t.schema()
        status = t.status()
        param_count = len(s["parameters"])
        print(f"  {name}: risk={s['risk']}, confirm={s['confirm_required']}, backend={s['backend']}, status={status}, params={param_count}")
print()

# Confirmation enforcement check
print("--- Confirmation Enforcement ---")
for name in ["email_send", "calendar_create", "messaging_send"]:
    t = reg.get(name)
    print(f"  {name}: confirm_required={t.confirm_required}, risk={t.risk}")
    r = reg.invoke(name, to="test@test.com", subject="t", body="t", confirmed=False)
    print(f"    untrusted invoke: status={r.get('status')}")
    r2 = reg.invoke(name, trusted=True, to="test@test.com", subject="t", body="t", confirmed=False)
    print(f"    trusted+unconfirmed: status={r2.get('status')}")
print()

# Safe production tool execution
print("--- Safe Production Execution ---")
r = reg.invoke("system_info")
print(f"  system_info: success={r.get('success')}")
r = reg.invoke("date_time")
print(f"  date_time: success={r.get('success')}")
r = reg.invoke("comm_status")
print(f"  comm_status: success={r.get('success')}, email={r.get('email')}")
r = reg.invoke("tts_status")
print(f"  tts_status: success={r.get('success')}, available={r.get('backend_available')}")
r = reg.invoke("proactive_status")
print(f"  proactive_status: success={r.get('success')}")
r = reg.invoke("browser_status")
print(f"  browser_status: success={r.get('success')}")
r = reg.invoke("android_status")
print(f"  android_status: success={r.get('success')}")
r = reg.invoke("iot_status")
print(f"  iot_status: success={r.get('success')}")
r = reg.invoke("web_search", query="python")
print(f"  web_search: success={r.get('success')}")
r = reg.invoke("memory_search", query="test")
print(f"  memory_search: success={r.get('success')}")
r = reg.invoke("list_memories")
print(f"  list_memories: success={r.get('success')}")
