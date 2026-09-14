"""Scheduled / reminder panel — upper-left, green rounded border.

Real items come from the existing ``core.scheduler`` TaskStore (the same store
the ARVEN scheduler feature uses). "Add" opens a one-line prompt parsed by the
real ``Scheduler.schedule()`` (natural language: 'remind me to X at 18:00',
'every day at 8am', 'in 30 minutes', ...). There is no fake static data.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from .icons import clock_icon


class SchedulePanel(QFrame):
    add_requested = Signal(str)
    cancel_requested = Signal(str, str)  # (id, description-or-empty)

    def __init__(self, parent=None, add_callback=None, cancel_callback=None):
        super().__init__(parent)
        self.setObjectName("SchedulePanel")
        self._add_cb = add_callback
        self._cancel_cb = cancel_callback

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        icon = QLabel(self)
        icon.setPixmap(clock_icon(20))
        icon.setFixedSize(22, 22)
        head.addWidget(icon)
        title = QLabel("Scheduled:", self)
        title.setObjectName("ScheduleTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.add_btn = QPushButton("+ Add", self)
        self.add_btn.setObjectName("ScheduleAdd")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._ask_add)
        head.addWidget(self.add_btn)
        root.addLayout(head)

        self.rows_widget = QWidget(self)
        self.rows = QVBoxLayout(self.rows_widget)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(6)
        self.rows.addStretch(1)
        root.addWidget(self.rows_widget, 1)

        self.empty_label = QLabel("No scheduled items yet.", self)
        self.empty_label.setObjectName("ScheduleEmpty")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

    # ------------------------------------------------------------------
    def _ask_add(self):
        text, ok = QInputDialog.getText(
            self, "Add scheduled item",
            "Describe it ('remind me to water plants at 18:00' "
            "or 'every day at 8am'):")
        if ok and text.strip():
            self.add_requested.emit(text.strip())
            if self._add_cb:
                self._add_cb(text.strip())

    def set_items(self, items):
        while self.rows.count() > 1:
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        has = bool(items)
        self.empty_label.setVisible(not has)
        self.rows_widget.setVisible(has)
        for index, item in enumerate(items):
            self.rows.insertWidget(index, self._render_row(item))

    def _render_row(self, item):
        text = str(item.get("text") or "").strip() or "task"
        when = str(item.get("time") or "").strip()
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(8)
        num = QLabel(f"{int(item.get('_index', 0)) + 1}.", row)
        num.setObjectName("ScheduleSub")
        lay.addWidget(num)
        body = QLabel(text, row)
        body.setObjectName("ScheduleRow")
        body.setWordWrap(True)
        lay.addWidget(body, 1)
        if when:
            t = QLabel(f"[{when}]", row)
            t.setObjectName("ScheduleRowTime")
            lay.addWidget(t)
        row.setContextMenuPolicy(Qt.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda _pos, task=item, idx=int(item.get('_index', 0)):
            self._cancel(task, idx))
        return row

    def _cancel(self, task, _idx):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        action = menu.addAction("Cancel this reminder")
        chosen = menu.exec(self.mapToGlobal(self.rect().topLeft()))
        if chosen == action:
            task_id = task.get("id")
            self.cancel_requested.emit(str(task_id or ""), "")
            if self._cancel_cb:
                self._cancel_cb(None, task_id)


__all__ = ["SchedulePanel"]