"""Media / profile panel — lower-left.

Per the reference: "Image/Video area if generator and if not then have
profile". Driving content is real:
* When ARVEN has generated media (Output/ImageGeneration, GeneratedImages,
  Output/...), the newest image is shown.
* Otherwise the panel shows the ARVEN profile emblem.
* Re-upload picks a real file and pushes it to the backend via the real
  ``read_file`` capability.
* Download saves the currently displayed media.
* Maximize opens a full-size viewer.
"""

import shutil
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

from ..emblem import Emblem
from ..styles import PALETTE


class _ProfileView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 120)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        size = min(self.width(), self.height())
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2,
                      size, size)
        Emblem.paint(p, rect, mode="badge", state="idle", phase=0.0)
        p.end()


class MediaPanel(QFrame):
    reupload = Signal(str)

    def __init__(self, parent=None, callbacks=None):
        super().__init__(parent)
        self.setObjectName("MediaPanel")
        callbacks = callbacks or {}
        self._current_path = None
        self._current_pixmap = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        self.title = QLabel("Image / Video", self)
        self.title.setObjectName("PanelTitle")
        head.addWidget(self.title)
        self.caption = QLabel("", self)
        self.caption.setObjectName("PanelSub")
        self.caption.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        head.addWidget(self.caption, 1)
        root.addLayout(head)

        self.view = QLabel(self)
        self.view.setObjectName("MediaView")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(200, 150)
        root.addWidget(self.view, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.reupload_btn = QPushButton("Re-upload", self)
        self.download_btn = QPushButton("Download", self)
        self.maximize_btn = QPushButton("Maximize", self)
        for btn in (self.reupload_btn, self.download_btn, self.maximize_btn):
            btn.setObjectName("MediaButton")
            btn.setCursor(Qt.PointingHandCursor)
            controls.addWidget(btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.reupload_btn.clicked.connect(self._reupload)
        self.download_btn.clicked.connect(self._download)
        self.maximize_btn.clicked.connect(self._maximize)

        if callbacks.get("reupload"):
            self.reupload.connect(lambda path: self._run(callbacks["reupload"], path))

        self.show_profile()
        self.reupload_btn.setEnabled(True)

    # ------------------------------------------------------------------
    def _run(self, fn, *args):
        try:
            fn(*args)
        except Exception:
            pass

    def show_profile(self):
        self._current_path = None
        self._current_pixmap = None
        self.view.setPixmap(QPixmap())
        self.view.setText("")
        widget = QLabel(self.view)
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(widget)
        profile = _ProfileView(widget)
        layout.addWidget(profile)
        note = QLabel("ARVEN profile", widget)
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet(f"color: {PALETTE['muted']}; font-size: 12px;")
        layout.addWidget(note)
        self.view.setLayout(layout)
        self.caption.setText("no generated media yet")
        self.download_btn.setEnabled(False)
        self.maximize_btn.setEnabled(False)

    def show_image(self, path):
        try:
            path = str(path)
            pix = QPixmap(path)
            if pix.isNull():
                raise ValueError(f"cannot read {path}")
            self._current_path = path
            self._current_pixmap = pix
            self.view.setLayout(None)
            self.view.setPixmap(pix.scaled(
                self.view.size(), Qt.KeepAspectRatio,
                Qt.SmoothTransformation))
            self.caption.setText(Path(path).name)
            self.download_btn.setEnabled(True)
            self.maximize_btn.setEnabled(True)
        except Exception as exc:
            self.show_profile()
            self.caption.setText(f"media unavailable: {exc}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            self.view.setPixmap(self._current_pixmap.scaled(
                self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def current_media_path(self):
        return self._current_path

    # ------------------------------------------------------------------
    def _reupload(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select an image or file", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All files (*)")
        if not file_path:
            return
        if str(file_path).lower().endswith(
                (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")):
            self.show_image(file_path)
        else:
            self.caption.setText(Path(file_path).name)
        self.reupload.emit(str(file_path))

    def _download(self):
        if not self._current_path:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Save media", Path(self._current_path).name,
            "PNG image (*.png);;JPEG (*.jpg);;All files (*)")
        if not target:
            return
        try:
            if self._current_pixmap is not None and str(target).lower().endswith(
                    (".png", ".jpg", ".jpeg")):
                self._current_pixmap.save(target)
            else:
                shutil.copyfile(self._current_path, target)
            self.caption.setText(f"saved: {Path(target).name}")
        except Exception as exc:
            self.caption.setText(f"save failed: {exc}")

    def _maximize(self):
        if not self._current_pixmap:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("ARVEN media viewer")
        lay = QVBoxLayout(dialog)
        label = QLabel(dialog)
        label.setAlignment(Qt.AlignCenter)
        label.setPixmap(self._current_pixmap)
        lay.addWidget(label)
        close = QPushButton("Close", dialog)
        close.setObjectName("DenyButton")
        close.clicked.connect(dialog.accept)
        lay.addWidget(close, alignment=Qt.AlignCenter)
        dialog.resize(
            min(self._current_pixmap.width() + 40, 1200),
            min(self._current_pixmap.height() + 90, 900))
        dialog.exec()


__all__ = ["MediaPanel"]