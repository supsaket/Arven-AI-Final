"""Central identity / status area — the large shield + circle emblem.

Preserves the reference's central visual identity and communicates ARVEN state
(idle / listening / thinking / processing / speaking / executing / error) via
the emblem ring and a status caption below it. Subtle, not a sci-fi dashboard.
"""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..emblem import Emblem
from ..styles import PALETTE

_STATE_TEXT = {
    "idle": "Ready",
    "listening": "Listening...",
    "thinking": "Thinking...",
    "processing": "Processing...",
    "speaking": "Speaking...",
    "executing": "Executing...",
    "error": "Error",
}


class CenterPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CenterPanel")
        self._state = "idle"
        self._phase = 0.0
        self._animate = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.view = _EmblemView(self)
        self.view.set_state(self._state, 0.0)
        root.addWidget(self.view, 1)

        self.caption = QLabel(_STATE_TEXT["idle"], self)
        self.caption.setObjectName("StatusWord")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setStyleSheet(
            f"color: {PALETTE['green']}; font-size: 15px; font-weight: 700;")
        root.addWidget(self.caption)

        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    def set_state(self, state, animate=True):
        state = state or "idle"
        self._state = state
        self.caption.setText(_STATE_TEXT.get(state, state.capitalize()))
        active = state not in ("idle", "error") and animate
        self._animate = active
        self._phase = 0.0
        if active and not self._timer.isActive():
            self._timer.start()
        if not active and self._timer.isActive():
            self._timer.stop()
        if not active:
            self._phase = 0.0
        self.view.set_state(state, self._phase if active else 0.0)
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.02) % 1.0
        self.view.set_state(self._state, self._phase)
        self.update()

    def state(self):
        return self._state


class _EmblemView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"
        self._phase = 0.0
        self.setMinimumSize(200, 200)

    def set_state(self, state, phase):
        self._state = state
        self._phase = phase
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        Emblem.paint(p, QRectF(self.rect()), mode="full",
                     state=self._state, phase=self._phase)
        p.end()


__all__ = ["CenterPanel"]