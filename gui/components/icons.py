"""Small programmatic icons (no binary assets needed)."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap


def _canvas(size, fn):
    pm = QPixmap(int(size), int(size))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    fn(p, size)
    p.end()
    return pm


def camera_icon(size=40, color="#16233A"):
    def draw(p, s):
        pen = QPen(QColor(color), s * 0.07, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        body = QRectF(s * 0.12, s * 0.28, s * 0.62, s * 0.46)
        p.drawRoundedRect(body, s * 0.06, s * 0.06)
        lens = QPointF(s * 0.43, s * 0.51)
        p.drawEllipse(lens, s * 0.12, s * 0.12)
        p.drawLine(QPointF(s * 0.74, s * 0.36), QPointF(s * 0.88, s * 0.26))
        p.drawLine(QPointF(s * 0.74, s * 0.62), QPointF(s * 0.88, s * 0.72))
    return _canvas(size, draw)


def pin_icon(size=40, color="#16233A"):
    def draw(p, s):
        pen = QPen(QColor(color), s * 0.06, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.14, s * 0.42, s * 0.3), s * 0.05, s * 0.05)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.56, s * 0.42, s * 0.3), s * 0.05, s * 0.05)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.2, s * 0.3, s * 0.18), s * 0.03, s * 0.03)
    return _canvas(size, draw)


def incognito_icon(size=40, color="#16233A"):
    def draw(p, s):
        pen = QPen(QColor(color), s * 0.075, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.26, s * 0.52, s * 0.4), s * 0.08, s * 0.08)
        p.drawLine(QPointF(s * 0.26, s * 0.30), QPointF(s * 0.66, s * 0.30))
        p.drawLine(QPointF(s * 0.31, s * 0.46), QPointF(s * 0.46, s * 0.46))
        p.drawLine(QPointF(s * 0.56, s * 0.46), QPointF(s * 0.64, s * 0.46))
        p.drawEllipse(QPointF(s * 0.42, s * 0.40), s * 0.05, s * 0.05)
        p.drawEllipse(QPointF(s * 0.56, s * 0.40), s * 0.05, s * 0.05)
    return _canvas(size, draw)


def clock_icon(size=20, color="#3E9B4F"):
    def draw(p, s):
        pen = QPen(QColor(color), s * 0.09, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        center = QPointF(s / 2, s / 2)
        p.drawEllipse(center, s * 0.4, s * 0.4)
        p.drawLine(center, QPointF(s / 2, s * 0.28))
        p.drawLine(center, QPointF(s * 0.64, s * 0.46))
    return _canvas(size, draw)


__all__ = ["camera_icon", "pin_icon", "incognito_icon", "clock_icon"]