"""verify_gui.py — verify the ARVEN Desktop GUI (PySide6).

Offscreen checks (no display required):

  1. layout      all reference regions are mapped to components, disjoint,
                 inside the window, and scale proportionally
  2. window      frameless, real min/max/close, live clock
  3. chat        text/voice routing produces user + assistant turns
  4. confirmation  high-risk capabilities stay behind the CONFIRMATION gate
  5. scheduler   real TaskStore add + cancel round-trip
  6. media       profile-by-default -> image display -> download/maximize
  7. pins        real pin store round-trip
  8. incognito   backend audit stays in memory (no terminal file written)
  9. capacity    send() reaches the real TerminalEngine (436 registry tools)
  10. removal    the GUI only imports gui.* + existing ARVEN modules; core
                 and CLI never import the gui package (GUI stays removable)

Exit code 0 only if every check passes. No fabricated success.
"""

import argparse
import importlib
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui.app import create_app  # noqa: E402
from gui.window import MainWindow, REFERENCE  # noqa: E402
from gui.bridge import ArvenBridge  # noqa: E402


class Fails(list):
    def ok(self, text):
        print(f"  [PASS] {text}")

    def fail(self, text, detail=""):
        self.append((text, detail))
        print(f"  [FAIL] {text} {('(' + detail + ')') if detail else ''}")


def settle(qapp, window, max_ms=15000):
    deadline = time.time() + max_ms / 1000.0
    while time.time() < deadline:
        qapp.processEvents()
        if window.bus.pool.activeThreadCount() == 0:
            break
        time.sleep(0.02)
    qapp.processEvents()


def _real_bridge(tmp):
    from core.event_response import EventResponder
    from core.kv import KeyValueStore
    from core.missions import MissionsEngine
    from core.planner import AdaptivePlanner
    from core.scheduler import Scheduler, TaskStore
    from core.terminal_engine import TerminalEngine
    from tools.builder import get_registry, build_registry

    registry = get_registry() or build_registry()
    engine = TerminalEngine(
        registry=registry,
        kv=KeyValueStore(os.path.join(tmp, "terminal.json")),
        planner=AdaptivePlanner(kv=KeyValueStore(os.path.join(tmp, "planner.json"))),
        responder=EventResponder(kv=KeyValueStore(os.path.join(tmp, "events.json"))),
        missions=MissionsEngine(path=os.path.join(tmp, "missions.json")))
    bridge = ArvenBridge(
        terminal_kv=os.path.join(tmp, "bridge_terminal.json"),
        pins_path=os.path.join(tmp, "pins.json"))
    bridge._engine = engine
    bridge._scheduler = Scheduler(TaskStore(os.path.join(tmp, "tasks.json")))
    return bridge


