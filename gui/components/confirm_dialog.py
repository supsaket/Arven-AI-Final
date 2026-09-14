"""Confirmation dialog — respects ARVEN's safety/confirmation gate.

Shown when the backend returns ``confirm_required`` for a high-risk capability.
Approve/Deny resolve the real pending CONFIRMATION request before re-running.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)


class ConfirmDialog(QDialog):
    def __init__(self, parent=None, title="Confirmation required",
                 detail="", risk="medium"):
        super().__init__(parent)
        self.setWindowTitle("ARVEN — confirmation")
        self.setModal(True)

        self._verdict = False
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        head = QLabel(self)
        head.setText(title)
        head.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #16233A;")
        layout.addWidget(head)

        risk_label = QLabel(self)
        risk_label.setText(f"Risk level: {str(risk).upper()}")
        risk_label.setStyleSheet("color: #B7840B; font-size: 12px; font-weight: 600;")
        layout.addWidget(risk_label)

        body = QLabel(self)
        body.setText(detail or "This operation requires your approval.")
        body.setWordWrap(True)
        body.setStyleSheet("color: #1B2733; font-size: 13px;")
        layout.addWidget(body)

        note = QLabel(self)
        note.setText("Approving keeps ARVEN's normal safety gate intact.")
        note.setStyleSheet("color: #5B6B7C; font-size: 11px; font-style: italic;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.deny = QPushButton("Deny", self)
        self.deny.setObjectName("DenyButton")
        self.approve = QPushButton("Approve", self)
        self.approve.setObjectName("OkButton")
        buttons.addWidget(self.deny)
        buttons.addWidget(self.approve)
        layout.addLayout(buttons)

        self.deny.clicked.connect(self._deny)
        self.approve.clicked.connect(self._approve)
        self.setMinimumWidth(360)

    def _deny(self):
        self._verdict = False
        self.accept()

    def _approve(self):
        self._verdict = True
        self.accept()

    def verdict(self):
        return self._verdict


__all__ = ["ConfirmDialog"]