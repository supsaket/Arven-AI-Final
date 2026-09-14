import json
import sqlite3
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget, QCheckBox, QComboBox,
    QSpinBox, QProgressBar
)

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parent
DATA_DIR = PROJECT / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "desktop_settings.json"
TASKS_FILE = DATA_DIR / "desktop_tasks.json"

APP_NAME = "ARVEN"
APP_VERSION = "1.0.0"
API_URL = "http://127.0.0.1:8000"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class Orb(QWidget):
    def __init__(self):
        super().__init__()
        self.phase = 0
        self.setMinimumSize(220, 220)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(40)

    def animate(self):
        self.phase = (self.phase + 2) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.rect().center()
        r = min(self.width(), self.height()) // 3
        # Soft rings
        for i in range(5, 0, -1):
            alpha = 18 + i * 8
            p.setPen(QPen(QColor(93, 211, 255, alpha), 2))
            rr = r + i * 10 + int(4 * __import__("math").sin((self.phase+i*18)*0.017))
            p.drawEllipse(c, rr, rr)
        p.setPen(QPen(QColor(110, 225, 255), 3))
        p.setBrush(QColor(22, 32, 48))
        p.drawEllipse(c, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(104, 218, 255, 45))
        p.drawEllipse(c, r-16, r-16)
        p.setPen(QPen(QColor(220, 250, 255), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r-30, r-30)
        p.setPen(QColor(235, 250, 255))
        p.setFont(QFont("Segoe UI", 22, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, "ARVEN")


class ApiWorker(QThread):
    result = Signal(str, bool)

    def __init__(self, message):
        super().__init__()
        self.message = message

    def run(self):
        payload = json.dumps({"message": self.message}).encode()
        candidates = [API_URL + "/chat", API_URL + "/api/chat"]
        for url in candidates:
            try:
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=45) as r:
                    raw = r.read().decode("utf-8", errors="replace")
                    try:
                        obj = json.loads(raw)
                        text = obj.get("response") or obj.get("reply") or obj.get("message") or obj.get("text") or raw
                    except Exception:
                        text = raw
                    self.result.emit(str(text), True)
                    return
            except Exception:
                pass
        self.result.emit(
            "I couldn't reach the Arven backend at 127.0.0.1:8000. "
            "Start your FastAPI service and try again. The desktop shell itself is running.",
            False
        )


class Page(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 28, 30, 28)
        self.layout.setSpacing(18)

    def title(self, text, subtitle=""):
        h = QLabel(text)
        h.setObjectName("PageTitle")
        self.layout.addWidget(h)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("Muted")
            self.layout.addWidget(s)


class HomePage(Page):
    def __init__(self, window):
        super().__init__()
        self.title("Good to see you.", "Arven is ready to work locally with your existing project.")
        row = QHBoxLayout()
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.addWidget(QLabel("ARVEN STATUS"))
        status = QLabel("●  ONLINE")
        status.setObjectName("Status")
        cl.addWidget(status)
        cl.addWidget(QLabel("Desktop shell: running"))
        cl.addWidget(QLabel("Backend: checking…"))
        self.backend_label = cl.itemAt(3).widget()
        row.addWidget(card, 1)
        orb_card = QFrame()
        orb_card.setObjectName("Card")
        ol = QVBoxLayout(orb_card)
        orb = Orb()
        ol.addWidget(orb, alignment=Qt.AlignCenter)
        row.addWidget(orb_card, 1)
        self.layout.addLayout(row)

        stats = QHBoxLayout()
        for name, value in [("Version", APP_VERSION), ("Memory", "Local"), ("Mode", "Desktop")]:
            c = QFrame(); c.setObjectName("Card"); l = QVBoxLayout(c)
            v = QLabel(value); v.setObjectName("Stat")
            l.addWidget(QLabel(name)); l.addWidget(v)
            stats.addWidget(c)
        self.layout.addLayout(stats)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_backend)
        self.timer.start(5000)
        self.check_backend()

    def check_backend(self):
        try:
            with urllib.request.urlopen(API_URL + "/", timeout=2) as r:
                self.backend_label.setText("Backend: online")
        except Exception:
            self.backend_label.setText("Backend: offline / not started")


