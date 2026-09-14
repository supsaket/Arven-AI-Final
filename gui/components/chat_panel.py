"""Chatbox — lower-right, matching the reference proportions.

Real conversation, working vertical scrollbar, bottom input with a "+"
attachment/action button. Enter sends. The "+" opens actions that connect to
real ARVEN capabilities (attach file, camera, generate image, calculator).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QScrollArea, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from ..styles import PALETTE


class ChatPanel(QFrame):
    send_requested = Signal(str)
    plus_action = Signal(str)  # kind: 'file' | 'camera' | 'image' | 'calc'

    def __init__(self, parent=None, callbacks=None):
        super().__init__(parent)
        self.setObjectName("ChatPanel")
        callbacks = callbacks or {}
        self._incognito = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Chat", self)
        title.setObjectName("PanelTitle")
        head.addWidget(title)
        self.inc_tag = QLabel("Incognito", self)
        self.inc_tag.setObjectName("IncognitoTag")
        self.inc_tag.setVisible(False)
        head.addWidget(self.inc_tag)
        head.addStretch(1)
        root.addLayout(head)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("ChatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content = QWidget(self.scroll)
        self.messages = QVBoxLayout(self.content)
        self.messages.setContentsMargins(4, 4, 4, 4)
        self.messages.setSpacing(8)
        self.messages.addStretch(1)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.plus_btn = QToolButton(self)
        self.plus_btn.setObjectName("ChatPlus")
        self.plus_btn.setText("+")
        self.plus_btn.setCursor(Qt.PointingHandCursor)
        self.plus_btn.setToolTip("Attach / actions")
        input_row.addWidget(self.plus_btn)
        self.input = QLineEdit(self)
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Type a message...")
        input_row.addWidget(self.input, 1)
        root.addLayout(input_row)

        self.plus_btn.clicked.connect(self._plus_menu)

        # --- wiring -----------------------------------------------------
        if callbacks.get("send"):
            self.send_requested.connect(lambda t: self._run(callbacks["send"], t))
        if callbacks.get("plus"):
            self.plus_action.connect(lambda k: self._run(callbacks["plus"], k))

    def _run(self, fn, *args):
        try:
            fn(*args)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_enter(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_requested.emit(text)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.input.hasFocus():
            self._on_enter()
            event.accept()
            return
        super().keyPressEvent(event)

    def _plus_menu(self):
        menu = QMenu(self)
        actions = {
            "Attach file...": "file",
            "Camera / capture": "camera",
            "Generate image": "image",
            "Calculator / tool": "calc",
        }
        mapping = {}
        for label, kind in actions.items():
            mapping[menu.addAction(label)] = kind
        chosen = menu.exec(self.mapToGlobal(
            self.plus_btn.rect().bottomLeft()))
        if chosen in mapping:
            self.plus_action.emit(mapping[chosen])

    # ------------------------------------------------------------------
    def add_message(self, role, text, meta=""):
        text = str(text or "").strip()
        if not text:
            return
        bubble = QFrame(self.content)
        is_user = role == "user"
        bubble.setObjectName("UserBubble" if is_user else "AssistantBubble")
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

        lay = QVBoxLayout(bubble)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        body = QLabel(text, bubble)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        lay.addWidget(body)
        if meta:
            m = QLabel(meta, bubble)
            m.setObjectName("ChatMeta")
            lay.addWidget(m)

        row = QWidget(self.content)
        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        if is_user:
            h.addStretch(1)
            h.addWidget(bubble, 0)
        else:
            h.addWidget(bubble, 0)
            h.addStretch(1)

        self.messages.insertWidget(self.messages.count() - 1, row)
        self._scroll_bottom()

    def add_system(self, text):
        row = QWidget(self.content)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        note = QLabel(str(text), row)
        note.setObjectName("ChatSystem")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        lay.addWidget(note)
        self.messages.insertWidget(self.messages.count() - 1, row)
        self._scroll_bottom()

    def set_conversation(self, turns):
        while self.messages.count() > 1:
            item = self.messages.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for turn in turns or []:
            self.add_message(turn.get("role", "assistant"),
                             turn.get("text", ""))
        self._scroll_bottom()

    def turns(self):
        out = []
        count = self.messages.count()
        for index in range(count):
            item = self.messages.itemAt(index)
            widget = item.widget() if item and item.widget() else None
            if widget is None:
                continue
            role = "assistant"
            text = ""
            for bubble in widget.findChildren(QFrame):
                if bubble.objectName() in ("UserBubble", "AssistantBubble"):
                    role = "user" if bubble.objectName() == "UserBubble" \
                        else "assistant"
                    for label in bubble.findChildren(QLabel):
                        if label.objectName() == "":
                            text = label.text()
            if text:
                out.append({"role": role, "text": text})
        return out

    def clear_chat(self):
        self.set_conversation([])

    def _scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_incognito(self, active):
        self._incognito = bool(active)
        self.inc_tag.setVisible(self._incognito)


__all__ = ["ChatPanel"]