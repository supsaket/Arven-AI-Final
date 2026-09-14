"""MainWindow — the ARVEN desktop interface.

Implements the reference wireframe composition using normalized regions that
preserve the exact relative placement and proportions at any window size:

    top-left      identity (badge + ARVEN) + live clock / status
    top-right     window controls (min / max / close)
    upper-left    Scheduled/Reminder panel (green border)
    center        large shield + circle emblem (ARVEN states)
    right side    vertical INC / Camera / Pinned Chats controls
    lower-left    Image/Video or profile panel + Re-upload / Download / Maximize
    lower-right   chatbox (scroll, input, "+")

All backend work runs through ArvenBridge on the worker pool — never on the UI
thread. Everything realised from the existing ARVEN system; nothing faked.
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLayout,
                               QLayoutItem, QMainWindow,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .bridge import ArvenBridge
from .components import (ChatPanel, CenterPanel, ConfirmDialog, MediaPanel,
                         RightControls, SchedulePanel, TitleBar)
from .workers import BackendBus
from .styles import PALETTE

# ---------------------------------------------------------------- reference
# Normalised regions from the reference image (1448x1086). Disjoint by design
# so components never overlap at any size.
REFERENCE = {
    "titlebar": (0.045, 0.040, 0.300, 0.160),
    "controls": (0.760, 0.035, 0.200, 0.070),
    "schedule": (0.075, 0.240, 0.220, 0.200),
    "side": (0.900, 0.130, 0.065, 0.270),
    "emblem": (0.330, 0.300, 0.340, 0.260),
    "media": (0.055, 0.600, 0.480, 0.360),
    "chat": (0.720, 0.585, 0.240, 0.375),
}

_EDGE = 7  # px of frameless resize zone around the window


class _WidgetItem(QLayoutItem):
    """Wrap a widget as a QLayoutItem for ReferenceLayout."""

    def __init__(self, widget):
        super().__init__()
        self._widget = widget

    def widget(self):
        return self._widget

    def sizeHint(self):
        return self._widget.sizeHint()

    def minimumSize(self):
        return self._widget.minimumSize()

    def maximumSize(self):
        return self._widget.maximumSize()

    def setGeometry(self, rect):
        self._widget.setGeometry(rect)

    def isEmpty(self):
        return False


class ReferenceLayout(QLayout):
    """Places children by normalised rectangles (proportional everywhere)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def place(self, widget, region):
        item = _WidgetItem(widget)
        self._items.append((item, QRectF(*region)))
        widget.setParent(self.parentWidget())
        return item

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index][0]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)[0]
        return None

    def addItem(self, item):
        self._items.append((item, QRectF(0, 0, 1, 1)))

    def setGeometry(self, rect):
        super().setGeometry(rect)
        for item, norm in self._items:
            widget = item.widget()
            if widget is None:
                continue
            x = rect.x() + norm.x() * rect.width()
            y = rect.y() + norm.y() * rect.height()
            wd = norm.width() * rect.width()
            ht = norm.height() * rect.height()
            widget.setGeometry(int(x), int(y), int(wd), int(ht))

    def sizeHint(self):
        if self.parentWidget():
            return self.parentWidget().size()
        return super().sizeHint()

    def minimumSize(self):
        if self.parentWidget():
            return self.parentWidget().minimumSize()
        return super().minimumSize()

    def expandingDirections(self):
        return Qt.Horizontal | Qt.Vertical


