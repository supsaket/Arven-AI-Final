"""ARVEN AI desktop views: Starting, Landing (mode pick), Chat, Talk, Shutting Down.

Each view is presentation-only; it forwards user gestures to the AppController via
injected callbacks. No backend intelligence lives here. All views share the layout
tokens in ``desktop.ui.theme`` so the look stays consistent and nothing touches the
screen edges.
"""

import tkinter as tk

from desktop.ui import theme
from desktop.ui.transcript import ChatTranscript
from desktop.ui.widgets import RoundedButton


def _muted_label(master, text, size=-1):
    return tk.Label(master, text=text, font=theme.FONT_SUB if size < 0 else size,
                    bg=master["bg"], fg=theme.FG_MUTED)


# ----------------------------------------------------------------------
# Starting / Shutting down (simple, calm status states)
# ----------------------------------------------------------------------

class StatusView(tk.Frame):
    """A centered status card used for STARTING and SHUTTING_DOWN."""

    def __init__(self, master, message, sub=None, glyph="✦"):
        super().__init__(master, bg=theme.BG)
        box = tk.Frame(self, bg=theme.PANEL)
        box.place(relx=0.5, rely=0.5, anchor="center")

        mark = tk.Canvas(box, width=88, height=88, bg=theme.PANEL,
                         highlightthickness=0)
        mark.pack(padx=48, pady=(40, 12))
        mark.create_oval(6, 6, 82, 82, fill=theme.ACCENT_DARK, outline="")
        mark.create_text(44, 44, text=glyph, fill=theme.FG,
                         font=("Segoe UI", 34))

        tk.Label(box, text=message, font=theme.FONT_TITLE, bg=theme.PANEL,
                 fg=theme.FG).pack(pady=(0, 6))
        if sub:
            _muted_label(box, sub).pack(pady=(0, 40))


class StartingView(StatusView):
    def __init__(self, master):
        super().__init__(master, "Starting ARVEN…", "Waking up your assistant")


class ShuttingDownView(StatusView):
    def __init__(self, master):
        super().__init__(master, "Bye Boss.", "See you soon")


# ----------------------------------------------------------------------
# Landing / mode selection
# ----------------------------------------------------------------------

class LandingView(tk.Frame):

    def __init__(self, master, on_chat, on_talk):
        super().__init__(master, bg=theme.BG)
        self.on_chat = on_chat
        self.on_talk = on_talk

        center = tk.Frame(self, bg=theme.BG)
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Brand mark
        mark = tk.Canvas(center, width=96, height=96, bg=theme.BG,
                         highlightthickness=0)
        mark.pack(pady=(0, 26))
        mark.create_oval(4, 4, 92, 92, fill=theme.ACCENT, outline="")
        mark.create_oval(4, 4, 92, 92, outline=theme.ACCENT_HOVER, width=1)
        mark.create_text(48, 48, text="✦", fill=theme.BG,
                         font=("Segoe UI", 42))

        tk.Label(center, text="ARVEN AI", font=theme.FONT_TITLE, bg=theme.BG,
                 fg=theme.FG).pack(pady=(0, 4))
        _muted_label(center, "Your right-hand companion").pack(pady=(0, 34))

        tk.Label(center, text="Boss, what do you prefer — Chat or Talk?",
                 font=("Segoe UI", 14), bg=theme.BG, fg=theme.FG).pack(pady=(0, 32))

        row = tk.Frame(center, bg=theme.BG)
        row.pack()
        self.btn_chat = RoundedButton(row, "CHAT", command=self.on_chat,
                                      fill=theme.ACCENT, hover_fill=theme.ACCENT_HOVER,
                                      width=180, height=48)
        self.btn_chat.pack(side="left", padx=10)
        self.btn_talk = RoundedButton(row, "TALK", command=self.on_talk,
                                      fill=theme.PURPLE, hover_fill=theme.ACCENT_2,
                                      width=180, height=48)
        self.btn_talk.pack(side="left", padx=10)

        _muted_label(center, "Or say Chat or Talk aloud").pack(pady=(28, 0))


# ----------------------------------------------------------------------
# Chat
# ----------------------------------------------------------------------

class ChatView(tk.Frame):

    def __init__(self, master, on_send, on_switch, on_back, on_typing=None):
        super().__init__(master, bg=theme.BG)
        self.on_send = on_send
        self.on_switch = on_switch
        self.on_typing = on_typing

        self._build_header("Chat", "TALK", switch_fill=theme.PURPLE,
                           switch_hover=theme.ACCENT_2)

        self.transcript = ChatTranscript(self)
        self.transcript.pack(fill="both", expand=True,
                             padx=theme.PAD, pady=(theme.GAP, theme.GAP))

        bottom = tk.Frame(self, bg=theme.BG)
        bottom.pack(fill="x", padx=theme.PAD, pady=(0, theme.PAD))
        self.entry = tk.Entry(bottom, bg=theme.PANEL, fg=theme.FG,
                              insertbackground=theme.FG, relief="flat",
                              font=theme.FONT, highlightthickness=1,
                              highlightbackground=theme.PANEL_2,
                              highlightcolor=theme.ACCENT)
        self.entry.pack(side="left", fill="x", expand=True,
                        ipady=11, ipadx=12)
        self.entry.bind("<Return>", lambda _e: self.send())
        self.entry.bind("<KeyRelease>", self._on_typing)
        self.btn = RoundedButton(bottom, "Send", command=self.send,
                                 fill=theme.ACCENT, hover_fill=theme.ACCENT_HOVER,
                                 height=42, width=96,
                                 font=("Segoe UI", 11, "bold"))
        self.btn.pack(side="right", padx=(theme.GAP, 0))
        self.entry.focus_set()

    def _build_header(self, title, switch_text, switch_fill, switch_hover):
        header = tk.Frame(self, bg=theme.BG_ALT)
        header.pack(fill="x", ipady=14)
        tk.Label(header, text=title, font=theme.FONT_LOGO, bg=theme.BG_ALT,
                 fg=theme.FG).pack(side="left", padx=theme.PAD)
        switch = RoundedButton(header, switch_text, command=self.on_switch,
                               fill=switch_fill, hover_fill=switch_hover,
                               height=36, width=96,
                               font=("Segoe UI", 10, "bold"))
        switch.pack(side="right", padx=theme.PAD)
        tk.Label(header, text="Boss", font=theme.FONT_SMALL, bg=theme.BG_ALT,
                 fg=theme.FG_FAINT).pack(side="right", padx=(0, 8))

    def send(self):
        raw = self.entry.get().strip()
        if not raw:
            return
        self.entry.delete(0, "end")
        self.on_send(raw)

    def _on_typing(self, _e):
        if self.on_typing:
            self.on_typing()

    def on_boss(self, text):
        self.transcript.append_user(text)

    def on_arven(self, text):
        self.transcript.append_arven(text)

    def on_system(self, text):
        self.transcript.append_system(text)

    def busy(self, state):
        self.transcript.show_typing(state)
        if state:
            self.btn.configure(state="disabled")
            self.btn.set_enabled(False)
        else:
            self.btn.configure(state="normal")
            self.btn.set_enabled(True)