class ChatPage(Page):
    def __init__(self):
        super().__init__()
        self.title("Arven Chat", "Talk to your existing Arven backend.")
        self.chat = QTextBrowser()
        self.chat.setObjectName("Chat")
        self.chat.setOpenExternalLinks(True)
        self.layout.addWidget(self.chat, 1)

        bar = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message Arven…")
        self.input.returnPressed.connect(self.send)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send)
        bar.addWidget(self.input, 1); bar.addWidget(self.send_btn)
        self.layout.addLayout(bar)
        self.worker = None
        self.add_message("ARVEN", "Desktop interface initialized. Ask me something.")

    def add_message(self, who, text):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.chat.append(f"<b>{who}</b><br>{safe}<br>")

    def send(self):
        text = self.input.text().strip()
        if not text or self.worker and self.worker.isRunning():
            return
        self.input.clear()
        self.add_message("YOU", text)
        self.send_btn.setEnabled(False)
        self.worker = ApiWorker(text)
        self.worker.result.connect(self.receive)
        self.worker.finished.connect(lambda: self.send_btn.setEnabled(True))
        self.worker.start()

    def receive(self, text, ok):
        self.add_message("ARVEN" if ok else "SYSTEM", text)


class TasksPage(Page):
    def __init__(self):
        super().__init__()
        self.title("Tasks", "Local task list for the Arven desktop application.")
        top = QHBoxLayout()
        self.input = QLineEdit(); self.input.setPlaceholderText("Add a task…")
        add = QPushButton("Add task"); add.clicked.connect(self.add_task)
        top.addWidget(self.input, 1); top.addWidget(add)
        self.layout.addLayout(top)
        self.list = QListWidget()
        self.layout.addWidget(self.list, 1)
        clear = QPushButton("Clear completed")
        clear.clicked.connect(self.clear_completed)
        self.layout.addWidget(clear)
        self.load_tasks()

    def load_tasks(self):
        self.list.clear()
        for task in load_json(TASKS_FILE, []):
            item = QListWidgetItem(task["text"])
            item.setData(Qt.UserRole, task)
            item.setCheckState(Qt.Checked if task.get("done") else Qt.Unchecked)
            self.list.addItem(item)

    def persist(self):
        data = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            data.append({"text": it.text(), "done": it.checkState() == Qt.Checked})
        save_json(TASKS_FILE, data)

    def add_task(self):
        t = self.input.text().strip()
        if t:
            it = QListWidgetItem(t)
            it.setCheckState(Qt.Unchecked)
            self.list.addItem(it)
            self.input.clear()
            self.persist()

    def clear_completed(self):
        for i in range(self.list.count()-1, -1, -1):
            if self.list.item(i).checkState() == Qt.Checked:
                self.list.takeItem(i)
        self.persist()


class MemoryPage(Page):
    def __init__(self):
        super().__init__()
        self.title("Memory", "Inspect local Arven SQLite memory without modifying it.")
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.layout.addWidget(self.info)
        self.box = QTextBrowser()
        self.layout.addWidget(self.box, 1)
        self.refresh()

    def refresh(self):
        dbs = list(PROJECT.glob("*memory*.db")) + list(PROJECT.glob("*memory*.sqlite"))
        if not dbs:
            self.info.setText("No memory database found in the project root.")
            self.box.setText("Your existing memory database will appear here when available.")
            return
        db = dbs[0]
        try:
            con = sqlite3.connect(db)
            tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            out = [f"Database: {db.name}", ""]
            for (table,) in tables:
                out.append(f"TABLE: {table}")
                try:
                    rows = con.execute(f'SELECT * FROM "{table}" LIMIT 8').fetchall()
                    for row in rows:
                        out.append("  " + " | ".join(map(str, row)))
                except Exception as e:
                    out.append("  Unable to read rows: " + str(e))
            con.close()
            self.info.setText(f"Found {db.name}")
            self.box.setText("\n".join(out))
        except Exception as e:
            self.box.setText("Memory database could not be opened:\n" + str(e))


class SecurityPage(Page):
    def __init__(self):
        super().__init__()
        self.title("Security Center", "Safe local visibility for your Arven environment.")
        cards = QHBoxLayout()
        for label, value in [("Network response", "Ready"), ("Event monitor", "Ready"), ("Protection", "Enabled")]:
            c=QFrame(); c.setObjectName("Card"); l=QVBoxLayout(c)
            l.addWidget(QLabel(label)); v=QLabel(value); v.setObjectName("Stat"); l.addWidget(v)
            cards.addWidget(c)
        self.layout.addLayout(cards)
        box = QFrame(); box.setObjectName("Card"); bl=QVBoxLayout(box)
        bl.addWidget(QLabel("System status"))
        p=QProgressBar(); p.setRange(0,100); p.setValue(100)
        bl.addWidget(p)
        bl.addWidget(QLabel("This dashboard is ready to receive events from your existing NEXUS/Arven security modules."))
        self.layout.addWidget(box)
        self.layout.addStretch()


