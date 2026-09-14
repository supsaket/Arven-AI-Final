"""ARVEN AI dark theme palette + layout tokens.

Central house style for the desktop shell. Keep all colour/spacing decisions
here so views share one coherent look.
"""

# --- Backgrounds -----------------------------------------------------------------
BG = "#0B0F14"            # app background
BG_ALT = "#11161E"        # slightly elevated surface (headers)
PANEL = "#151C26"         # panels / inputs
PANEL_2 = "#1B2430"       # elevated surface (bubbles, hover)
PANEL_3 = "#212C3B"       # active/raised surface

# --- Foregrounds -----------------------------------------------------------------
FG = "#E6EDF3"            # primary text
FG_MUTED = "#9AA7B4"      # secondary text
FG_FAINT = "#5C6B7A"      # tertiary / hints

# --- Accents ---------------------------------------------------------------------
ACCENT = "#3E9BFF"        # primary electric blue
ACCENT_DARK = "#1F6FEA"   # pressed / deep accent
ACCENT_HOVER = "#5FADFF"  # button hover
ACCENT_2 = "#9C6BFF"      # secondary violet
PURPLE = "#9C6BFF"
GREEN = "#34D399"
RED = "#F87171"
AMBER = "#FBBF24"

# --- Chat bubbles -----------------------------------------------------------------
USER_BUBBLE = "#1F4FA8"
ARVEN_BUBBLE = PANEL_2
USER_TEXT = FG
ARVEN_TEXT = FG

# --- Layout tokens ----------------------------------------------------------------
PAD = 24                  # consistent outer margin
GAP = 12                  # vertical rhythm between blocks
TITLEBAR_H = 46

# --- Typography -------------------------------------------------------------------
FONT_FAMILY = "Segoe UI"
FONT = (FONT_FAMILY, 10)
FONT_BOLD = (FONT_FAMILY, 10, "bold")
FONT_TITLE = (FONT_FAMILY, 22, "bold")
FONT_SUB = (FONT_FAMILY, 11)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_LOGO = (FONT_FAMILY, 13, "bold")
FONT_BUTTON = (FONT_FAMILY, 12, "bold")
