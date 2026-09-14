"""Async backend execution for the GUI.

Backend calls (engine, brain, voice, registry tools) can take seconds; they must
never block the Qt main thread. Every call runs in a ``QThreadPool`` worker and
the result is delivered back on the main thread through Qt signals (queued
auto-connections), keeping the UI responsive.
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Job(QRunnable):
    def __init__(self, kind, fn, bus):
        super().__init__()
        self.kind = kind
        self.fn = fn
        self.bus = bus

    def run(self):
        try:
            payload = self.fn()
        except Exception as exc:  # pragma: no cover - defensive
            self.bus._failed.emit(self.kind, f"{exc}")
            return
        self.bus._finished.emit(self.kind, payload)


class BackendBus(QObject):
    """Queue + deliver backend jobs without freezing the UI."""

    started = Signal(str)            # job kind (drives central state text)
    finished = Signal(str, object)   # (kind, payload dict)
    failed = Signal(str, str)        # (kind, error message)

    def __init__(self, max_workers=3):
        super().__init__()
        self._finished = self.finished
        self._failed = self.failed
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, max_workers))

    def start(self, kind, fn):
        if not callable(fn):
            return
        self.started.emit(kind)
        job = _Job(kind, fn, self)
        self.pool.start(job)


__all__ = ["BackendBus"]