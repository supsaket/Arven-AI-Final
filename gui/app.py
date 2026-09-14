"""QApplication bootstrap for the ARVEN GUI."""

import sys

from PySide6.QtWidgets import QApplication

from .styles import app_stylesheet
from .window import MainWindow


def create_app(argv=None):
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("ARVEN AI")
    app.setOrganizationName("Arven AI")
    app.setStyleSheet(app_stylesheet())
    return app


def main(argv=None):
    app = create_app(argv)
    window = MainWindow()
    window.show()
    return app.exec()


__all__ = ["create_app", "main"]