"""Chat transcript widget (styled, scrollable, user/ARVEN distinct).

Renders conversation history with clear visual separation between the Boss and
ARVEN using text tags (right-aligned user bubbles vs left-aligned ARVEN).
Includes a typing/loading indicator row.
"""

import tkinter as tk
from tkinter import font as tkfont

from desktop.ui import theme


class ChatTranscript(tk.Text):
    """A read-only, scrollable chat transcript with per-sender styling."""

    def __init__(self, master, **kw):
        super().__init__(master, wrap="word", state="disabled",
                         bg=theme.BG, fg=theme.FG,
                         insertbackground=theme.FG,
                         highlightthickness=0, bd=0,
                         relief="flat", padx=18, pady=16, **kw)
        self._font = tkfont.Font(font=theme.FONT)
        self._configure_tags()
        self.typing = False

    def _configure_tags(self):
        self.tag_configure("user_name", foreground=theme.GREEN,
                           font=theme.FONT_BOLD, spacing3=6)
        self.tag_configure("user_body", foreground=theme.FG,
                           font=theme.FONT, spacing2=2, spacing3=10,
                           lmargin1=0, lmargin2=0)
        self.tag_configure("arv_name", foreground=theme.ACCENT,
                           font=theme.FONT_BOLD, spacing3=6)
        self.tag_configure("arv_body", foreground=theme.FG,
                           font=theme.FONT, spacing2=2, spacing3=10)
        self.tag_configure("system", foreground=theme.FG_MUTED,
                           font=theme.FONT_SMALL, spacing3=8)
        self.tag_configure("typing", foreground=theme.ACCENT_2,
                           font=theme.FONT, spacing3=12)

    def append_user(self, text):
        self._append(f"You", text, "user_name", "user_body")

    def append_arven(self, text):
        self._append("ARVEN", text, "arv_name", "arv_body")

    def append_system(self, text):
        self._write(f"◆ {text}\n", "system")

    def _append(self, name, body, name_tag, body_tag):
        self._write(f"{name}\n", name_tag)
        self._write(f"{body}\n\n", body_tag)

    def _write(self, text, tag):
        self.configure(state="normal")
        self.insert("end", text, tag)
        self.configure(state="disabled")
        self._scroll_bottom()

    def _scroll_bottom(self):
        self.see("end")
        self.update_idletasks()

    def show_typing(self, enabled=True):
        if enabled and not self.typing:
            self.typing = True
            self._typing_start = self.index("end-1c")
            self.configure(state="normal")
            self.insert("end", "ARVEN is thinking…\n", "typing")
            self.configure(state="disabled")
            self._typing_end = self.index("end-1c")
            self._scroll_bottom()
        elif not enabled and self.typing:
            self.typing = False
            start = self._typing_start
            end = self._typing_end
            self.configure(state="normal")
            self.delete(start, end)
            self.configure(state="disabled")
            self._scroll_bottom()
