"""ARVEN AI - Step 3 desktop GUI (fresh build).

A clean, modern, borderless ARVEN window with:
  * top-left: temporary ARVEN mark + "ARVEN"
  * top-right: Minimize / Maximize-Restore / Close
  * center: large, EXACTLY centered temporary ARVEN mark/logo
  * right: the CC0 Quaternius "Animated Robot" (software-rendered, smaller
    than the logo, animated via the model's real GLB animation clips)

Opening cinematic (Step 3, after a short wait):
  1. WAIT        - logo centered, robot idle on the right (Idle clip).
  2. TURN_LEFT   - robot smoothly turns to face the logo (world-Y 'turn').
  3. WALK_IN     - robot walks left toward the logo using the real Walking
                   clip (container translation + clip loops supply the gait).
  4. WIND_UP     - brief idle beat right next to the logo.
  5. PUSH        - robot throws the real Punch clip repeatedly; while its
                   arm extends toward the logo the logo is pushed left IN
                   SYNC with the arm's screen-space extension (measured from
                   the rendered silhouette, "as closely as technically
                   possible" with the software renderer); the logo coasts off
                   the LEFT edge and is no longer visible.
  6. TURN_RIGHT  - robot turns to face right.
  7. WALK_CENTER - robot walks back to the exact screen center.
  8. SETTLE      - robot turns to face the camera and glides into Idle,
                   remaining there.

The GUI is fully isolated from the ARVEN backend: it imports only the Python
standard library (tkinter), plus arven_3d (numpy+PIL software renderer).
Optional: if a real logo image exists at data/logo.png, assets/logo.png or
arven_logo.png next to this file, it is used automatically in place of the
drawn placeholder mark (aspect ratio preserved).

Limitation (documented): the GLB's two SKINNED hand meshes (nodes 72/73) are
omitted - their inverse-bind matrices are authored in a space that matches no
combination of the node transforms and their vertex scale is inconsistent with
the joints, so a correct bind is not recoverable from the file. The real arm
meshes (UpperArm/LowerArm) DO animate via the clips; the punch/push is
performed by the actual arm meshes. Smallest fix: re-export hands parented
under the LowerArm nodes (see arven_3d.py docstring).

Launch (from anywhere):
    python arven_gui.py
"""

import time
import tkinter as tk
from pathlib import Path

try:
    from arven_3d import GlbModel
    from PIL import ImageTk as _PIL_ImageTk
    _ROBOT_AVAILABLE = True
except Exception:  # 3D module / deps missing -> GUI still runs, robot area blank
    _ROBOT_AVAILABLE = False

BG = "#0B0B10"
BAR_BG = "#0B0B10"
BUTTON_HOVER = "#1D1D26"
CLOSE_HOVER = "#E53935"
RED = "#E53935"
RED_DARK = "#B71C1C"
PURPLE = "#8B6FE0"
PURPLE_DIM = "#7E57C2"
TEXT = "#F2F2F2"
MUTED = "#8A8A99"

FONT = "Segoe UI"

LOGO_IMAGE_CANDIDATES = (
    Path(__file__).resolve().parent / "data" / "logo.png",
    Path(__file__).resolve().parent / "assets" / "logo.png",
    Path(__file__).resolve().parent / "arven_logo.png",
)

ROBOT_GLB_PATH = (Path(__file__).resolve().parent / "assets"
                  / "3D-character" / "robot_quaternius.glb")

MARK_TAG = "clogo"
SMALL_TAG = "tlogo"

# Animation clip names from the Quaternius GLB
CLIP_IDLE = "RobotArmature|Robot_Idle"
CLIP_WALK = "RobotArmature|Robot_Walking"
CLIP_PUNCH = "RobotArmature|Robot_Punch"

# Facing: robot's face (black head-visor) direction after world-Y 'turn'
TURN_FRONT = 0.0      # face camera
TURN_FACE_LEFT = 270.0   # face screen-left (toward the logo)
TURN_FACE_RIGHT = 90.0   # face screen-right (walking back to center)


