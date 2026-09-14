"""ARVEN emblem — programmatic QPainter implementation of the reference logo.

The reference (``Downloads/logo design.jpeg``) is a dark sheet with a light
emblem: a stylised two-stroke "A" peak above a circular motif inside a wider
trapezoid/shield form, with the lockup text at the bottom. ``gui design.jpeg``
places a small circular badge beside the ``ARVEN`` wordmark and a LARGE outer
shield + circle as the central visual identity.

This module draws the emblem without any image assets, so the GUI stays fully
self-contained and removable.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QBrush, QPolygonF

# ---------------------------------------------------------------- palette ---
NAVY = QColor("#16233A")          # emblem primary (matches dark logo sheet)
NAVY_LIGHT = QColor("#2C4258")
SILVER = QColor("#C9D4E0")        # stroke highlight
SILVER_DIM = QColor("#9FB0C3")
GREEN = QColor("#3E9B4F")         # schedule accent
BG = QColor("#F2F4F7")
PANEL = QColor("#FFFFFF")
INK = QColor("#1B2733")
MUTED = QColor("#5B6B7C")


class Emblem:
    """Paint the ARVEN emblem into ``rect``.

    ``mode``:
      * 'badge'  — small circular badge for the top-left wordmark
      * 'full'   — large central shield + circle identity
    ``state``   — 'idle' | 'listening' | 'thinking' | 'speaking' |
                  'executing' | 'error'  (drives the outer ring colour)
    ``phase``   — 0..1 animation phase (0 disables pulsing)
    """

    STATE_RING = {
        "idle": ("#9FB0C3", 1.0),
        "listening": ("#3E9B4F", 2.0),
        "thinking": ("#D9A13E", 1.5),
        "speaking": ("#4F8FD9", 1.5),
        "executing": ("#D9A13E", 1.5),
        "error": ("#C0392B", 1.0),
    }

    @staticmethod
    def paint(painter, rect, mode="badge", state="idle", phase=0.0):
        painter.setRenderHint(QPainter.Antialiasing, True)

        if mode == "badge":
            Emblem._badge(painter, rect, state, phase)
        else:
            Emblem._shield(painter, rect, state, phase)

    # ------------------------------------------------------------------
    @staticmethod
    def _circle_badge(painter, cx, cy, outer_r, state):
        ring_col, ring_w = Emblem.STATE_RING.get(state, Emblem.STATE_RING["idle"])
        painter.setPen(QPen(QColor(ring_col), max(2.0, outer_r * 0.10)))
        painter.setBrush(QBrush(NAVY))
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        painter.setPen(QPen(QColor("#F2F4F7"), max(1.0, outer_r * 0.045)))
        painter.setBrush(Qt.NoBrush)
        inner = outer_r * 0.62
        painter.drawEllipse(QPointF(cx, cy), inner, inner)

        # central stylised "A"
        size = outer_r * 0.74
        top = QPointF(cx, cy - size * 0.7)
        bl = QPointF(cx - size * 0.62, cy + size * 0.62)
        br = QPointF(cx + size * 0.62, cy + size * 0.62)
        painter.setPen(QPen(QColor("#F2F4F7"), max(1.5, outer_r * 0.07),
                            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(top, bl)
        painter.drawLine(top, br)
        cross_l = QPointF(cx - size * 0.19, cy + size * 0.12)
        cross_r = QPointF(cx + size * 0.19, cy + size * 0.12)
        painter.drawLine(cross_l, cross_r)

    @staticmethod
    def _badge(painter, rect, state, phase):
        r = min(rect.width(), rect.height()) / 2.0
        cx, cy = rect.center().x(), rect.center().y()
        if phase:
            glow = 0.7 + 0.3 * phase
            painter.setPen(QPen(QColor(Emblem.STATE_RING.get(
                state, Emblem.STATE_RING["idle"])[0]), r * 0.12))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r * 1.28 * glow, r * 1.28 * glow)
        Emblem._circle_badge(painter, cx, cy, r * 0.94, state)

    # ------------------------------------------------------------------
    @staticmethod
    def _shield(painter, rect, state, phase):
        cx, cy = rect.center().x(), rect.center().y()
        w, h = rect.width(), rect.height()
        ring_col, ring_w = Emblem.STATE_RING.get(state, Emblem.STATE_RING["idle"])
        pulse = max(0.98, 1.0 + 0.06 * phase) if phase else 1.0

        # outer state ring (communication ring) — always present, honours state
        ring_r = min(w, h) * 0.47 * pulse
        painter.setPen(QPen(QColor(ring_col), max(2.0, w * 0.010)))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # outer shield / trapezoid form (dark navy, silver trim)
        tw, th = w * 0.64, h * 0.86
        top_y = cy - th * 0.10
        bottom_y = cy + th * 0.78
        shield = QPolygonF([
            QPointF(cx - tw * 0.5, top_y),
            QPointF(cx + tw * 0.5, top_y),
            QPointF(cx + tw * 0.62, bottom_y),
            QPointF(cx, bottom_y + th * 0.22),
            QPointF(cx - tw * 0.62, bottom_y),
        ])
        path = QPainterPath()
        path.addPolygon(shield)
        path.closeSubpath()
        painter.fillPath(path, QBrush(NAVY))
        painter.setPen(QPen(QColor(SILVER), max(2.0, w * 0.012)))
        painter.drawPath(path)

        # inside the shield: the large circular center
        circle_r = min(w, h) * 0.285
        circle_cent = QPointF(cx, cy + th * 0.16)
        painter.setPen(QPen(QColor(NAVY_LIGHT), max(2.0, w * 0.008)))
        painter.setBrush(QBrush(NAVY_LIGHT))
        painter.drawEllipse(circle_cent, circle_r, circle_r)
        painter.setPen(QPen(QColor("#F2F4F7"), max(1.5, w * 0.006)))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(circle_cent, circle_r * 0.80, circle_r * 0.80)

        Emblem._circle_badge(painter, circle_cent.x(), circle_cent.y(),
                             circle_r * 0.66, state)


__all__ = ["Emblem"]