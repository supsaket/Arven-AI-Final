"""Custom tkinter widgets for the ARVEN AI desktop shell.

Everything here is pure presentation: no ARVEN intelligence. Widgets are drawn
on a Canvas for a modern, rounded, dark look instead of the stock `ttk` widgets.
"""

import tkinter as tk

from desktop.ui import theme


def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rounded rectangle on a Canvas and return the item id(s)."""
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedButton(tk.Canvas):
    """A flat, rounded, hoverable button drawn on a Canvas."""

    def __init__(self, master, text, command=None, *, fill=theme.ACCENT,
                 fg=theme.FG, font=theme.FONT_BUTTON, height=44, radius=12,
                 hover_fill=None, width=None, bg=theme.BG):
        pad = 24
        text_w = max(60, len(text) * 9)  # rough width estimate for latin text
        w = width if width else (text_w + pad)
        self._height = height
        super().__init__(master, width=w, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.fill = fill
        self.hover_fill = hover_fill or (fill)
        self.fg = fg
        self.font = font
        self.radius = radius
        self._enabled = True
        self._draw(fill, fg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        target = self.fill if enabled else theme.PANEL_2
        self._draw(target, self.fg if enabled else theme.FG_FAINT)
        return self

    def _coords(self):
        return self.radius, self.radius, self.winfo_reqwidth() - self.radius, \
            self._height - self.radius

    def _draw(self, fill, fg):
        self.delete("all")
        x1, y1, x2, y2 = self._coords()
        r = self.radius
        rounded_rect(self, x1, y1, x2, y2, r, fill=fill, outline="", tags="bg")
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        self.create_text(cx, cy, text=self.text, fill=fg, font=self.font,
                         tags="label")

    def _on_enter(self, _e):
        if self._enabled:
            self._transition(self.hover_fill)

    def _on_leave(self, _e):
        if self._enabled:
            self._transition(self.fill)

    def _on_click(self, _e):
        if self._enabled and self.command:
            self.command()

    def _transition(self, target):
        # Simple hover colour transition via a short after loop.
        current = self.fill
        if target == current:
            self._draw(target, self.fg)
            return
        steps = 8
        for i in range(1, steps + 1):
            t = i / steps
            mixed = _blend(current, target, t)
            self.after(i * 12, lambda c=mixed: self._draw(c, self.fg))


def _blend(c1, c2, t):
    """Blend two #RRGGBB colours by t in [0,1]."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    out = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*out)


class TitleBar(tk.Frame):
    """Custom window chrome: drag region + minimize/maximize/close buttons."""

    def __init__(self, master, title, on_min, on_max, on_close,
                 bg=theme.BG, fg=theme.FG):
        super().__init__(master, bg=bg, height=theme.TITLEBAR_H,
                         highlightthickness=0)
        self.pack_propagate(False)

        self._logo = tk.Label(self, text="✦ ARVEN AI", font=theme.FONT_LOGO,
                              bg=bg, fg=theme.ACCENT)
        self._logo.pack(side="left", padx=14)

        # Buttons drawn on simple canvases (no emoji needed).
        self.min_btn = self._draw_btn("\u2013", 46, theme.BG, on_min)
        self.max_btn = self._draw_btn("\u25a1", 46, theme.BG, on_max)
        self.close_btn = self._draw_btn("\u2715", 46, theme.BG, on_close,
                                        hover=theme.RED)

        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.pack(side="right", padx=(0, 2), pady=5)

        # Drag window when grabbing the bar.
        self.bind("<Button-1>", self._start_drag)
        self.bind("<B1-Motion>", self._drag)
        self._logo.bind("<Button-1>", self._start_drag)
        self._logo.bind("<B1-Motion>", self._drag)

    def _draw_btn(self, glyph, size, color, command, hover=None):
        c = tk.Canvas(self, width=size, height=theme.TITLEBAR_H - 10, bg=self["bg"],
                      highlightthickness=0, cursor="hand2")
        c.create_text(size // 2, (theme.TITLEBAR_H - 10) // 2, text=glyph,
                      fill=color, font=("Segoe UI", 12))
        hover = hover or theme.FG_FAINT
        c.bind("<Enter>", lambda _e: self._recolor(glyph, hover, c))
        c.bind("<Leave>", lambda _e: self._recolor(glyph, color, c))
        c.bind("<Button-1>", lambda _e: command())
        return c

    def _recolor(self, glyph, color, canvas):
        canvas.delete("all")
        canvas.create_text(canvas.winfo_width() // 2, (theme.TITLEBAR_H - 10) // 2,
                           text=glyph, fill=color, font=("Segoe UI", 12))

    def _start_drag(self, _e):
        self._drag_x = _e.x_root - self.winfo_toplevel().winfo_x()
        self._drag_y = _e.y_root - self.winfo_toplevel().winfo_y()

    def _drag(self, e):
        try:
            self.winfo_toplevel().geometry(
                f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")
        except Exception:
            pass
