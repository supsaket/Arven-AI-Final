"""ARVEN GUI - tiny software rasterizer for the CC0 Quaternius robot GLB.

Parses a glTF 2.0 GLB (positions, indices, node hierarchy, flat material
colors) and renders it with numpy + Pillow only, so the GUI needs no
GPU/WebView/3D dependencies.

Features
--------
* Static rest-pose rendering (bind pose as authored by the node transforms).
* GLB animation clips: LINEAR keyframe sampling (slerp for rotations,
  lerp for translations/scales) applied to the node hierarchy; each sample
  rebuilds the node globals and re-transforms the unskinned primitives.
* ``turn`` rotates the model about its vertical axis so it can face
  left/right/forward without moving the camera (used by the opening
  cinematic: walk toward the logo, punch, walk back).
* Screen-space projection (``project``) and silhouette bounding box
  (``last_bbox``) so the GUI can sync GUI-events with rendered pixels
  (e.g. drive the logo push from the arm extension).

Skeleton skinned parts (the two hands, nodes 72/73) are omitted: their
inverse-bind matrices are authored in a space that does not match any
combination of the node transforms (verified numerically: max
|joint_world @ invBind - I| ~ 2.8 in every candidate space, versus the
body-wide 100x mismatch) and their vertex scale is inconsistent with the
joint scale, so a correct rest binding cannot be recovered from this file
alone. Smallest fix: re-export the hand meshes rigidly parented under the
LowerArm nodes (or re-author bind matrices) in Blender; no code change
would then be needed here beyond rendering the prims.
"""

import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

_COMPONENT_DTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
                     5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_LOOKUP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _mat4(flat_row_major16):
    return np.asarray(flat_row_major16, dtype=np.float64).reshape(4, 4).T


