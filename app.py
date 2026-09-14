"""ARVEN AI — standalone desktop application entry point.

Run with:
    python app.py                # development GUI launch
    python app.py --no-hotkey    # launch without registering ALT+A
    python app.py --hotkey-agent # background agent: ALT+A launches/focuses ARVEN

ALWAYS single-instance:
  - launching a second time (or pressing ALT+A) focuses/restores the existing
    window instead of starting another process.
"""

import argparse
import logging
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

LOGGING = logging.getLogger("arven")

sys.path.insert(0, str(Path(__file__).resolve().parent))


class _TkUIHook:
    """UI hook for the real tkinter app: thread-safe main-thread scheduling + TTS.

    Naively calling ``root.after(0, ...)`` from worker threads is unreliable —
    the Tcl event loop intermittently drops cross-thread ``after`` callbacks
    (which is exactly what made real Chat replies/status updates sometimes never
    appear). Instead we push every callback into a queue and drain it on the
    main thread via a self-rescheduling ``after`` timer. That guarantees each
    posted callback runs exactly once, on the main thread, in order.
    """

    def __init__(self, root):
        self.root = root
        self._queue = queue.Queue()
        self._draining = False
        self._closed = False

    def post(self, fn, *args):
        if self._closed:
            return
        self._queue.put((fn, args))
        if not self._draining:
            self._draining = True
            try:
                self.root.after(50, self._drain)
            except Exception:
                self._draining = False

    def _drain(self):
        self._draining = False
        if self._closed:
            # Once closed we are done; nothing more to drain.
            fire = []
            while not self._queue.empty():
                fire.append(self._queue.get_nowait())
            for fn, args in fire:
                try:
                    fn(*args)
                except Exception:
                    pass
            return
        fired = 0
        while not self._queue.empty():
            fn, args = self._queue.get_nowait()
            try:
                fn(*args)
            except Exception:
                pass
            fired += 1
        if fired > 0 or not self._queue.empty():
            try:
                self._draining = True
                self.root.after(50, self._drain)
                return
            except Exception:
                self._draining = False
        # Nothing pending: schedule a light poll so late-arriving posts still
        # get picked up without tight-spinning the main thread.
        try:
            self._draining = True
            self.root.after(100, self._drain)
        except Exception:
            self._draining = False

    def shutdown(self):
        self._closed = True

    def speak(self, text):
        return _speak_blocking(text)

    def request_speak(self, text):
        threading.Thread(target=_speak_blocking, args=(text,), daemon=True).start()
        return True

    def exit_process(self, code=0):
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            pass
        return code


def _speak_blocking(text):
    try:
        from voice.output import speak
        return bool(speak(text))
    except Exception:
        return False


def _bind_window_handlers(controller, window):
    """Wire controller output to whatever view is currently active."""

    def user_handler(text):
        v = window.chat_view() or window.talk_view()
        if v:
            v.on_boss(text)

    def arven_handler(text):
        v = window.chat_view() or window.talk_view()
        if v:
            v.on_arven(text)

    def system_handler(text):
        v = window.chat_view() or window.talk_view()
        if v:
            v.on_system(text)

    def busy_handler(busy):
        v = window.chat_view() or window.talk_view()
        if v:
            v.busy(busy)

    controller.bind_ui(
        state_handler=window.show_state,
        user_handler=user_handler,
        arven_handler=arven_handler,
        system_handler=system_handler,
        busy_handler=busy_handler,
        status_handler=lambda text, kind: (
            window.talk_view().set_status(text, kind)
            if window.talk_view() else None),
        close_handler=window.destroy,
    )


