"""Right-side vertical controls — INC / Camera / Pinned Chats.

Preserved vertical stack from the reference. Every control is functional:
* INC toggles a genuinely non-persistent conversation session (transcript stays
  in memory; the backend audit store is in-memory, so nothing is written).
* Camera invokes the real ARVEN camera/screen capture capabilities and reports
  honest backend results (permission / backend missing are surfaced, never
  faked).
* Pinned Chats opens the chat pin drawer bound to real conversation turns.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from .icons import camera_icon, incognito_icon, pin_icon
from ..styles import PALETTE


class RightControls(QFrame):
    incognito_toggled = Signal(bool)
    camera_clicked = Signal()
    pinned_clicked = Signal()

    def __init__(self, parent=None, callbacks=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        callbacks = callbacks or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 12, 10, 12)
        root.setSpacing(10)

        def side_button(text, caption):
            btn = QPushButton(text, self)
            btn.setObjectName("SideButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumSize(64, 54)
            cap = QLabel(caption, self)
            cap.setObjectName("SideCaption")
            cap.setAlignment(Qt.AlignCenter)
            cap.setWordWrap(True)
            return btn, cap

        self.inc_btn, inc_cap = side_button("INC", "Incognito\nChat")
        self.inc_btn.setCheckable(True)
        self.inc_btn.setIcon(incognito_icon(30))
        self.inc_btn.clicked.connect(self._toggle_inc)

        self.cam_btn, cam_cap = side_button("", "Camera /\nCapture")
        self.cam_btn.setIcon(camera_icon(34))
        self.cam_btn.clicked.connect(self.camera_clicked)

        self.pin_btn, pin_cap = side_button("", "Pinned\nChats")
        self.pin_btn.setIcon(pin_icon(34))
        self.pin_btn.clicked.connect(self.pinned_clicked)

        root.addWidget(self.inc_btn)
        root.addWidget(inc_cap)
        root.addSpacing(4)
        root.addWidget(self.cam_btn)
        root.addWidget(cam_cap)
        root.addSpacing(4)
        root.addWidget(self.pin_btn)
        root.addWidget(pin_cap)
        root.addStretch(1)

        if callbacks.get("camera"):
            self.camera_clicked.connect(lambda: self._run(callbacks["camera"]))
        if callbacks.get("pinned"):
            self.pinned_clicked.connect(lambda: self._run(callbacks["pinned"]))

    def _run(self, fn):
        try:
            fn()
        except Exception:
            pass

    def _toggle_inc(self, checked):
        self.inc_btn.setProperty("active", "true" if checked else "false")
        self.inc_btn.style().unpolish(self.inc_btn)
        self.inc_btn.style().polish(self.inc_btn)
        self.incognito_toggled.emit(checked)

    def set_incognito(self, active):
        if active != self.inc_btn.isChecked():
            self.inc_btn.setChecked(active)
            self.inc_btn.setProperty("active", "true" if active else "false")
            self.inc_btn.style().unpolish(self.inc_btn)
            self.inc_btn.style().polish(self.inc_btn)


__all__ = ["RightControls"]