def _slerp(a, b, f):
    """Spherical linear interpolation between two quaternions (shortest path)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na > 0:
        a = a / na
    if nb > 0:
        b = b / nb
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if dot < 0.0:
        dot = -dot
        b = -b
    if dot > 0.9995:  # nearly parallel -> linear + renormalize
        out = a + (b - a) * f
        n = float(np.linalg.norm(out))
        return out / n if n > 0 else a.copy()
    theta = np.arccos(dot)
    w1 = np.sin((1.0 - f) * theta)
    w2 = np.sin(f * theta)
    out = (w1 * a + w2 * b) / np.sin(theta)
    return out / np.linalg.norm(out)


def _trs_matrix(tvec, quat, svec):
    """Compose the translation-rotation-scale local matrix (glTF child-of)."""
    x, y, z, w = float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
    nn = x * x + y * y + z * z + w * w
    if nn > 0:
        inv = 1.0 / np.sqrt(nn)
        x, y, z, w = x * inv, y * inv, z * inv, w * inv
    rot = np.array(
        [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
         [0, 0, 0, 1]], dtype=np.float64)
    sc = np.eye(4)
    sx, sy, sz = float(svec[0]), float(svec[1]), float(svec[2])
    sc[0, 0], sc[1, 1], sc[2, 2] = sx, sy, sz
    tr = np.eye(4)
    tr[:3, 3] = tvec[:3]
    return tr @ rot @ sc


class GlbModel:
    """Minimal GLB model: loads geometry, animates clips, renders frames."""

    def __init__(self, path):
        data = Path(path).read_bytes()
        assert data[:4] == GLB_MAGIC, "not a GLB file"
        off = 12
        chunks = {}
        while off < len(data):
            clen, ctype = struct.unpack("<II", data[off:off + 8])
            chunks[ctype] = data[off + 8:off + 8 + clen]
            off += 8 + clen
        root = json.loads(chunks[CHUNK_JSON].decode("utf-8"))
        self.bin = chunks.get(CHUNK_BIN, b"")
        self._init_from(root)
        self._load_animations(root)
        self._static_center = self._compute_center()
        self._last_view = None
        self._last_bbox = (0.0, 0.0, 0.0, 0.0)

    @property
    def last_bbox(self):
        """Silhouette bbox of the most recent render (canvas pixels)."""
        return self._last_bbox

    # ------------------------------------------------------------ load
    def _init_from(self, root):
        self.bufferViews = root.get("bufferViews", [])
        self.accessors = root.get("accessors", [])
        self.nodes = root.get("nodes", [])
        self.meshes = root.get("meshes", [])
        self.materials = root.get("materials", [])
        self.skins = root.get("skins", [])
        scene_index = root.get("scene", 0)
        scene = root.get("scenes", [{"nodes": []}])[scene_index]
        self.scene_roots = scene.get("nodes", [])
        self.node_children = [nd.get("children", []) for nd in self.nodes]

        node_count = len(self.nodes)
        self.static_t = [None] * node_count
        self.static_r = [None] * node_count
        self.static_s = [None] * node_count
        self.static_matrix_node = [False] * node_count

        local = [np.eye(4) for _ in range(node_count)]
        for i, nd in enumerate(self.nodes):
            if "matrix" in nd:
                local[i] = _mat4(nd["matrix"])
                self.static_matrix_node[i] = True
                self.static_t[i] = np.zeros(3)
                self.static_r[i] = np.array([0.0, 0.0, 0.0, 1.0])
                self.static_s[i] = np.ones(3)
                continue
            t = np.asarray(nd.get("translation", [0, 0, 0]), dtype=np.float64)
            r = np.asarray(nd.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
            s = np.asarray(nd.get("scale", [1, 1, 1]), dtype=np.float64)
            self.static_t[i] = t
            self.static_r[i] = r
            self.static_s[i] = s
            local[i] = _trs_matrix(t, r, s)
        self.static_local = local

        self.globals = self._walk_globals(local)
        self._prim_data = []
        self._prims = []
        self._skinned_skipped = 0

        for node_i, nd in enumerate(self.nodes):
            mesh_i = nd.get("mesh")
            if mesh_i is None:
                continue
            g = self.globals[node_i]
            if g is None:
                continue
            if nd.get("skin") is not None:
                self._skinned_skipped += len(
                    self.meshes[mesh_i].get("primitives", []))
                continue
            for prim in self.meshes[mesh_i].get("primitives", []):
                p = self._load_prim(prim, node_i)
                if p is not None:
                    self._prim_data.append(p)

        pts = self._all_pos()
        self._prims = [dict(idx=d["idx"], color=d["color"], name=d["name"],
                            pos=d["world"]) for d in self._prim_data]
        _ = pts

    def _walk_globals(self, local):
        node_count = len(self.nodes)
        globals_out = [None] * node_count

        def walk(i, acc, seen):
            if i in seen:
                return
            seen.add(i)
            globals_out[i] = acc @ local[i]
            for c in self.node_children[i]:
                walk(c, globals_out[i], seen)

        seen = set()
        for r in self.scene_roots:
            walk(r, np.eye(4), seen)
        return globals_out

    def _load_prim(self, prim, node_i):
        if "JOINTS_0" in prim["attributes"]:
            # skinned part (hand) -- omitted, see module docstring
            return None
        pos = self._accessor(prim["attributes"]["POSITION"])  # (n,3)
        if "indices" in prim:
            idx = self._accessor(prim["indices"]).reshape(-1).astype(np.int64)
        else:
            idx = np.arange(len(pos), dtype=np.int64)
        mat = self._materials_info(prim.get("material"))
        world = self._node_xform(pos, node_i, self.globals)
        return {"node": node_i, "local": pos, "idx": idx, "color": mat["rgb"],
                "name": mat["name"], "world": world}

    def _node_xform(self, pos, node_i, globals_):
        h = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
        return np.einsum("ij,nj->ni", globals_[node_i], h)[:, :3]

    def _materials_info(self, mat_i):
        color = (0.55, 0.55, 0.55)
        name = "Default"
        if mat_i is not None and mat_i < len(self.materials):
            m = self.materials[mat_i]
            name = m.get("name") or "Material"
            pbr = m.get("pbrMetallicRoughness", {})
            color = pbr.get("baseColorFactor", [1, 1, 1, 1])[:3]
        rgb = tuple(max(0, min(255, int(255 * (c ** (1.0 / 2.2))))) for c in color)
        return {"rgb": rgb, "name": name}

    def _accessor(self, ai):
        a = self.accessors[ai]
        bv = self.bufferViews[a["bufferView"]]
        dtype = _COMPONENT_DTYPES[a["componentType"]]
        comp = _LOOKUP[a["type"]]
        n = a["count"]
        itemsz = comp * np.dtype(dtype).itemsize
        stride = bv.get("byteStride", itemsz) or itemsz
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        try:
            arr = np.ndarray(shape=(n, comp), dtype=dtype, buffer=self.bin,
                             offset=base, strides=(stride, np.dtype(dtype).itemsize))
            return arr.astype(np.float64)
        except Exception:
            rows = [np.frombuffer(self.bin, dtype=dtype, count=comp,
                                  offset=base + i * stride) for i in range(n)]
            return np.stack(rows).astype(np.float64)

    # ------------------------------------------------------------ clips
    def _load_animations(self, root):
        self.clips = []
        for ai, anim in enumerate(root.get("animations", [])):
            name = anim.get("name") or "anim%d" % ai
            channels = []
            duration = 0.0
            for c in anim.get("channels", []):
                s = anim["samplers"][c["sampler"]]
                times = self._accessor(s["input"]).reshape(-1)
                data = self._accessor(s["output"])
                node = c["target"].get("node")
                path = c["target"].get("path", "rotation")
                interp = s.get("interpolation", "LINEAR")
                if len(times):
                    duration = max(duration, float(times[-1]))
                channels.append((node, path, times, data, interp))
            self.clips.append({"name": name, "index": ai,
                               "duration": duration, "channels": channels})

    @property
    def clip_names(self):
        return [c["name"] for c in self.clips]

    def clip_index(self, name):
        for i, c in enumerate(self.clips):
            if c["name"] == name:
                return i
        return -1

    def done(self, anim_idx, t):
        """True when t has passed the clip's last keyframe."""
        return t >= self.clips[anim_idx]["duration"]

    @staticmethod
    def _sample_channel(times, data, interp, t):
        n = len(times)
        if n == 0:
            return None
        if n == 1:
            return data[0].copy()
        t0, t1 = float(times[0]), float(times[-1])
        if t <= t0:
            k0, k1, f = 0, 1, 0.0
        elif t >= t1:
            if n >= 2:
                k0, k1, f = n - 2, n - 1, 1.0
            else:
                return data[0].copy()
        else:
            k1 = int(np.searchsorted(times, t, side="right"))
            k0 = k1 - 1
            dt = float(times[k1] - times[k0])
            f = 0.0 if dt <= 0 else (t - times[k0]) / dt
        a, b = data[k0], data[k1]
        if interp == "STEP":
            return a.copy()
        if data.shape[1] == 4:
            return _slerp(a, b, f)
        return a + (b - a) * f

    def _anim_globals(self, anim_idx, t):
        local = [m.copy() for m in self.static_local]
        over = {}
        for node, path, times, data, interp in self.clips[anim_idx]["channels"]:
            if node is None:
                continue
            val = self._sample_channel(times, data, interp, t)
            if val is not None:
                over.setdefault(node, {})[path] = val
        for node, d in over.items():
            if self.static_matrix_node[node]:
                continue
            tv = d.get("translation", self.static_t[node])
            rv = d.get("rotation", self.static_r[node])
            sv = d.get("scale", self.static_s[node])
            local[node] = _trs_matrix(tv, rv, sv)
        return self._walk_globals(local)

    # ------------------------------------------------------------ frames
    def _compute_center(self):
        pts = self._all_pos()
        if not len(pts):
            return np.zeros(3)
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        return (lo + hi) / 2.0

    def _all_pos(self):
        all_pos = []
        for p in self._prims:
            all_pos.append(p["pos"])
        return np.concatenate(all_pos) if all_pos else np.zeros((0, 3))

    def prepare(self, anim=None, t=0.0, turn_deg=0.0):
        """Position all prims for the given clip at time t (None = rest pose).
        Also applies a world-Y ``turn`` so the model can face left/right."""
        if anim is None:
            globs = self.globals
        else:
            globs = self._anim_globals(anim, t)
        for d, pr in zip(self._prim_data, self._prims):
            pr["pos"] = self._node_xform(d["local"], d["node"], globs)
        if turn_deg:
            self._apply_turn(float(turn_deg))

    def _apply_turn(self, turn_deg):
        bx, _, bz = self._static_center
        ang = np.radians(turn_deg)
        c, s = np.cos(ang), np.sin(ang)
        for pr in self._prims:
            v = pr["pos"]
            dx = v[:, 0] - bx
            dz = v[:, 2] - bz
            x = c * dx + s * dz
            z = -s * dx + c * dz
            pr["pos"] = np.stack([x + bx, v[:, 1], z + bz], axis=1)

    # ------------------------------------------------------------ view
    def _view(self, w, h, yaw_deg, pitch_deg, zoom, shift, ss):
        W, H = w * ss, h * ss
        pts = self._all_pos()
        lo = pts.min(axis=0)
        hi = pts.max(axis=0)
        center = (lo + hi) / 2.0
        max_ext = float(max(hi - lo))
        if max_ext <= 0:
            max_ext = 1.0

        yaw = np.radians(yaw_deg)
        pitch = np.radians(pitch_deg)
        dirv = np.array([np.cos(pitch) * np.sin(yaw), np.sin(pitch),
                         np.cos(pitch) * np.cos(yaw)])
        dirv /= np.linalg.norm(dirv)
        up = np.array([0.0, 1.0, 0.0])
        cam_x = np.cross(up, dirv)
        cam_x /= np.linalg.norm(cam_x)
        cam_y = np.cross(dirv, cam_x)
        basis = np.stack([cam_x, cam_y, dirv], axis=1)

        scale = (min(W, H) * 0.72) * zoom / max_ext
        ox = W / 2.0 + shift[0]
        oy = H / 2.0 + shift[1]
        return {"w": w, "h": h, "ss": ss, "W": W, "H": H, "center": center,
                "dirv": dirv, "basis": basis, "scale": scale, "ox": ox,
                "oy": oy}

    def project(self, world_pt):
        """Project a world point to canvas pixels using the last render."""
        v = self._last_view
        if v is None:
            return None
        rel = np.asarray(world_pt, dtype=np.float64) - v["center"]
        c = rel @ v["basis"]
        sx = v["ox"] + v["scale"] * float(c[0])
        sy = v["oy"] - v["scale"] * float(c[1])
        return (sx / v["ss"], sy / v["ss"])

    # ------------------------------------------------------------ render
    def render(self, width, height, yaw_deg=32.0, pitch_deg=8.0, zoom=1.0,
               shift=(0.0, 0.0), supersample=None):
        w, h = max(1, int(width)), max(1, int(height))
        if supersample is None:
            supersample = 2 if max(w, h) <= 700 else 1
        view = self._view(w, h, yaw_deg, pitch_deg, zoom, shift, supersample)
        self._last_view = view
        dirv = view["dirv"]
        basis = view["basis"]
        scale = view["scale"]
        ox, oy = view["ox"], view["oy"]
        center = view["center"]

        # silhouette bbox over all in-front vertices (canvas pixels)
        pts_all = self._all_pos()
        if len(pts_all):
            rel_all = pts_all - center
            zf_all = rel_all @ dirv
            front_pts = rel_all[zf_all > 0.0]
            if len(front_pts):
                cam_all = front_pts @ basis
                sx_all = ox + scale * cam_all[:, 0]
                sy_all = oy - scale * cam_all[:, 1]
                self._last_bbox = (float(sx_all.min()) / supersample,
                                   float(sx_all.max()) / supersample,
                                   float(sy_all.min()) / supersample,
                                   float(sy_all.max()) / supersample)

        faces = []
        for p in self._prims:
            t = p["idx"].reshape(-1, 3)
            if len(t) == 0:
                continue
            v = p["pos"][t]  # (f,3,3)
            e1 = v[:, 1] - v[:, 0]
            e2 = v[:, 2] - v[:, 0]
            n = np.cross(e1, e2)
            nl = np.linalg.norm(n, axis=1)
            ok = nl > 1e-9
            n_unit = np.zeros_like(n)
            n_unit[ok] = n[ok] / nl[ok, None]
            front = n_unit @ dirv > 0
            rel = v - center
            zf = rel @ dirv  # (f,3)
            front &= (zf > 0.0).all(axis=1)
            camera = rel @ basis  # (f,3,3)
            sx = ox + scale * camera[:, :, 0]
            sy = oy - scale * camera[:, :, 1]
            zavg = zf.mean(axis=1)
            pts2d = np.stack([sx, sy], axis=2)[front]
            zright = zavg[front]
            normals_front = n_unit[front]
            base_rgb = p["color"]
            for k in range(len(pts2d)):
                faces.append((float(zright[k]), base_rgb, pts2d[k],
                              normals_front[k]))

        if not faces:
            return Image.new("RGBA", (w, h), (0, 0, 0, 0))

        faces.sort(key=lambda f: f[0], reverse=True)
        light = np.array([0.45, 0.80, 0.38])
        light /= np.linalg.norm(light)

        img = Image.new("RGBA", (view["W"], view["H"]), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for _, color, tri, n in faces:
            diff = max(0.0, float(n @ light))
            if not np.isfinite(diff):
                diff = 0.0
            intensity = 0.32 + 0.68 * diff
            rgb = tuple(max(0, min(255, int(ch * intensity))) for ch in color)
            draw.polygon([(float(x), float(y)) for x, y in tri], fill=rgb + (255,))

        if supersample > 1:
            img = img.resize((w, h), Image.LANCZOS)
        return img