# ---------------------------------------------------------------- main
class MainWindow(QMainWindow):
    closed = Signal()

    def __init__(self, bridge=None, bus=None):
        super().__init__()
        self.bridge = bridge or ArvenBridge()
        self.bus = bus or BackendBus()

        self._incognito = False
        self._voice_replies = False
        self._pins_dialog = None

        self.setWindowTitle("ARVEN AI")
        self.setMinimumSize(920, 640)
        self.resize(1280, 900)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setObjectName("ReferenceRoot")

        self.central = QWidget(self)
        self.central.setObjectName("ReferenceRoot")
        self.setCentralWidget(self.central)
        self.layout = ReferenceLayout(self.central)
        self.central.setLayout(self.layout)

        self._build_components()
        self._wire()

        self.chat.add_system(
            "ARVEN GUI online — routed through the existing ARVEN backend. "
            "Ask for any of the registered capabilities or just chat.")

    # ------------------------------------------------------------------
    def _build_components(self):
        self.titlebar = TitleBar(self.central, on_min=self.showMinimized,
                                 on_max=self.toggle_maximize,
                                 on_close=self.close)

        controls = QWidget(self.central)
        ctrl_lay = QHBoxLayout(controls)
        ctrl_lay.setContentsMargins(0, 0, 0, 0)
        ctrl_lay.addStretch(1)
        for btn in (self.titlebar.min_btn, self.titlebar.max_btn,
                    self.titlebar.close_btn):
            ctrl_lay.addWidget(btn)
        self.controls = controls

        self.schedule = SchedulePanel(
            self.central, add_callback=self._schedule_add,
            cancel_callback=self._schedule_cancel)
        self.center = CenterPanel(self.central)
        self.side = RightControls(self.central, callbacks={
            "camera": self._camera_action,
            "pinned": self._pinned_drawer,
        })
        self.media = MediaPanel(self.central, callbacks={
            "reupload": self._reupload,
        })
        self.chat = ChatPanel(self.central, callbacks={
            "send": self._submit_text,
            "plus": self._plus_action,
        })

        self.layout.place(self.titlebar, REFERENCE["titlebar"])
        self.layout.place(self.controls, REFERENCE["controls"])
        self.layout.place(self.schedule, REFERENCE["schedule"])
        self.layout.place(self.side, REFERENCE["side"])
        self.layout.place(self.center, REFERENCE["emblem"])
        self.layout.place(self.media, REFERENCE["media"])
        self.layout.place(self.chat, REFERENCE["chat"])

    def _wire(self):
        self.side.incognito_toggled.connect(self._set_incognito)

        self.bus.started.connect(self._bus_started)
        self.bus.finished.connect(self._bus_finished)
        self.bus.failed.connect(self._bus_failed)

        self._refresh_schedule()
        self._refresh_media()

    def showEvent(self, event):
        super().showEvent(event)
        self.titlebar.tick()

    # ------------------------------------------------------------- drag/resize
    def start_window_move(self):
        handle = self.windowHandle()
        if handle is None:
            return
        try:
            handle.startSystemMove()
        except Exception:
            pass

    def _edge(self, pos):
        w, h = self.width(), self.height()
        if pos.x() <= _EDGE:
            return Qt.LeftEdge
        if pos.x() >= w - _EDGE:
            return Qt.RightEdge
        if pos.y() <= _EDGE:
            return Qt.TopEdge
        if pos.y() >= h - _EDGE:
            return Qt.BottomEdge
        return 0

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._edge(event.position())
            if edge:
                try:
                    self.windowHandle().startSystemResize(edge)
                except Exception:
                    pass
                event.accept()
                return
            if event.position().y() <= 120:
                self.start_window_move()
                event.accept()
                return
        super().mousePressEvent(event)

    # ------------------------------------------------------------- controls
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # --------------------------------------------------------------- states
    _KIND_STATE = {
        "send": "thinking",
        "voice": "listening",
        "tts": "speaking",
        "cam_screen": "executing",
        "cam_photo": "executing",
        "cam_perm": "processing",
        "img": "processing",
        "file": "executing",
        "sched": "processing",
        "pins": "processing",
        "media": "processing",
        "health": "processing",
    }

    def _bus_started(self, kind):
        state = self._KIND_STATE.get(kind, "processing")
        self.center.set_state(state)
        self.titlebar.set_status(state)

    def _bus_failed(self, kind, message):
        self.center.set_state("idle")
        self.titlebar.set_status("idle")
        self.chat.add_system(f"Backend error: {message}")

    def _set_idle(self):
        self.center.set_state("idle")
        self.titlebar.set_status("idle")

    # ------------------------------------------------------------- send flow
    def _submit_text(self, text, approve=False):
        text = str(text or "").strip()
        if not text:
            return
        self.chat.add_message("user", text)
        payload = {"text": text, "incognito": self._incognito,
                   "approve": approve}
        self._pending = payload
        self.bus.start("send", lambda p=payload: self.bridge.send(
            p["text"], approve=p["approve"], incognito=p["incognito"]))

    def _handle_send(self, result):
        if result.get("confirm") and result.get("request_id"):
            self.chat.add_system(
                f"Confirmation required for '{result.get('title')}'.")
            dialog = ConfirmDialog(
                self,
                title=f"Approve: {result.get('title') or 'task'}",
                detail=str(result.get("text") or ""),
                risk=self._risk_of(result))
            if dialog.exec() == dialog.Accepted and dialog.verdict():
                rid = result["request_id"]

                def resolve(rid=rid, res=result):
                    self.bridge.confirm(rid, "yes")
                    return self._resolve_approved(res)

                self.bus.start("send", resolve)
                return
            rid = result["request_id"]
            self.bridge.confirm(rid, "no")
            self.chat.add_system(f"Declined — {result.get('title')} was not run.")
            self._set_idle()
            return

        text = result.get("text") or "ARVEN is listening, Boss."
        meta = result.get("status") or result.get("source") or ""
        self.chat.add_message("assistant", text, meta=meta)
        self._set_idle()
        if self._voice_replies and result.get("ok"):
            self.bus.start("tts", lambda t=text: self.bridge.speak(t))

    def _risk_of(self, result):
        data = result.get("data")
        if isinstance(data, dict):
            risk = data.get("risk") or data.get("risk_level")
            if risk:
                return risk
        return "high"

    def _resolve_approved(self, original):
        pending = getattr(self, "_pending", None)
        if pending and pending.get("text"):
            text = pending["text"]
            incognito = pending.get("incognito", original.get("incognito"))
            return self.bridge.send(text, approve=True, incognito=incognito)
        return self.bridge.send(
            original["text"], approve=True, incognito=original["incognito"])

    # ---------------------------------------------------------- incognito
    def _set_incognito(self, active):
        self._incognito = bool(active)
        self.chat.set_incognito(self._incognito)
        self.chat.add_system(
            "Incognito ON — this conversation is not persisted and ARVEN's "
            "audit for these turns is kept in memory only."
            if self._incognito else
            "Incognito OFF.")

    # ------------------------------------------------------------- schedule
    def _refresh_schedule(self):
        self.bus.start("sched", lambda: self.bridge.scheduled_items())

    def _schedule_add(self, text):
        self.bridge.add_scheduled(text)
        self._refresh_schedule()

    def _schedule_cancel(self, description, task_id):
        self.bridge.cancel_scheduled(text=description or None, task_id=task_id)
        self._refresh_schedule()

    # --------------------------------------------------------------- media
    def _refresh_media(self):
        self.bus.start("media", lambda: self.bridge.latest_media())

    def _reupload(self, path):
        self.chat.add_message("user", f"Attached file: {path}")
        self.bus.start("file", lambda p=path: self.bridge.read_file(p))

    # ------------------------------------------------------------- actions
    def _plus_action(self, kind):
        if kind == "file":
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, "Attach a file", "", "All files (*)")
            if path:
                self._reupload(path)
        elif kind == "camera":
            self._camera_action()
        elif kind == "image":
            from PySide6.QtWidgets import QInputDialog
            prompt, ok = QInputDialog.getText(
                self, "Generate image", "Prompt:")
            if ok and prompt.strip():
                self.bus.start(
                    "img", lambda p=prompt: self.bridge.generate_image(p))
        elif kind == "calc":
            from PySide6.QtWidgets import QInputDialog
            expr, ok = QInputDialog.getText(
                self, "Calculate", "Expression (e.g. 12*6):")
            if ok and expr.strip():
                self._submit_text(f"calculate {expr.strip()}")
        elif kind == "voice":
            self.bus.start("voice", lambda: self.bridge.transcribe(5))
        elif kind == "tts":
            self._voice_replies = not self._voice_replies
            self.chat.add_system(
                f"Voice replies: {'ON' if self._voice_replies else 'OFF'}")

    def _camera_action(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        screen = menu.addAction("Capture screen (real screen_capture)")
        photo = menu.addAction("Camera photo (permission + cv2 required)")
        grant = menu.addAction("Grant camera permission")
        chosen = menu.exec(self.mapToGlobal(
            self.side.cam_btn.rect().bottomRight()))
        if chosen == screen:
            self.bus.start("cam_screen", lambda: self.bridge.capture_screen())
        elif chosen == photo:
            self.bus.start("cam_photo", lambda: self.bridge.camera_capture())
        elif chosen == grant:
            self.bus.start("cam_perm", lambda: self.bridge.grant_camera())

    # ---------------------------------------------------------------- pins
    def _pinned_drawer(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Pinned Chats")
        dialog.resize(440, 480)
        lay = QVBoxLayout(dialog)

        head = QHBoxLayout()
        title = QLabel("Pinned Chats", dialog)
        title.setStyleSheet(
            f"color: {PALETTE['navy']}; font-size: 16px; font-weight: 700;")
        head.addWidget(title)
        head.addStretch(1)
        self._pin_now_btn = QPushButton("+ Pin this chat", dialog)
        self._pin_now_btn.setObjectName("ScheduleAdd")
        self._pin_now_btn.setCursor(Qt.PointingHandCursor)
        self._pin_now_btn.clicked.connect(self._pin_now)
        head.addWidget(self._pin_now_btn)
        lay.addLayout(head)

        self._pins_box = QVBoxLayout()
        lay.addLayout(self._pins_box, 1)

        close = QPushButton("Close", dialog)
        close.setObjectName("DenyButton")
        close.clicked.connect(dialog.accept)
        lay.addWidget(close)

        self._pins_dialog = dialog
        self._refresh_pins()
        dialog.exec()

    def _refresh_pins(self):
        self.bus.start("pins", lambda: self.bridge.list_pins())

    def _render_pins(self, pins):
        dialog = self._pins_dialog
        if dialog is None:
            return
        while self._pins_box.count():
            item = self._pins_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not pins:
            lbl = QLabel("No pinned chats yet. Use '+ Pin this chat'.", dialog)
            lbl.setStyleSheet(f"color: {PALETTE['muted']};")
            lbl.setWordWrap(True)
            self._pins_box.addWidget(lbl)
            self._pins_box.addStretch(1)
            return
        for pin in pins:
            card = QWidget(dialog)
            card_lay = QVBoxLayout(card)
            t = QLabel(str(pin.get("title") or "Pinned chat"), card)
            t.setStyleSheet(f"color: {PALETTE['ink']}; font-weight: 600;")
            card_lay.addWidget(t)
            m = QLabel(
                f"{pin.get('count')} messages · {str(pin.get('at'))[:19]}", card)
            m.setStyleSheet(f"color: {PALETTE['muted']}; font-size: 11px;")
            card_lay.addWidget(m)
            btns = QHBoxLayout()
            open_btn = QPushButton("Open", card)
            open_btn.setObjectName("MediaButton")
            del_btn = QPushButton("Delete", card)
            del_btn.setObjectName("DenyButton")
            open_btn.clicked.connect(
                lambda _=False, pid=pin.get("id"): self._open_pin(pid))
            del_btn.clicked.connect(
                lambda _=False, pid=pin.get("id"): self._delete_pin(pid))
            btns.addWidget(open_btn)
            btns.addWidget(del_btn)
            btns.addStretch(1)
            card_lay.addLayout(btns)
            self._pins_box.addWidget(card)
        self._pins_box.addStretch(1)

    def _pin_now(self):
        turns = self.chat.turns()
        if not turns:
            QMessageBox.information(self, "Pin", "The chat is empty.")
            return
        title = str(turns[0].get("text", "") or "")[:42] or "Pinned chat"
        self.bridge.pin_chat(title, turns)
        self._refresh_pins()

    def _open_pin(self, pin_id):
        payload = self.bridge.load_pin(pin_id)
        if payload.get("ok"):
            self._pins_dialog.accept()
            self._pins_dialog = None
            self.chat.set_conversation(payload.get("turns", []))
            self.chat.add_system(
                f"Restored pinned chat: {payload.get('title')}")

    def _delete_pin(self, pin_id):
        self.bridge.remove_pin(pin_id)
        self._refresh_pins()

    # ------------------------------------------------------------- dispatch
    def _bus_finished(self, kind, payload):
        try:
            if kind == "send":
                self._handle_send(payload)
            elif kind == "voice":
                self._handle_voice(payload)
            elif kind == "tts":
                self._handle_tts(payload)
            elif kind in ("cam_screen", "cam_photo", "cam_perm"):
                self._handle_camera(kind, payload)
            elif kind == "img":
                self._handle_image(payload)
            elif kind == "file":
                self._handle_file(payload)
            elif kind == "sched":
                self._handle_sched(payload)
            elif kind == "media":
                self._handle_media(payload)
            elif kind == "pins":
                self._handle_pins(payload)
            elif kind == "health":
                self._handle_health(payload)
        except Exception as exc:  # pragma: no cover - defensive
            self.chat.add_system(f"UI error: {exc}")

    def _handle_voice(self, payload):
        if not payload.get("success"):
            self._set_idle()
            self.chat.add_system(
                payload.get("message") or "Voice input unavailable.")
            return
        text = str(payload.get("text") or "").strip()
        if not text:
            self._set_idle()
            self.chat.add_system("No speech detected.")
            return
        self._submit_text(text)

    def _handle_tts(self, payload):
        if payload and not payload.get("success"):
            self.chat.add_system(
                str(payload.get("message") or "TTS unavailable."))

    def _handle_camera(self, kind, payload):
        self._set_idle()
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        ok = bool(payload.get("success"))
        message = payload.get("message") or payload.get("status") or "done"
        path = result.get("path") or (payload.get("path") if isinstance(payload.get("path"), str) else None)
        if ok and path:
            self.media.show_image(path)
            self.chat.add_message("assistant", f"Captured: {path}", meta=kind)
        else:
            self.chat.add_system(f"{kind}: {message}")
            self.chat.add_message("assistant", message, meta=kind)

    def _handle_image(self, payload):
        self._set_idle()
        if payload.get("ok") and payload.get("path"):
            self.media.show_image(payload["path"])
            self.chat.add_message(
                "assistant", f"Generated image: {payload['path']}", meta="image_generate")
        else:
            self.chat.add_message(
                "assistant",
                payload.get("message")
                or "Image generation unavailable (set IMAGE_GENERATION_PROVIDER).",
                meta=payload.get("status") or "image_generate")

    def _handle_file(self, payload):
        if bool(payload.get("success")):
            content = payload.get("content") or ""
            path = payload.get("path") or "?"
            preview = str(content)[:200] or "(empty file)"
            self.chat.add_message(
                "assistant",
                f"Read {path}: {payload.get('content_length', len(content))} "
                f"chars. Preview: {preview}", meta="read_file")
        else:
            self.chat.add_system(
                f"File: {payload.get('message') or 'failed'}")

    def _handle_sched(self, payload):
        self._set_idle()
        items = payload.get("items", [])
        for idx, item in enumerate(items):
            item["_index"] = idx
        self.schedule.set_items(items)

    def _handle_media(self, payload):
        if payload.get("ok"):
            self.media.show_image(payload["path"])

    def _handle_pins(self, payload):
        if payload.get("ok"):
            self._render_pins(payload.get("pins", []))

    def _handle_health(self, payload):
        self.titlebar.set_status(payload.get("worst", "idle"))


__all__ = ["MainWindow", "ReferenceLayout"]