# ----------------------------------------------------------------------
# Talk
# ----------------------------------------------------------------------

class TalkView(tk.Frame):
    """Hands-free, always-listening voice conversation view.

    No push-to-talk button: once Talk mode is entered the controller runs a
    continuous listen/think/speak loop, and this view only reflects its state.
    """

    # Visual status kinds -> (text, colour)
    STATES = {
        "READY": ("Voice ready.", theme.FG_MUTED),
        "LISTENING": ("Listening… speak freely.", theme.AMBER),
        "PROCESSING": ("Thinking…", theme.ACCENT),
        "SPEAKING": ("ARVEN is speaking…", theme.GREEN),
        "ERROR": ("Voice unavailable.", theme.RED),
    }

    def __init__(self, master, on_push_to_talk=None, on_switch=None,
                 on_back=None, on_typing=None):
        super().__init__(master, bg=theme.BG)
        self.on_push_to_talk = on_push_to_talk  # kept for compatibility (unused)

        header = tk.Frame(self, bg=theme.BG_ALT)
        header.pack(fill="x", ipady=14)
        tk.Label(header, text="Talk", font=theme.FONT_LOGO, bg=theme.BG_ALT,
                 fg=theme.FG).pack(side="left", padx=theme.PAD)
        switch = RoundedButton(header, "CHAT", command=on_switch,
                               fill=theme.ACCENT, hover_fill=theme.ACCENT_HOVER,
                               height=36, width=96,
                               font=("Segoe UI", 10, "bold"))
        switch.pack(side="right", padx=theme.PAD)
        tk.Label(header, text="Boss", font=theme.FONT_SMALL, bg=theme.BG_ALT,
                 fg=theme.FG_FAINT).pack(side="right", padx=(0, 8))

        # Always-listening indicator (no push-to-talk mic needed).
        self.indicator = tk.Canvas(self, width=120, height=120, bg=theme.BG,
                                   highlightthickness=0)
        self.indicator.pack(pady=(theme.GAP, 4))
        self._draw_indicator_idle()

        self.status = tk.Label(self, text="", font=theme.FONT_SUB,
                               bg=theme.BG, fg=theme.FG_MUTED)
        self.status.pack(pady=(4, theme.GAP))
        self.set_status("LISTENING")

        self.transcript = ChatTranscript(self, height=7)
        self.transcript.pack(fill="both", expand=True,
                             padx=theme.PAD + 12, pady=(0, theme.GAP))

        _muted_label(self, "Hands-free: just speak · say Bye Arven to close").\
            pack(pady=(0, theme.PAD))

    def _draw_indicator_idle(self):
        self.indicator.delete("all")
        self.indicator.create_oval(10, 10, 110, 110, fill=theme.PANEL,
                                   outline=theme.ACCENT, width=2)
        self.indicator.create_text(60, 60, text="◉", font=("Segoe UI", 30),
                                   fill=theme.AMBER)

    def set_status(self, state_or_text, kind=None):
        if kind is not None:
            # (text, kind) explicit form
            color = {"info": theme.FG_MUTED, "ok": theme.GREEN,
                     "err": theme.RED, "doing": theme.AMBER}.get(
                kind, theme.FG_MUTED)
            self.status.configure(text=state_or_text, fg=color)
            return
        text, color = self.STATES.get(state_or_text,
                                      (state_or_text, theme.FG_MUTED))
        self.status.configure(text=text, fg=color)
        # Recolour the always-listening dot to match the live state.
        dot = {"LISTENING": theme.AMBER, "PROCESSING": theme.ACCENT,
               "SPEAKING": theme.GREEN, "ERROR": theme.RED,
               "READY": theme.FG_MUTED}.get(state_or_text, theme.AMBER)
        self.indicator.delete("all")
        self.indicator.create_oval(10, 10, 110, 110, fill=theme.PANEL,
                                   outline=dot, width=2)
        self.indicator.create_text(60, 60, text="◉", font=("Segoe UI", 30),
                                   fill=dot)

    def on_boss(self, text):
        self.transcript.append_user(text)

    def on_arven(self, text):
        self.transcript.append_arven(text)

    def on_system(self, text):
        self.transcript.append_system(text)

    def busy(self, state):
        self.transcript.show_typing(state)
        self.set_status("PROCESSING" if state else "LISTENING")