def _blend_hex(c1, c2):
    r = int(c1[1:3], 16) + int(c2[1:3], 16)
    g = int(c1[3:5], 16) + int(c2[3:5], 16)
    b = int(c1[5:7], 16) + int(c2[5:7], 16)
    return "#%02X%02X%02X" % (min(255, r // 2), min(255, g // 2), min(255, b // 2))


def draw_mark(canvas, cx, cy, dia, tag):
    """Draw the temporary ARVEN mark (rings + 'A' glyph), ratio-locked."""
    canvas.delete(tag)
    r = dia / 2.0

    halo = _blend_hex(PURPLE, BG)
    canvas.create_oval(cx - r * 1.30, cy - r * 1.30, cx + r * 1.30, cy + r * 1.30,
                       outline=halo, width=1, tags=(tag,))
    canvas.create_oval(cx - r * 1.02, cy - r * 1.02, cx + r * 1.02, cy + r * 1.02,
                       outline=PURPLE_DIM, width=1, tags=(tag,))

    ax = cx
    ay = cy - r * 0.72
    bxl = cx - r * 0.68
    bxr = cx + r * 0.68
    by = cy + r * 0.74

    canvas.create_line(ax, ay, bxl, by, fill=RED, width=max(3, r * 0.26),
                       capstyle="round", tags=(tag,))
    canvas.create_line(ax, ay, bxr, by, fill=RED, width=max(3, r * 0.26),
                       capstyle="round", tags=(tag,))
    canvas.create_line(cx - r * 0.40, cy + r * 0.12, cx + r * 0.40, cy + r * 0.12,
                       fill=PURPLE_DIM, width=max(2, r * 0.18),
                       capstyle="round", tags=(tag,))

    canvas.create_polygon(cx, cy - r * 0.86, cx - r * 0.10, cy - r * 0.66,
                          cx + r * 0.10, cy - r * 0.66,
                          fill=PURPLE, outline="", tags=(tag,))
    canvas.create_oval(cx - r * 0.16, cy + r * 0.30, cx + r * 0.16, cy + r * 0.62,
                       fill=PURPLE_DIM, outline="", tags=(tag,))


class RobotView(tk.Canvas):
    """Controllable container that renders the CC0 Quaternius robot.

    Geometry/layout of this widget is driven programmatically from the main
    canvas (position/size via create_window). The robot is software-rendered
    with numpy+PIL. `set_frame(clip, t, turn)` renders an animated pose;
    `set_rotation`/`set_zoom` control the static bind-pose view.
    """

    THROTTLE_MS = 120

    def __init__(self, master, model_path, **kw):
        kw.setdefault("bg", BG)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(master, **kw)
        self._model = GlbModel(model_path) if _ROBOT_AVAILABLE else None
        self._yaw = 0.0
        self._pitch = 6.0
        self._zoom = 1.0
        self._frame = (None, 0.0, 0.0)   # (clip_index or None, t, turn_deg)
        self._image = None
        self._last_pil = None
        self._last_bbox = (0.0, 0.0, 0.0, 0.0)
        self._after_id = None
        self.bind("<Configure>", lambda _e: self._schedule_render())
        self._render()

    def set_rotation(self, yaw, pitch=None):
        self._yaw = float(yaw)
        if pitch is not None:
            self._pitch = float(pitch)
        self.refresh()

    def set_zoom(self, zoom):
        self._zoom = float(zoom)
        self.refresh()

    def refresh(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._render()

    def set_frame(self, clip, t, turn_deg=0.0):
        """Render clip frame t with world-Y turn; used by the cinematic."""
        self._frame = (clip, float(t), float(turn_deg))
        self.refresh()

    @property
    def last_bbox(self):
        return self._last_bbox

    def robot_screen_left(self, window_x, container_w):
        """Main-canvas X of the robot's left visible edge."""
        return window_x - container_w / 2.0 + self._last_bbox[0]

    def robot_screen_right(self, window_x, container_w):
        return window_x - container_w / 2.0 + self._last_bbox[1]

    def _schedule_render(self):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._after_id = self.after(self.THROTTLE_MS, self._render)

    def _render(self):
        self._after_id = None
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 8 or h < 8:
            return
        if self._model is None:
            self._render_missing(w, h)
            return
        clip, t, turn = self._frame
        try:
            self._model.prepare(clip, t, turn_deg=turn)
            img = self._model.render(w, h, self._yaw, self._pitch, self._zoom)
            self._last_bbox = self._model.last_bbox
            self._last_pil = img
        except Exception:
            img = None
        if img is not None:
            try:
                self._image = _PIL_ImageTk.PhotoImage(img)
                self.delete("all")
                self.create_image(w // 2, h // 2, image=self._image,
                                  anchor="center")
            except Exception:
                pass

    def _render_missing(self, w, h):
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((6, 6), "3D module unavailable", fill=MUTED)
            draw.text((6, 24), str(ROBOT_GLB_PATH.parent), fill=MUTED)
            self._last_pil = img
            self._image = _PIL_ImageTk.PhotoImage(img)
            self.delete("all")
            self.create_image(w // 2, h // 2, image=self._image, anchor="center")
        except Exception:
            pass


class ArvenGui:
    # ---- cinematic tuning (tests may override on the instance) -------------
    CINEMATIC_ENABLED = True          # False keeps the static Step-2 look
    OPENING_DELAY_MS = 3000           # wait before the robot approaches
    TICK_MS = 33                      # ~30 fps ticker
    WALK_SPEED = 0.45                 # px per ms (container translation)
    ROTATE_MS = 500                   # 270->front/->90 turn duration
    PUSH_MS = 900                     # one punch cycle plays at ~1.06x
    PUSH_FORCE = 16.0                 # max logo px moved per punch frame
    EXT_MAX = 10.0                    # bbox px of a fully extended arm
    WIND_UP_MS = 350
    SETTLE_MS = 600
    ROBOT_GAP = 8.0                   # gap between logo and robot at contact
    STAGE_NAMES = ("WAIT", "TURN_LEFT", "WALK_IN", "WIND_UP",
                   "PUSH", "TURN_RIGHT", "WALK_CENTER", "SETTLE", "DONE")

    def __init__(self, root):
        self.root = root
        root.title("ARVEN AI")
        root.configure(bg=BG)
        root.minsize(520, 340)

        self._normal_geometry = None
        self._maximized = False
        self._photo = None
        self._iphoto = None

        root.overrideredirect(True)

        self._title = None
        self._max_btn = None
        self._canvas = None
        self.robot = None
        self._robot_item = None

        # ---- cinematic state -------------------------------------------------
        self._logo_dx = 0.0            # logo horizontal offset from center (px)
        self._robot_x = None           # robot window center x (px), lazily set
        self._stage_i = 0
        self._stage_t0 = 0.0           # monotonic ms when the current stage began
        self._clock0 = time.perf_counter()
        self._test_clock = None
        self._clip = CLIP_IDLE
        self._turn = TURN_FRONT
        self._clip_t = 0.0
        self._push_ref = None          # robot left-edge reference for the push
        self._last_stage_t = None      # mono ms of previous stage tick (delta
        self._ticker = None            #   driver for per-tick movement)
        self._stage_t0 = None

        self._build_titlebar()
        self._build_center()

        root.protocol("WM_DELETE_WINDOW", self._close)
        root.bind("<Map>", self._on_map)

        root.geometry("1000x700")
        root.update_idletasks()
        x = max(0, (root.winfo_screenwidth() - 1000) // 2)
        y = max(0, (root.winfo_screenheight() - 700) // 2)
        root.geometry(f"+{x}+{y}")

        if self.CINEMATIC_ENABLED:
            self._start_ticker()

    # ------------------------------------------------------------------ timing
    def _now(self):
        if self._test_clock is not None:
            return float(self._test_clock)
        return (time.perf_counter() - self._clock0) * 1000.0

    def set_test_clock(self, ms):
        """Deterministic clock for programmatic tests (overrides perf clock)."""
        self._test_clock = float(ms)

    def _start_ticker(self):
        self._ticker = self.root.after(self.TICK_MS, self._tick)

    def _tick(self):
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self._cin_step(self._now())
        self._ticker = self.root.after(self.TICK_MS, self._tick)

    # ------------------------------------------------------------------ parts
    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=BAR_BG, height=54)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        left = tk.Frame(bar, bg=BAR_BG)
        left.pack(side="left", padx=(16, 0), pady=6)
        logo_c = tk.Canvas(left, width=42, height=42, bg=BAR_BG,
                           highlightthickness=0, bd=0)
        logo_c.pack(side="left")
        self._small_logo = logo_c
        draw_mark(logo_c, 21, 21, 26, SMALL_TAG)

        tk.Label(left, text="ARVEN", bg=BAR_BG, fg=TEXT,
                 font=(FONT, 17, "bold")).pack(side="left", padx=(8, 0))

        right = tk.Frame(bar, bg=BAR_BG)
        right.pack(side="right", padx=(0, 6))
        self._max_btn = self._win_button(right, "\u25A1", self._toggle_max,
                                         close=False)
        right_children = list(right.winfo_children())
        self._btn_min = right_children[0] if right_children else None
        self._win_button(right, "\u2013", self._minimize, close=False)
        self._win_button(right, "\u2715", self._close, close=True)

        for widget in (bar, left, logo_c):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

    def _win_button(self, parent, glyph, command, close):
        btn = tk.Button(parent, text=glyph, command=command,
                        bg=BAR_BG, fg=TEXT, relief="flat", borderwidth=0,
                        activebackground=CLOSE_HOVER if close else BUTTON_HOVER,
                        activeforeground=TEXT,
                        font=(FONT, 12 if not close else 13),
                        padx=16, pady=12, cursor="hand2", takefocus=0)
        btn.pack(side="right", fill="y")
        return btn

    def _build_center(self):
        self._canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        if _ROBOT_AVAILABLE:
            self.robot = RobotView(self._canvas, ROBOT_GLB_PATH)
            self._robot_item = self._canvas.create_window(
                0, 0, window=self.robot, anchor="center")
        self._canvas.bind("<Configure>", lambda _e: self._draw_center())
        self._draw_center()

    # ------------------------------------------------------------------ layout
    def _canvas_size(self):
        c = self._canvas
        return max(40, c.winfo_width()), max(40, c.winfo_height())

    @property
    def _logo_dia(self):
        w, h = self._canvas_size()
        return max(80.0, min(w, h) * 0.28)

    def _logo_center_x(self):
        w, _ = self._canvas_size()
        return w / 2.0 + self._logo_dx

    def _logo_half_span(self):
        return self._logo_dia * 0.62

    def _draw_center(self):
        c = self._canvas
        w, h = self._canvas_size()
        cx = self._logo_center_x()
        cy = h / 2
        dia = self._logo_dia
        if self._photo is not None:
            c.delete(MARK_TAG)
            base = int(dia)
            ratio = base / float(max(1, self._photo.height))
            new_w = max(1, int(self._photo.width * ratio))
            resized = self._photo.resize((new_w, base))
            from PIL import ImageTk
            self._iphoto = ImageTk.PhotoImage(resized)
            c.create_image(cx, cy, image=self._iphoto, anchor="center",
                           tags=(MARK_TAG,))
        else:
            draw_mark(c, cx, cy, dia, MARK_TAG)
        c.create_text(cx, cy + dia * 0.62, text="ARVEN",
                      fill=TEXT, font=(FONT, int(dia * 0.18), "bold"),
                      tags=(MARK_TAG,))
        c.create_text(cx, cy + dia * 0.62 + int(dia * 0.14),
                      text="PERSONAL AI ASSISTANT", fill=PURPLE_DIM,
                      font=(FONT, int(dia * 0.055)), tags=(MARK_TAG,))
        self._place_robot()

    def _robot_size(self):
        dia = self._logo_dia
        rh = dia * 1.0
        rw = max(64.0, dia * 0.66)
        return rw, rh

    def _place_robot(self):
        if self._robot_item is None or self.robot is None:
            return
        w, h = self._canvas_size()
        rw, rh = self._robot_size()
        rx = self._robot_x
        if rx is None:
            rx = w * 0.80
            self._robot_x = rx
        ry = h * 0.5
        self._canvas.coords(self._robot_item, rx, ry)
        self._canvas.itemconfigure(self._robot_item, width=rw, height=rh)
        self._robot_size_now = (rw, rh)

    def _load_logo_image(self):
        try:
            from PIL import Image
        except Exception:
            return None
        for path in LOGO_IMAGE_CANDIDATES:
            try:
                if path.exists():
                    return Image.open(path).convert("RGBA")
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------ window
    def _minimize(self):
        if self._maximized:
            self._toggle_max()
        self.root.overrideredirect(False)
        self.root.iconify()

    def _toggle_max(self):
        if self._maximized:
            self._restore()
        else:
            self._maximize()

    def _maximize(self):
        self._normal_geometry = self.root.geometry()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")
        self._maximized = True
        if self._max_btn is not None:
            self._max_btn.configure(text="\u2750")

    def _restore(self):
        if self._normal_geometry:
            self.root.geometry(self._normal_geometry)
        self._maximized = False
        if self._max_btn is not None:
            self._max_btn.configure(text="\u25A1")

    def _close(self):
        self.root.destroy()

    # ------------------------------------------------------------------ drag
    def _drag_start(self, event):
        if self._maximized:
            return
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag_move(self, event):
        if self._maximized:
            return
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _on_map(self, _event):
        if self.root.state() == "normal":
            self.root.overrideredirect(True)

    # ------------------------------------------------------------ cinematic
    def _set_anim(self, clip_name, t, turn):
        self._clip = clip_name
        self._clip_t = t
        self._turn = turn
        if self.robot is not None:
            ci = self.robot._model.clip_index(clip_name) if clip_name else None
            self.robot.set_frame(ci, t, turn)
        self._place_robot()

    def _advance_stage(self, stage_i):
        self._stage_i = stage_i
        self._stage_t0 = self._now()
        self._last_stage_t = self._now()    # fresh per-tick delta baseline

    def _robot_left_px(self):
        rw, _ = getattr(self, "_robot_size_now", (0.0, 0.0))
        if self._robot_x is None:
            return 0.0
        if self.robot is None:
            return self._robot_x
        return self.robot.robot_screen_left(self._robot_x, rw)

    def _robot_fully_left_of_logo(self):
        """Robot's visible silhouette fully past the logo's left edge."""
        if self._robot_x is None:
            return True
        logo = self._logo_center_x() - self._logo_half_span()
        return self._robot_left_px() >= logo

    def _logo_off_screen(self):
        """Logo's right edge beyond the left border -> fully hidden."""
        logo_right = self._logo_center_x() + self._logo_half_span()
        return logo_right <= 0.0

    def _loop_clip_t(self, t, dur, rate):
        if dur <= 0:
            return 0.0
        return (t * rate) % dur

    def _cin_step(self, now):
        """Advance the opening cinematic to absolute mono time `now`."""
        if self.robot is None:
            return
        st = self._stage_i
        f = self._stage_t0
        p = self._last_stage_t
        if f is None:
            f = now
            self._stage_t0 = now
        if p is None:
            p = now
        step_dt = max(0.0, now - p)      # time elapsed since previous tick
        self._last_stage_t = now

        if st == 0:  # WAIT
            self._set_anim(CLIP_IDLE, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_IDLE), 1.0), TURN_FRONT)
            if now - f >= self.OPENING_DELAY_MS:
                self._advance_stage(1)
            return

        if st == 1:  # TURN_LEFT
            k = min(1.0, (now - f) / max(1.0, self.ROTATE_MS))
            turn = TURN_FRONT + (TURN_FACE_LEFT - TURN_FRONT) * k
            self._set_anim(CLIP_IDLE, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_IDLE), 1.0), turn)
            if k >= 1.0:
                self._advance_stage(2)
            return

        if st == 2:  # WALK_IN
            self._set_anim(CLIP_WALK, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_WALK), 1.0), TURN_FACE_LEFT)
            if self._robot_x is None:
                self._robot_x = self._canvas_size()[0] * 0.80
            candidate = self._robot_x - self.WALK_SPEED * step_dt
            logo_right = (self._logo_center_x() + self._logo_half_span()
                          + self.ROBOT_GAP)
            rw, _ = self._robot_size_now
            left_at = candidate - rw / 2.0 + self.robot.last_bbox[0]
            reached = left_at <= logo_right
            if reached and candidate < self._robot_x:
                # stop at the first contact position (never overshoot/bounce)
                self._robot_x = candidate
                self._place_robot()
                self._advance_stage(3)
                return
            self._robot_x = candidate
            self._place_robot()
            if now - f > 6000:
                self._advance_stage(3)
            return

        if st == 3:  # WIND_UP (brief idle beat before the push)
            self._set_anim(CLIP_IDLE, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_IDLE), 1.0), TURN_FACE_LEFT)
            if now - f >= self.WIND_UP_MS:
                self._push_ref = self._robot_left_px()
                self._advance_stage(4)
            return

        if st == 4:  # PUSH
            t = self._loop_clip_t(now - f, self._clip_dur(CLIP_PUNCH), 1.06)
            self._set_anim(CLIP_PUNCH, t, TURN_FACE_LEFT)
            # arm extension toward the logo (screen-left silhouette widened)
            ref = self._push_ref
            if ref is None:
                ref = self._robot_left_px()
                self._push_ref = ref
            ext = max(0.0, ref - self._robot_left_px())
            ext = min(ext, self.EXT_MAX)
            if ext > 0.0:
                ease = 0.35 + 0.65 * (ext / max(1.0, self.EXT_MAX))
                self._logo_dx -= self.PUSH_FORCE * ease
                self._draw_center()
            if self._logo_off_screen() or now - f > self.PUSH_MS * 14:
                self._advance_stage(5)
            return

        if st == 5:  # TURN_RIGHT
            k = min(1.0, (now - f) / max(1.0, self.ROTATE_MS))
            turn = TURN_FACE_LEFT + (TURN_FACE_RIGHT - TURN_FACE_LEFT) * k
            self._set_anim(CLIP_IDLE, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_IDLE), 1.0), turn)
            if k >= 1.0:
                self._advance_stage(6)
            return

        if st == 6:  # WALK_CENTER
            self._set_anim(CLIP_WALK, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_WALK), 1.0), TURN_FACE_RIGHT)
            target = self._canvas_size()[0] / 2.0
            if self._robot_x is not None and abs(self._robot_x - target) > 0.5:
                if self._robot_x < target:
                    self._robot_x += self.WALK_SPEED * step_dt
                    if self._robot_x > target:
                        self._robot_x = target
                else:
                    self._robot_x -= self.WALK_SPEED * step_dt
                    if self._robot_x < target:
                        self._robot_x = target
            self._place_robot()
            if (self._robot_x is not None
                    and abs(self._robot_x - target) <= 0.5
                    or now - f > 6000):
                self._advance_stage(7)
            return

        if st == 7:  # SETTLE (turn to face the camera, then idle in place)
            k = min(1.0, (now - f) / max(1.0, self.SETTLE_MS))
            turn = TURN_FACE_RIGHT + (TURN_FRONT - TURN_FACE_RIGHT) * k
            self._set_anim(CLIP_IDLE, self._loop_clip_t(
                now - f, self._clip_dur(CLIP_IDLE), 1.0), turn)
            if k >= 1.0:
                self._advance_stage(8)
            return

        # DONE: robot idles at center facing the camera
        self._set_anim(CLIP_IDLE, self._loop_clip_t(
            now - f, self._clip_dur(CLIP_IDLE), 1.0), TURN_FRONT)

    def _clip_dur(self, clip_name):
        if self.robot is None or self.robot._model is None:
            return 1.0
        ci = self.robot._model.clip_index(clip_name)
        if ci < 0:
            return 1.0
        return max(0.001, self.robot._model.clips[ci]["duration"])


def main():
    root = tk.Tk()
    gui = ArvenGui(root)
    gui._photo = gui._load_logo_image()
    gui._draw_center()
    root.mainloop()


if __name__ == "__main__":
    main()