def run_app(register_hotkey=True):
    import tkinter as tk
    from desktop.controller import AppController
    from desktop.state import AppState
    import desktop.single_instance as si

    # Single instance: if another is already running, focus it and exit.
    handle, is_primary = si.acquire_single_instance()
    if not is_primary:
        title = "ARVEN AI"
        if si.focus_window(title) or si.focus_window("ARVEN - Personal AI Assistant"):
            print("ARVEN AI is already running — brought its window to front.")
        else:
            print("ARVEN AI is already running (could not focus its window).")
        return 0

    # Exactly ONE Tk root for the whole application. This single root drives the
    # UI hook AND the MainWindow, so there is no second hidden blank window.
    root = tk.Tk()
    ui = _TkUIHook(root)

    # Reuse the existing voice engine (never re-implemented). Wiring it in is
    # what previously made Talk/voice report "Voice input is unavailable".
    try:
        from voice.input import VoiceInput
        voice = VoiceInput()
    except Exception as exc:
        LOGGING.error("could not initialise VoiceInput: %s", exc)
        voice = None

    controller = AppController(brain=None, voice=voice, ui=ui)
    controller._instance_handle = handle

    from desktop.ui.window import MainWindow
    window = MainWindow(controller, root=root)
    _bind_window_handlers(controller, window)

    # Eagerly monitor persisted reminders from launch (idempotent).
    _start_scheduler_at_launch()

    from core.config import settings
    if register_hotkey:
        from desktop.hotkey import GlobalHotkey
        controller.register_hotkey(GlobalHotkey, callback=window.focus_window)

    # Start in mode selection: "Boss, what do you prefer — Chat or Talk?"
    # begin_mode_selection speaks the prompt, and only AFTER the prompt TTS has
    # fully finished (plus a short audio-settle delay) opens the microphone —
    # so ARVEN never captures its own question, and a chosen mode immediately
    # lands the user in the right view without any button click.
    controller._set_state(AppState.MODE_SELECTION)
    controller.begin_mode_selection(settings.APP_MODE_PROMPT)

    root.protocol("WM_DELETE_WINDOW", controller.request_shutdown)
    try:
        root.mainloop()
    finally:
        controller.release_single_instance()
        _stop_other_workers()
    return 0


def _stop_other_workers():
    # Best-effort stop of the scheduler daemon so it doesn't outlive the app.
    try:
        from scheduler.scheduler import scheduler as _sched
        _sched.stop()
    except Exception:
        pass


def _start_scheduler_at_launch():
    # Eagerly start the scheduler so persisted reminders are monitored from the
    # very beginning of the session — not only after the user first mentions a
    # task/schedule phrase. The scheduler daemon is idempotent (start() no-ops
    # if already running) so importing + starting it here is safe and cheap.
    try:
        import scheduler.scheduler as _mod
        _mod.scheduler.start()
        log = logging.getLogger("arven")
        log.debug("scheduler started at launch")
    except Exception:
        pass


def run_hotkey_agent():
    """Background agent: ALT+A launches (or focuses) ARVEN.

    Runs a hidden process listening for ALT+A; when pressed it starts the app
    via `python app.py`, which single-instance-focuses any running instance.
    Register this with Task Scheduler / Startup for the hotkey to work even
    before ARVEN is open.
    """
    from desktop.hotkey import GlobalHotkey, HotkeyError
    python = sys.executable
    this = Path(__file__).resolve()

    def on_hotkey():
        try:
            subprocess.Popen(
                [python, str(this), "--no-hotkey"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as exc:
            LOGGING.error("launch failed: %s", exc)

    hk = GlobalHotkey(callback=on_hotkey)
    try:
        hk.register()
    except HotkeyError as exc:
        print(f"hotkey-agent: {exc}")
        return 1
    hk.start()
    print("ARVEN AI hotkey agent running (ALT+A). Ctrl+C to stop.")
    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        hk.stop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="ARVEN AI desktop app")
    parser.add_argument("--no-hotkey", action="store_true",
                        help="do not register the ALT+A global hotkey")
    parser.add_argument("--hotkey-agent", action="store_true",
                        help="run as a background agent that launches ARVEN on ALT+A")
    parser.add_argument("--text", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

    if args.hotkey_agent:
        return run_hotkey_agent()

    if args.text:
        from main import run_text
        run_text()
        return 0

    return run_app(register_hotkey=not args.no_hotkey)


if __name__ == "__main__":
    sys.exit(main())
