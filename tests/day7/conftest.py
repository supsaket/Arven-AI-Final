"""Day 7 — GUI tests. All hermetic: offscreen Qt, fake/stubbed backend paths,
temporary stores. No Ollama calls, no real hardware, no network needed.

The GUI itself is tested against a FakeBridge (deterministic routing), while the
real ArvenBridge is exercised against a real TerminalEngine built on temporary
stores so the actual 123-feature routing is covered without touching repo data.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def window(qapp):
    """A MainWindow bound to a FakeBridge with the real BackendBus."""
    from gui.window import MainWindow
    bridge = FakeBridge()
    win = MainWindow(bridge=bridge)
    win.show()
    settle(qapp, win)
    yield win
    win.close()
    settle(qapp, win)


def settle(qapp, window, max_ms=8000):
    """Process Qt events until the window's background jobs have settled."""
    import time
    deadline = time.time() + max_ms / 1000.0
    while time.time() < deadline:
        qapp.processEvents()
        if window.bus.pool.activeThreadCount() == 0:
            qapp.processEvents()
            if window.bus.pool.activeThreadCount() == 0:
                break
        time.sleep(0.02)
    qapp.processEvents()


# --------------------------------------------------------------------------- 
class FakeBridge:
    """Deterministic ArvenBridge stand-in for GUI interaction tests."""

    def __init__(self):
        self.sends = []
        self.confirmed = []
        self.spoken = []
        self.pins = []

    # ---- core
    def send(self, text, approve=False, incognito=False, principal="boss"):
        self.sends.append({"text": text, "approve": approve,
                           "incognito": incognito})
        if str(text).lower() == "review" and not approve:
            return {"ok": False, "source": "feature", "status": "confirm_required",
                    "title": "review_task", "text": "Approve the review?",
                    "confirm": True, "request_id": "req-1",
                    "incognito": incognito, "data": {"risk": "high"}}
        return {"ok": True, "source": "feature", "status": "ok",
                "title": "feature",
                "text": f"ARVEN handled: {text}" + (" (approved)" if approve else ""),
                "confirm": False, "request_id": None,
                "incognito": incognito, "data": {}}

    def confirm(self, request_id, verdict):
        self.confirmed.append((request_id, verdict))
        return {"ok": True, "request_id": request_id}

    # ---- scheduler
    def scheduled_items(self, limit=6):
        return {"ok": True, "items": [{"id": "t1", "text": "water plants",
                                       "time": "18:00"}]}

    def add_scheduled(self, text):
        return {"success": True, "id": "t2"}

    def cancel_scheduled(self, text=None, task_id=None):
        return {"success": True}

    # ---- media
    def latest_media(self):
        return {"ok": False, "path": None}

    def generate_image(self, prompt, width=384, height=384):
        return {"ok": False, "status": "NOT_CONFIGURED",
                "message": "provider not configured"}

    def capture_screen(self):
        return {"success": False, "status": "FAILED",
                "message": "no screen available offscreen", "result": {}}

    def camera_capture(self):
        return {"success": False, "status": "FAILED",
                "message": "camera unavailable (cv2 missing)", "result": {}}

    def grant_camera(self):
        return {"success": True, "status": "ok", "message": "permission granted"}

    def read_file(self, path):
        return {"success": True, "path": str(path), "content": "probe content",
                "content_length": 13}

    # ---- voice
    def transcribe(self, duration=5):
        return {"success": True, "text": "spoken words"}

    def speak(self, text):
        self.spoken.append(text)
        return {"success": True}


# --------------------------------------------------------------------------- 
def build_real_bridge(tmp_path):
    """ArvenBridge with a real TerminalEngine on temporary stores."""
    from core.event_response import EventResponder
    from core.kv import KeyValueStore
    from core.missions import MissionsEngine
    from core.planner import AdaptivePlanner
    from core.terminal_engine import TerminalEngine
    from tools.builder import get_registry, build_registry
    from gui.bridge import ArvenBridge

    registry = get_registry() or build_registry()
    engine = TerminalEngine(
        registry=registry,
        kv=KeyValueStore(str(tmp_path / "terminal.json")),
        planner=AdaptivePlanner(kv=KeyValueStore(str(tmp_path / "planner.json"))),
        responder=EventResponder(kv=KeyValueStore(str(tmp_path / "events.json"))),
        missions=MissionsEngine(path=str(tmp_path / "missions.json")))

    from core.scheduler import Scheduler, TaskStore
    bridge = ArvenBridge(
        terminal_kv=str(tmp_path / "bridge_terminal.json"),
        pins_path=str(tmp_path / "pins.json"))
    bridge._engine = engine
    bridge._scheduler = Scheduler(TaskStore(str(tmp_path / "tasks.json")))
    return bridge


@pytest.fixture()
def real_bridge(tmp_path):
    return build_real_bridge(tmp_path)


__all__ = ["FakeBridge", "build_real_bridge", "settle", "ROOT"]