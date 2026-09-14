"""ARVEN GUI stylesheet + palette (single source for the reference look).

Light polished surface (the wireframe is a pencil sketch on light paper) with a
green border for the schedule panel, dark navy ARVEN identity accents and airy,
clean typography.
"""

PALETTE = {
    "bg": "#F2F4F7",
    "panel": "#FFFFFF",
    "panel_border": "#D8DEE5",
    "ink": "#1B2733",
    "muted": "#5B6B7C",
    "navy": "#16233A",
    "navy_light": "#2C4258",
    "green": "#3E9B4F",
    "green_soft": "#E3F2E4",
    "silver": "#C9D4E0",
    "user_bubble": "#16233A",
    "user_text": "#FFFFFF",
    "assistant_bubble": "#E7ECF2",
    "assistant_text": "#1B2733",
    "error": "#C0392B",
    "warn": "#B7840B",
}


def app_stylesheet():
    p = PALETTE
    return f"""
QMainWindow {{ background: {p['bg']}; }}
* {{ font-family: "Segoe UI", "Segoe UI Variable Text"; }}

#ReferenceRoot {{ background: {p['bg']}; }}

/* ---------- panels (rounded, white) ---------- */
#Panel {{
    background: {p['panel']};
    border: 1px solid {p['panel_border']};
    border-radius: 14px;
}}
#PanelTitle {{
    color: {p['ink']};
    font-size: 15px;
    font-weight: 700;
}}
#PanelSub {{
    color: {p['muted']};
    font-size: 12px;
}}

/* ---------- identity / clock ---------- */
#BrandName {{ color: {p['navy']}; font-size: 40px; font-weight: 800; letter-spacing: 1px; }}
#ClockTime {{ color: {p['ink']}; font-size: 30px; font-weight: 700; }}
#ClockDate {{ color: {p['muted']}; font-size: 12px; }}
#StatusWord {{ color: {p['green']}; font-size: 13px; font-weight: 600; }}

/* ---------- schedule panel ---------- */
#SchedulePanel {{
    background: {p['panel']};
    border: 2px solid {p['green']};
    border-radius: 14px;
}}
#ScheduleTitle {{ color: {p['navy']}; font-size: 14px; font-weight: 700; }}
#ScheduleRow {{ color: {p['ink']}; font-size: 13px; }}
#ScheduleRowTime {{ color: {p['green']}; font-weight: 700; }}
#ScheduleEmpty {{ color: {p['muted']}; font-size: 12px; font-style: italic; }}
#ScheduleAdd {{
    background: {p['green_soft']};
    color: {p['green']};
    border: 1px solid {p['green']};
    border-radius: 10px;
    font-weight: 700;
    padding: 4px 12px;
}}
#ScheduleAdd:hover {{ background: {p['green']}; color: white; }}

/* ---------- right controls ---------- */
#SideButton {{
    background: {p['panel']};
    border: 1px solid {p['panel_border']};
    border-radius: 12px;
    color: {p['navy']};
    font-weight: 700;
    text-align: center;
}}
#SideButton:hover {{ border-color: {p['green']}; background: #F4FAF5; }}
#SideButton:pressed {{ background: {p['green_soft']}; }}
#SideButton[active="true"] {{
    background: {p['green']};
    color: white;
    border: 1px solid {p['green']};
}}
#SideCaption {{ color: {p['muted']}; font-size: 10px; }}

/* ---------- chat ---------- */
#ChatPanel {{ background: {p['panel']}; border: 1px solid {p['panel_border']}; border-radius: 14px; }}
#ChatScroll {{
    background: transparent;
    border: none;
    outline: none;
}}
#ChatScroll {{ border: none; }}
#ChatScroll QScrollBar:vertical {{
    background: {p['panel']};
    width: 10px;
    border-radius: 5px;
}}
#ChatScroll QScrollBar::handle:vertical {{
    background: {p['silver']};
    border-radius: 5px;
    min-height: 24px;
}}
#ChatScroll QScrollBar::add-line:vertical, #ChatScroll QScrollBar::sub-line:vertical {{
    height: 0px;
}}
#ChatScroll QScrollBar::add-page:vertical, #ChatScroll QScrollBar::sub-page:vertical {{
    background: transparent;
}}
#ChatInput {{
    background: {p['bg']};
    border: 1px solid {p['panel_border']};
    border-radius: 12px;
    padding: 8px 12px;
    color: {p['ink']};
    font-size: 13px;
}}
#ChatInput:focus {{ border-color: {p['green']}; }}
#ChatPlus {{
    background: {p['green_soft']};
    border: 1px solid {p['green']};
    border-radius: 12px;
    color: {p['green']};
    font-size: 20px;
    font-weight: 700;
}}
#ChatPlus:hover {{ background: {p['green']}; color: white; }}
#UserBubble {{
    background: {p['user_bubble']};
    color: {p['user_text']};
    border-radius: 12px;
    padding: 8px 12px;
    font-size: 13px;
}}
#AssistantBubble {{
    background: {p['assistant_bubble']};
    color: {p['assistant_text']};
    border-radius: 12px;
    padding: 8px 12px;
    font-size: 13px;
}}
#ChatMeta {{ color: {p['muted']}; font-size: 10px; }}
#ChatSystem {{ color: {p['warn']}; font-size: 11px; }}
#IncognitoTag {{
    background: {p['green']};
    color: white;
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
}}

/* ---------- media ---------- */
#MediaPanel {{ background: {p['panel']}; border: 1px solid {p['panel_border']}; border-radius: 14px; }}
#MediaView {{ background: #E9EDF2; border: 1px solid {p['panel_border']}; border-radius: 10px; }}
#MediaButton {{
    background: {p['panel']};
    border: 1px solid {p['panel_border']};
    border-radius: 10px;
    color: {p['navy']};
    font-weight: 600;
    padding: 4px 10px;
}}
#MediaButton:hover {{ border-color: {p['green']}; color: {p['green']}; }}

/* ---------- window controls ---------- */
#WinButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {p['ink']};
    font-size: 14px;
}}
#WinButton:hover {{ background: {p['panel_border']}; }}
#WinButton[destructive="true"]:hover {{ background: #C0392B; color: white; }}

/* ---------- titlebar drag strip ---------- */
#TitleStrip {{ background: transparent; }}

/* ---------- generic buttons / dialogs ---------- */
QPushButton {{ outline: none; }}
QToolTip {{ background: {p['navy']}; color: {p['bg']}; border: none; padding: 4px 8px; }}
#OkButton {{
    background: {p['green']};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 6px 16px;
    font-weight: 700;
}}
#DenyButton {{
    background: {p['panel']};
    color: {p['muted']};
    border: 1px solid {p['panel_border']};
    border-radius: 8px;
    padding: 6px 16px;
}}
QDialog {{ background: {p['bg']}; }}
"""


__all__ = ["PALETTE", "app_stylesheet"]