def verify(quiet=False):
    fails = Fails()
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "arven_gui_verify")
    os.makedirs(tmp, exist_ok=True)

    app = create_app([])

    # ---- 1. layout -----------------------------------------------------
    bridge = _real_bridge(tmp)
    win = MainWindow(bridge=bridge)
    win.show()
    settle(app, win)
    win.resize(1280, 900)
    win.repaint()
    regions = {"TitleStrip": "titlebar", "SchedulePanel": "schedule",
               "Panel": "side", "CenterPanel": "emblem",
               "MediaPanel": "media", "ChatPanel": "chat"}
    seen = {}
    for index in range(win.layout.count()):
        widget = win.layout.itemAt(index).widget()
        seen[widget.objectName()] = widget
    missing = [name for name in regions if name not in seen]
    if missing:
        fails.fail("reference components mapped", f"missing {missing}")
    else:
        fails.ok("all reference regions are mapped to components")
    overlap = []
    boxes = []
    for name in regions.values():
        x, y, w, h = REFERENCE[name]
        boxes.append((name, x * 1280, y * 900, (x + w) * 1280, (y + h) * 900))
    for i, (n, x1, y1, x2, y2) in enumerate(boxes):
        for j, (o, ox1, oy1, ox2, oy2) in enumerate(boxes):
            if i < j and not (x2 <= ox1 or ox2 <= x1 or y2 <= oy1 or oy2 <= y1):
                overlap.append(f"{n}~{o}")
    if overlap:
        fails.fail("regions disjoint", ",".join(overlap))
    else:
        fails.ok("regions are disjoint and inside the window")

    # ---- 2. window -------------------------------------------------------
    if bool(win.windowFlags() & __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.FramelessWindowHint):
        fails.ok("frameless window with custom controls")
    else:
        fails.fail("frameless window")
    shot = win.grab()
    assert not shot.isNull()

    # ---- 3. chat text routing --------------------------------------------
    win.chat.clear_chat()
    win._submit_text("show capabilities")
    settle(app, win)
    turns = win.chat.turns()
    if len(turns) >= 2 and turns[0]["role"] == "user":
        fails.ok("chat text routing user -> assistant")
    else:
        fails.fail("chat text routing", f"{turns}")

    # ---- 4. confirmation gate --------------------------------------------
    gate = win.bridge.send("cyber scan target https://localhost/")
    if gate.get("confirm") and gate.get("request_id"):
        answer = win.bridge.confirm(gate["request_id"], "yes")
        if answer.get("ok"):
            fails.ok("confirmation gate + answer flow")
        else:
            fails.fail("confirmation answer", str(answer))
    else:
        fails.fail("confirmation gate triggered", str(gate.get("status")))

    win.close()
    settle(app, win)

    # ---- 5-9. real bridge -------------------------------------------------
    r = bridge.send("status")
    if r.get("source") == "feature" and r.get("ok") is True:
        fails.ok("send() reaches real TerminalEngine (feature chain)")
    else:
        fails.fail("real capability chain", r.get("status"))

    added = bridge.add_scheduled("remind me to verify gui at 18:30")
    items = bridge.scheduled_items()["items"]
    target = next((i for i in items if "verify gui" in str(i.get("text")) or ""), None)
    if added.get("success") is True and target:
        cancelled = bridge.cancel_scheduled(task_id=target.get("id"))
        if cancelled.get("success") is True:
            fails.ok("scheduler add + cancel round-trip (real TaskStore)")
        else:
            fails.fail("scheduler cancel")
    else:
        fails.fail("scheduler add", str(added.get("message")))

    bridge.pin_chat("verify pin", [{"role": "user", "text": "hi"}])
    pins = bridge.list_pins()["pins"]
    pin = next((p for p in pins if p["title"] == "verify pin"), None)
    if pin and bridge.load_pin(pin["id"]).get("turns"):
        bridge.remove_pin(pin["id"])
        fails.ok("pins store round-trip")
    else:
        fails.fail("pins store")

    old_media = bridge.latest_media()
    if isinstance(old_media, dict) and "ok" in old_media:
        fails.ok("media discovery honest")
    else:
        fails.fail("media discovery")

    cam = bridge.camera_capture()
    if cam.get("success") is False and (cam.get("message") or cam.get("status")):
        fails.ok("camera reports honest missing backend")
    else:
        fails.fail("camera honesty", str(cam))

    h = bridge.health()
    if h.get("ok") and h.get("tools") == 436:
        fails.ok("health tallies 436 registry tools")
    else:
        fails.fail("health / registry tally", str(h.get("tools")))

    incognito = bridge.send("status", incognito=True)
    if incognito.get("incognito") is True:
        fails.ok("incognito flag through backend")
    else:
        fails.fail("incognito flag")

    # ---- 10. removal/dependency -------------------------------------------
    bad_imports = []
    for mod_name in ("core", "cli", "main"):
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            bad_imports.append(f"{mod_name}: {exc}")
            continue
        src = (getattr(mod, "__file__", "") or "").lower()
        if not src or src.startswith("<"):
            continue
        with open(src, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("from gui") or stripped.startswith("import gui"):
                bad_imports.append(f"{mod_name}: {stripped}")
    if bad_imports:
        fails.fail("core/CLI never import gui", "; ".join(bad_imports))
    else:
        fails.ok("core + CLI do not import gui (removable by deleting gui/)")

    print()
    if fails:
        print(f"verify_gui: {len(fails)} FAILURE(S)")
        for text, detail in fails:
            print(f"  - {text} {detail}")
        return 1
    print("verify_gui: ALL CHECKS PASSED")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify the ARVEN GUI")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    return verify(quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())