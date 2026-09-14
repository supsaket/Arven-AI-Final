"""Title bar — ARVEN identity + live clock + window controls.

Matches the reference top section: small circular badge + ARVEN wordmark on the
left, dynamic time/status beneath it, and minimise/maximize/close at the top
right (a real frameless desktop window).
"""

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..emblem import Emblem
from ..styles import PALETTE


class _Badge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self._phase = 0.0

    def splash(self):
        if not hasattr(self, "_timer"):
            self._timer = QTimer(self)
            self._timer.setInterval(40)
            self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._phase = self._phase + 0.04 if self._phase < 1.0 else 0.0
        self.update()
        if self._phase == 0.0:
            self._timer.stop()

    def paintEvent(self, _event):
        p = self._painter()
        phase = self._phase
        Emblem.paint(p, QRectF(self.rect()), mode="badge", state="idle",
                     phase=phase if phase else 0.0)
        p.end()

    def _painter(self):
        from PySide6.QtGui import QPainter
        return QPainter(self)


class TitleBar(QFrame):
    class Signals(QWidget):
        pass

    def __init__(self, parent=None, on_min=None, on_max=None, on_close=None):
        super().__init__(parent)
        self.setObjectName("TitleStrip")
        self.setMouseTracking(True)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        left = QWidget(self)
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(0, 0, 0, 0)
        lcol.setSpacing(2)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        self.badge = _Badge(left)
        self.badge.splash()
        brand_row.addWidget(self.badge)
        self.brand = QLabel("ARVEN", left)
        self.brand.setObjectName("BrandName")
        self.brand.setAlignment(Qt.AlignVCenter)
        brand_row.addWidget(self.brand)
        brand_row.addStretch(1)
        lcol.addLayout(brand_row)

        clock_row = QHBoxLayout()
        clock_row.setSpacing(10)
        self.time_label = QLabel("", left)
        self.time_label.setObjectName("ClockTime")
        clock_row.addWidget(self.time_label)
        self.date_label = QLabel("", left)
        self.date_label.setObjectName("ClockDate")
        clock_row.addWidget(self.date_label)
        clock_row.addSpacing(14)
        self.status_label = QLabel("idle", left)
        self.status_label.setObjectName("StatusWord")
        clock_row.addWidget(self.status_label)
        clock_row.addStretch(1)
        lcol.addLayout(clock_row)

        root.addWidget(left)
        root.addStretch(1)

        self.min_btn = QPushButton("\u2500", self)
        self.min_btn.setObjectName("WinButton")
        self.min_btn.setToolTip("Minimize")
        self.max_btn = QPushButton("\u25a1", self)
        self.max_btn.setObjectName("WinButton")
        self.max_btn.setToolTip("Maximize / Restore")
        self.close_btn = QPushButton("\u2715", self)
        self.close_btn.setObjectName("WinButton")
        self.close_btn.setProperty("destructive", True)
        self.close_btn.setToolTip("Close")

        controls = QHBoxLayout()
        controls.setSpacing(4)
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFixedSize(34, 26)
            controls.addWidget(btn)
        root.addLayout(controls)

        self.min_btn.clicked.connect(on_min if on_min else lambda: None)
        self.max_btn.clicked.connect(on_max if on_max else lambda: None)
        self.close_btn.clicked.connect(on_close if on_close else lambda: None)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.tick)
        self._clock.start()

    # ------------------------------------------------------------------
    def tick(self):
        from datetime import datetime
        now = datetime.now()
        meridiem = "am" if now.hour < 12 else "pm"
        hour12 = now.hour % 12 or 12
        self.time_label.setText(f"{hour12}:{now.minute:02d} {meridiem}")
        self.date_label.setText(now.strftime("%A, %d %b %Y"))

    def set_status(self, status):
        self.status_label.setText(str(status or "idle").capitalize())


class _DragArea(QWidget):
    """A transparent, mouse-grab-allowed strip used for window dragging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            win = self.window()
            if hasattr(win, "start_window_move"):
                win.start_window_move()


def build_drag_strip(parent):
    strip = _DragArea(parent)
    strip.setFixedHeight(10)
    return strip


__all__ = ["TitleBar", "build_drag_strip"]