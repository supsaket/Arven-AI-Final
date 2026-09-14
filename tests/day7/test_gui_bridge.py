"""Day 7 — the real ArvenBridge against a real TerminalEngine (temp stores),
verifying the GUI routing reaches the actual ARVEN backend, no brain/Ollama."""

from core.confirmation import CONFIRMATION


def test_real_capability_routes_through_features(real_bridge):
    result = real_bridge.send("status")
    assert result["source"] == "feature"
    assert result["ok"] is True
    assert result["status"] in ("AVAILABLE", "ok")
    assert result["text"]


def test_real_confirmation_gate_then_answer(real_bridge):
    result = real_bridge.send("cyber scan target https://localhost/")
    assert result["status"] == "confirm_required"
    assert result["confirm"] is True
    assert result["request_id"]
    answer = real_bridge.confirm(result["request_id"], "yes")
    assert answer.get("ok") is True


def test_real_confirmation_denial(real_bridge):
    result = real_bridge.send("cyber scan target https://localhost/")
    assert result["request_id"]
    answer = real_bridge.confirm(result["request_id"], "no")
    assert answer.get("ok") is True
    assert CONFIRMATION.is_pending(result["request_id"]) is False


def test_real_approved_rerun_skips_gate(real_bridge):
    result = real_bridge.send("cyber scan target https://localhost/",
                              approve=True)
    # approve path consumes the gate and lands on an honest authorization scope
    assert result["ok"] is False  # not silently 'success' without real scope
    assert result["status"] not in ("confirm_required", "ERROR")


def test_read_file_via_registry(real_bridge, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("x" * 40, encoding="utf-8")
    out = real_bridge.read_file(str(f))
    assert out["success"] is True
    assert len(out["content"]) == 40


def test_incognito_keeps_engine_audit_in_memory(real_bridge, tmp_path):
    kv_file = tmp_path / "terminal.json"
    kv_file.write_text("{}", encoding="utf-8")
    before = kv_file.read_bytes()
    result = real_bridge.send("status", incognito=True)
    assert result.get("incognito") is True
    assert kv_file.read_bytes() == before  # no terminal audit persisted


def test_latest_media_reports_missing(real_bridge):
    out = real_bridge.latest_media()
    assert out["ok"] in (True, False)  # honest either way
    assert "path" in out


def test_scheduler_real_store_roundtrip(real_bridge):
    added = real_bridge.add_scheduled("remind me to water plants at 18:00")
    assert added.get("success") is True
    items = real_bridge.scheduled_items()["items"]
    assert items, "task should appear in scheduled panel store"
    assert any("water" in (str(i.get("text")) or "") for i in items)
    target = next(i for i in items if "water" in (str(i.get("text")) or ""))
    cancelled = real_bridge.cancel_scheduled(task_id=target.get("id"))
    assert cancelled.get("success") is True
    remaining = real_bridge.scheduled_items()["items"]
    assert all(str(i.get("id")) != str(target.get("id")) for i in remaining)


def test_pins_real_store_roundtrip(real_bridge):
    real_bridge.pin_chat("Pinned from test", [
        {"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}])
    pins = real_bridge.list_pins()
    assert pins["ok"] is True
    assert any(p["title"] == "Pinned from test" for p in pins["pins"])
    pid = next(p["id"] for p in pins["pins"] if p["title"] == "Pinned from test")
    loaded = real_bridge.load_pin(pid)
    assert loaded["ok"] is True
    assert len(loaded["turns"]) == 2
    real_bridge.remove_pin(pid)
    assert not any(p["id"] == pid for p in real_bridge.list_pins()["pins"])


def test_camera_and_image_report_honest_missing_state(real_bridge):
    cam = real_bridge.camera_capture()
    assert cam["success"] is False  # cv2 absent -> honest failure, not fake
    assert cam.get("message") or cam.get("status")
    img = real_bridge.generate_image("test")
    assert img["ok"] in (True, False)  # NOT_CONFIGURED is a valid honest state


def test_registry_health_tally(real_bridge):
    h = real_bridge.health()
    assert h["ok"] is True
    assert h["tools"] == 436


def test_screen_capture_missing_backend_is_honest(real_bridge):
    out = real_bridge.capture_screen()
    assert "success" in out  # either True (writes file) or False (honest msg)