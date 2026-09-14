"""Main ARVEN AI application window.

Owns THE single Tk root (supplied by the app entry point — see app.py), the
custom title bar, window sizing/positioning, and switches between the Starting,
Landing, Chat, Talk and Shutting-Down views. All intelligence is delegated to
the AppController; this module only draws the current view and forwards user
gestures to the controller.
"""

import tkinter as tk

from config import get_settings
from desktop.ui import theme
from desktop.ui.widgets import TitleBar
from desktop.ui.views import (StartingView, LandingView, ChatView, TalkView,
                              ShuttingDownView)


class MainWindow:
    """The tkinter window for ARVEN AI.

    Accepts an already-created ``root`` from the app entry point so there is
    exactly one ``tk.Tk()`` for the whole process (a second root previously
    caused a hidden blank window). When used standalone (tests) a root is
    created lazily.
    """

    def __init__(self, controller, root=None):
        self.controller = controller
        self.root = root if root is not None else tk.Tk()
        self._owned_root = root is None
        s = get_settings()
        self.root.title(s.APP_TITLE)
        self.root.configure(bg=theme.BG)
        self.root.minsize(s.APP_MIN_WIDTH, s.APP_MIN_HEIGHT)
        try:
            self.root.iconbitmap(self._icon_path())
        except Exception:
            pass

        self._apply_size()

        # Remove the OS title bar entirely for a custom, modern chrome.
        self.root.overrideredirect(True)
        self.root.protocol("WM_DELETE_WINDOW", controller.request_shutdown)

        self.titlebar = TitleBar(
            self.root, s.APP_TITLE,
            on_min=self.minimize,
            on_max=self.toggle_maximize,
            on_close=controller.request_shutdown,
        )
        self.titlebar.pack(fill="x")

        self.body = tk.Frame(self.root, bg=theme.BG)
        self.body.pack(fill="both", expand=True)

        self.views = {}
        self._maximized = False

        # Moving the tiled/custom window.
        self.root.bind("<Alt-KeyPress-a>", lambda _e: self.focus_window())
        self.root.bind("<Alt-a>", lambda _e: self.focus_window())

    # ------------------------------------------------------------------
    # Sizing / positioning
    # ------------------------------------------------------------------

    def _apply_size(self):
        s = get_settings()
        w, h = s.APP_WINDOW_WIDTH, s.APP_WINDOW_HEIGHT
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # Centre the window on the work area.
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _icon_path(self):
        from pathlib import Path
        for p in (Path("assets/icon.ico"), Path("ARVEN AI.ico")):
            if p.exists():
                return str(p.resolve())
        return ""

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def _make_view(self, key):
        if key == "starting":
            return StartingView(self.body)
        if key == "landing":
            return LandingView(self.body,
                               on_chat=self.controller.select_chat,
                               on_talk=self.controller.select_talk)
        if key == "chat":
            return ChatView(self.body,
                            on_send=self.controller.on_user_input,
                            on_switch=self.controller.switch_to_talk,
                            on_back=self.controller.request_shutdown,
                            on_typing=self.controller.send_typing)
        if key == "talk":
            return TalkView(self.body,
                            on_push_to_talk=self.controller.begin_listen,
                            on_switch=self.controller.switch_to_chat,
                            on_back=self.controller.request_shutdown,
                            on_typing=self.controller.send_typing)
        if key == "shutting_down":
            return ShuttingDownView(self.body)
        return None

    def show_state(self, state):
        """Show the view matching an AppState."""
        key = {
            "STARTING": "starting",
            "MODE_SELECTION": "landing",
            "CHAT": "chat",
            "TALK": "talk",
            "SHUTTING_DOWN": "shutting_down",
        }.get(state.value)
        if key is None or key in ("starting", "shutting_down"):
            # Calm states: show them and stop.
            for child in self.body.winfo_children():
                child.destroy()
            self.views = {key: self._make_view(key)}
            if self.views[key]:
                self.views[key].pack(fill="both", expand=True)
            return
        for child in self.body.winfo_children():
            child.destroy()
        self.views = {}
        view = self._make_view(key)
        if view:
            self.views[key] = view
            view.pack(fill="both", expand=True)

    def chat_view(self):
        return self.views.get("chat")

    def talk_view(self):
        return self.views.get("talk")

    # ------------------------------------------------------------------
    # Window chrome
    # ------------------------------------------------------------------

    def minimize(self):
        self.root.iconify()

    def toggle_maximize(self):
        # Use the OS-native zoom state so DPI/resizing are handled correctly.
        state = self.root.state()
        if state == "zoomed":
            self.root.state("normal")
            self._maximized = False
        else:
            self.root.state("zoomed")
            self._maximized = True

    def focus_window(self):
        self.root.deiconify()
        if self._maximized:
            self.root.state("zoomed")
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    def destroy(self):
        try:
            self.root.destroy()
        except Exception:
            pass
