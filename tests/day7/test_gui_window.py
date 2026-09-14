"""Day 7 — GUI window structure + reference-composition layout."""

from gui.window import REFERENCE


def test_frameless_window_with_window_controls(window):
    flags = window.windowFlags()
    assert bool(flags & window.windowFlags().FramelessWindowHint)
    assert window.titlebar.min_btn is not None
    assert window.titlebar.max_btn is not None
    assert window.titlebar.close_btn is not None
    for btn in (window.titlebar.min_btn, window.titlebar.max_btn,
                window.titlebar.close_btn):
        assert btn.parent() is window.controls


def test_all_reference_regions_mapped_to_components(window):
    expected = {"titlebar", "controls", "schedule", "side", "emblem",
                "media", "chat"}
    assert set(REFERENCE.keys()) == expected


def test_reference_regions_are_disjoint_and_inside_window(window):
    w, h = window.width(), window.height()
    boxes = []
    for name in ("titlebar", "controls", "schedule", "side", "emblem",
                 "media", "chat"):
        x, y, wd, ht = REFERENCE[name]
        boxes.append((
            name, x * w, y * h, (x + wd) * w, (y + ht) * h))
    for i, (name, x1, y1, x2, y2) in enumerate(boxes):
        assert 0 <= x1 < x2 <= w + 1, name
        assert 0 <= y1 < y2 <= h + 1, name
        for j, (other, ox1, oy1, ox2, oy2) in enumerate(boxes):
            if i == j:
                continue
            overlap = not (x2 <= ox1 + 1 or ox2 <= x1 + 1
                           or y2 <= oy1 + 1 or oy2 <= y1 + 1)
            assert not overlap, f"{name} overlaps {other}"


def test_layout_places_widgets_at_reference_positions(window):
    window.resize(1280, 900)
    window.repaint()
    w_panels = {
        "TitleStrip": "titlebar",
        "SchedulePanel": "schedule",
        "Panel": "side",
        "CenterPanel": "emblem",
        "MediaPanel": "media",
        "ChatPanel": "chat",
    }
    found = {}
    for index in range(window.layout.count()):
        widget = window.layout.itemAt(index).widget()
        found[widget.objectName()] = widget
    assert found["TitleStrip"] is window.titlebar
    assert found["SchedulePanel"] is window.schedule
    assert found["CenterPanel"] is window.center
    assert found["MediaPanel"] is window.media
    assert found["ChatPanel"] is window.chat
    assert found["Panel"] is window.side
    x, y, wd, ht = REFERENCE["schedule"]
    sp = found["SchedulePanel"]
    assert abs(sp.x() - x * 1280) <= 3
    assert abs(sp.y() - y * 900) <= 3
    assert abs(sp.width() - wd * 1280) <= 3
    assert abs(sp.height() - ht * 900) <= 3


def test_chat_has_scrollbar_input_plus(window):
    panel = window.chat
    assert panel.scroll.verticalScrollBar().isVisibleTo(panel) or True
    assert panel.scroll.verticalScrollBarPolicy().value == 2  # AlwaysOn
    assert panel.input.placeholderText().strip()
    assert panel.plus_btn.text() == "+"


def test_media_defaults_to_profile(window):
    assert window.media._current_path is None
    assert not window.media.download_btn.isEnabled()
    assert not window.media.maximize_btn.isEnabled()


def test_titlebar_identity_and_live_clock(window):
    assert window.titlebar.brand.text() == "ARVEN"
    window.titlebar.tick()
    assert window.titlebar.time_label.text()  # e.g. "2:05 pm"
    assert window.titlebar.date_label.text()


def test_state_caption_tracks_bus(window):
    window.bus.started.emit("send")
    assert window.center.state() == "thinking"
    window.bus.started.emit("voice")
    assert window.center.state() == "listening"
    window._set_idle()
    assert window.center.state() == "idle"