class SettingsPage(Page):
    def __init__(self):
        super().__init__()
        self.title("Settings", "Desktop preferences.")
        settings = load_json(SETTINGS_FILE, {"start_backend": True, "notifications": True, "theme": "Dark"})
        form = QFrame(); form.setObjectName("Card"); l=QVBoxLayout(form)
        self.backend = QCheckBox("Start backend with Arven")
        self.backend.setChecked(settings.get("start_backend", True))
        self.notify = QCheckBox("Enable desktop notifications")
        self.notify.setChecked(settings.get("notifications", True))
        theme = QComboBox(); theme.addItems(["Dark"]); theme.setCurrentText(settings.get("theme","Dark"))
        save = QPushButton("Save settings")
        save.clicked.connect(lambda: self.save(theme))
        l.addWidget(self.backend); l.addWidget(self.notify)
        l.addWidget(QLabel("Theme")); l.addWidget(theme); l.addWidget(save)
        self.layout.addWidget(form); self.layout.addStretch()

    def save(self, theme):
        save_json(SETTINGS_FILE, {
            "start_backend": self.backend.isChecked(),
            "notifications": self.notify.isChecked(),
            "theme": theme.currentText()
        })
        QMessageBox.information(self, "Arven", "Settings saved.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} AI — Desktop")
        self.resize(1280, 800)
        self.setMinimumSize(1000, 650)

        central = QWidget(); self.setCentralWidget(central)
        main = QHBoxLayout(central); main.setContentsMargins(0,0,0,0); main.setSpacing(0)

        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(230)
        sl=QVBoxLayout(sidebar); sl.setContentsMargins(18,24,18,18)
        brand=QLabel("ARVEN"); brand.setObjectName("Brand"); sl.addWidget(brand)
        ver=QLabel("AI DESKTOP  •  v"+APP_VERSION); ver.setObjectName("Muted"); sl.addWidget(ver)
        sl.addSpacing(25)

        self.stack=QStackedWidget()
        pages = [
            ("⌂  Home", HomePage(self)),
            ("◉  Chat", ChatPage()),
            ("✓  Tasks", TasksPage()),
            ("✦  Memory", MemoryPage()),
            ("◈  Security", SecurityPage()),
            ("⚙  Settings", SettingsPage()),
        ]
        self.buttons=[]
        for name, page in pages:
            b=QPushButton(name); b.setCheckable(True); b.setAutoExclusive(True)
            b.clicked.connect(lambda checked, p=page: self.stack.setCurrentWidget(p))
            sl.addWidget(b); self.buttons.append(b); self.stack.addWidget(page)
        sl.addStretch()
        foot=QLabel("LOCAL • PRIVATE\nArven AI"); foot.setObjectName("Muted"); sl.addWidget(foot)

        main.addWidget(sidebar); main.addWidget(self.stack,1)
        self.buttons[0].setChecked(True)

        self.setStyleSheet(STYLE)


STYLE = """
* { font-family: "Segoe UI"; }
QMainWindow, QWidget { background: #0b0f14; color: #e8eef5; }
#Sidebar { background: #080b10; border-right: 1px solid #1b2632; }
#Brand { font-size: 28px; font-weight: 800; letter-spacing: 3px; }
#PageTitle { font-size: 30px; font-weight: 700; }
#Muted { color: #7f8c9a; }
#Status { color: #67e8a5; font-weight: 700; }
QPushButton {
    background: transparent; border: 1px solid transparent; border-radius: 9px;
    padding: 12px; text-align: left; color: #aeb9c5; font-size: 14px;
}
QPushButton:hover { background: #111923; color: #ffffff; }
QPushButton:checked { background: #132331; color: #74dcff; border: 1px solid #21465b; }
QFrame#Card {
    background: #0f151d; border: 1px solid #1c2a37; border-radius: 14px;
}
QLabel#Stat { font-size: 24px; font-weight: 700; color: #dff7ff; }
QLineEdit, QTextBrowser, QListWidget, QComboBox, QSpinBox {
    background: #0d131a; border: 1px solid #22313f; border-radius: 9px;
    padding: 10px; color: #e8eef5;
}
QTextBrowser#Chat { padding: 16px; }
QProgressBar { border: 1px solid #22313f; border-radius: 7px; text-align: center; background: #0b1117; }
QProgressBar::chunk { background: #62d9ff; border-radius: 6px; }
QCheckBox { padding: 10px; }
"""

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
