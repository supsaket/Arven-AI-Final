"""Day 7 — GUI chat flow: send, confirmation, incognito, voice, TTS, media,
camera honesty, files, pins drawer render."""

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

import gui.window as window_mod
from conftest import settle


def chat_text(panel):
    return " ".join(label.text()
                    for label in panel.content.findChildren(QLabel))


def test_text_send_produces_user_and_assistant_turns(window, qapp):
    window._submit_text("hello")
    settle(qapp, window)
    turns = window.chat.turns()
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert "ARVEN handled: hello" in turns[1]["text"]
    assert window.center.state() == "idle"


def test_confirmation_approve_flow(window, qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(window_mod, "ConfirmDialog", _ApproveDialog)
    window.bridge.confirm = lambda rid, verdict: calls.append((rid, verdict)) \
        or {"ok": True}
    window._submit_text("review")
    settle(qapp, window)
    assert calls == [("req-1", "yes")]
    assert any(s["text"] == "review" and s["approve"] is True
               for s in window.bridge.sends)
    turns = window.chat.turns()
    assert any("approved" in t["text"] for t in turns)


def test_confirmation_deny_flow(window, qapp, monkeypatch):
    monkeypatch.setattr(window_mod, "ConfirmDialog", _DenyDialog)
    window._submit_text("review")
    settle(qapp, window)
    assert ("req-1", "no") in window.bridge.confirmed
    assert not any(s["approve"] is True for s in window.bridge.sends)
    assert "was not run" in chat_text(window.chat)


def test_incognito_toggle_shows_tag_and_flags_sends(window, qapp):
    window._set_incognito(True)
    assert window.chat.inc_tag.isVisibleTo(window.chat)
    window._submit_text("secret message")
    settle(qapp, window)
    assert window.bridge.sends[-1]["incognito"] is True
    window._set_incognito(False)
    assert not window.chat.inc_tag.isVisibleTo(window.chat)
    window._submit_text("normal")
    settle(qapp, window)
    assert window.bridge.sends[-1]["incognito"] is False


def test_voice_input_routes_text_through_backend(window, qapp):
    window._handle_voice({"success": True, "text": "spoken words"})
    settle(qapp, window)
    turns = window.chat.turns()
    assert turns[0]["role"] == "user"
    assert turns[0]["text"] == "spoken words"
    assert "ARVEN handled: spoken words" in turns[-1]["text"]


def test_voice_silence_is_honest(window):
    window.chat.clear_chat()
    window._handle_voice({"success": False, "message": "no microphone"})
    assert "no microphone" in chat_text(window.chat)


def test_tts_toggle_enables_voice_replies(window, qapp, monkeypatch):
    monkeypatch.setattr(window.bridge, "speak", lambda t: window.bridge.spoken.append(t) or {"success": True})
    window._plus_action("tts")
    assert window._voice_replies is True
    window._submit_text("say this aloud")
    settle(qapp, window)
    assert any("say this aloud" in t for t in window.bridge.spoken)


def test_camera_honest_failure_shows_message(window, qapp):
    before = len(window.chat.turns())
    window._handle_camera("cam_screen", window.bridge.capture_screen())
    assert "no screen" in chat_text(window.chat)
    assert len(window.chat.turns()) >= before


def test_generate_image_not_configured_is_honest(window, qapp):
    window._handle_image(window.bridge.generate_image("landscape"))
    turns = window.chat.turns()
    assert any("provider" in t["text"] for t in turns)


def test_media_panel_shows_latest_image(window, qapp, tmp_path):
    from PySide6.QtGui import QImage
    png = tmp_path / "art.png"
    img = QImage(8, 8, QImage.Format_RGB32)
    img.fill(0x2E9B4F)
    assert img.save(str(png))
    window.bridge.latest_media = lambda: {"ok": True, "path": str(png)}
    window._handle_media(window.bridge.latest_media())
    assert window.media._current_path == str(png)
    assert window.media.download_btn.isEnabled()
    assert window.media.maximize_btn.isEnabled()


def test_file_attach_reads_through_registry(window, qapp, tmp_path):
    data = tmp_path / "note.txt"
    data.write_text("attached content", encoding="utf-8")
    window._reupload(str(data))
    settle(qapp, window)
    turns = window.chat.turns()
    assert any("Read" in t["text"] for t in turns)


def test_schedule_panel_renders_real_items(window, qapp):
    window.schedule.set_items([
        {"id": "t1", "text": "water plants", "time": "18:00"},
        {"id": "t2", "text": "daily standup", "time": "09:00"},
    ])
    rows = window.schedule.rows
    labels = []
    for index in range(rows.count()):
        item = rows.itemAt(index)
        if item and item.widget():
            labels += [l.text() for l in item.widget().findChildren(QLabel)]
    assert any("water plants" in t for t in labels)
    assert any("standup" in t for t in labels)
    assert any("[18:00]" in t for t in labels)


def test_pins_drawer_renders_cards(window, qapp, tmp_path):
    bridge = window.bridge
    bridge.pin_chat = lambda title, turns: bridge.pins.append(
        {"id": "pinx", "title": title, "at": "now", "count": len(turns)})
    bridge.list_pins = lambda: {"ok": True, "pins": [
        {"id": "pinx", "title": "my chat", "at": "2026-01-01T00:00:00",
         "count": 2}]}
    dialog = QDialog(window)
    dialog.setWindowTitle("Pinned Chats")
    window._pins_dialog = dialog
    window._pins_box = QVBoxLayout(dialog)
    window._render_pins(bridge.list_pins()["pins"])
    labels = [l.text() for l in dialog.findChildren(QLabel)]
    assert "my chat" in " ".join(labels)
    assert "2 messages" in " ".join(labels)
    dialog.close()


class _ApproveDialog:
    Accepted = 1

    def __init__(self, *args, **kwargs):
        self._verdict = True

    def exec(self):
        return self.Accepted

    def verdict(self):
        return self._verdict


class _DenyDialog(_ApproveDialog):
    def __init__(self, *args, **kwargs):
        self._verdict = False