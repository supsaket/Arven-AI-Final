"""Feature 109 — Resource & Capability Awareness.

Honest, offline-first probing of what ARVEN can do right now: hardware,
software, providers, permissions and the capability graph. Every probe is
best-effort and NEVER invents a capability:

* missing binaries / modules report NOT_INSTALLED
* GPU is only reported when a detector (nvidia-smi) actually answers
* providers come from the authoritative ``providers_registry``
* a fresh snapshot is cached with a TTL; ``refresh(force=True)`` re-probes
* ``restore()`` re-reads the persisted snapshot (restart recovery) and
  ``stale`` flags a snapshot older than twice the TTL

All probes are stdlib-first and never block longer than a short bound.
"""

import ctypes
import importlib.util
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time

from core.kv import KeyValueStore

_DEFAULT_PATH = "data/capability_awareness.json"
_TTL = 45.0

_STATUS_AVAILABLE = "AVAILABLE"
_STATUS_UNAVAILABLE = "UNAVAILABLE"
_STATUS_NOT_INSTALLED = "NOT_INSTALLED"
_STATUS_NOT_DETECTED = "NOT_DETECTED"
_STATUS_UNVERIFIED = "UNVERIFIED"

# name -> (module, or None for shutil.which(name)) — key software checks.
_SOFTWARE_CHECKS = {
    "python": ("python_toolcheck", None),
    "git": ("git_toolcheck", "git"),
    "node": ("node_toolcheck", "node"),
    "docker": ("docker_toolcheck", "docker"),
    "ffmpeg": ("ffmpeg_toolcheck", "ffmpeg"),
    "ollama": ("ollama", None),
    "pytest": ("pytest", None),
    "PIL": ("PIL", None),
    "numpy": ("numpy", None),
    "psutil": ("psutil", None),
    "sounddevice": ("sounddevice", None),
    "pycaw": ("pycaw", None),
    "cv2": ("cv2", None),
    "faster_whisper": ("faster_whisper", None),
    "playwright": ("playwright", None),
}

_GRAPH_QUESTIONS = (
    ("what_exists", "Which features exist in the catalog?"),
    ("what_is_available", "What can ARVEN do right now?"),
    ("what_needs_configuration", "What needs configuration before use?"),
    ("what_is_unavailable", "What is not reachable right now?"),
    ("what_resources", "What compute/storage resources are available?"),
    ("what_software", "Which key software is installed?"),
    ("what_dependencies", "What does a feature/operation depend on?"),
    ("what_permissions", "Which permissions/grants are recorded?"),
    ("what_to_fix", "What should be fixed or enabled next?"),
)


def _probe_network(timeout=1.0):
    """True when a route exists; never raises."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except Exception:
        return False


def _ram_bytes():
    """Total/available physical RAM on win32 via GlobalMemoryStatusEx."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        if not ok:
            return None, None
        return stat.ullTotalPhys, stat.ullAvailPhys
    except Exception:
        return None, None


def _gpu_info():
    """nvidia-smi -L parse. Honest: only reported when it actually answers."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True, text=True,
            timeout=2.0)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    gpus = [line.strip() for line in out.stdout.splitlines()
            if line.strip().startswith("GPU ")]
    return gpus or None


def _probe_hardware():
    total, avail = _ram_bytes()
    try:
        usage = shutil.disk_usage(".")
    except Exception:
        usage = None

    network = _probe_network()
    gpus = _gpu_info()

    mic = _STATUS_NOT_INSTALLED
    mic_note = "no audio-probe library (sounddevice) installed"
    if importlib.util.find_spec("sounddevice"):
        mic = _STATUS_AVAILABLE
        mic_note = "sounddevice present; device unverified until first capture"
    elif importlib.util.find_spec("pyaudio"):
        mic = _STATUS_AVAILABLE
        mic_note = "pyaudio present; device unverified until first capture"

    speaker = _STATUS_UNVERIFIED
    speaker_note = "Windows SAPI assumed; not measured"
    if not (sys.platform.startswith("win") or sys.platform == "darwin"):
        speaker = _STATUS_UNAVAILABLE
        speaker_note = "no OS TTS backend detected on this platform"

    cam = _STATUS_NOT_INSTALLED
    cam_note = "no camera library (cv2) installed"
    if importlib.util.find_spec("cv2"):
        try:
            import cv2  # noqa: PLC0415
            cap = cv2.VideoCapture(0)
            opened = bool(cap.isOpened())
            cap.release()
            cam = _STATUS_AVAILABLE if opened else _STATUS_UNAVAILABLE
            cam_note = "camera answered isOpened()" if opened else \
                "camera did not open (permission or absence)"
        except Exception as exc:
            cam = _STATUS_UNAVAILABLE
            cam_note = f"camera probe failed: {exc}"

    return {
        "cpu": {
            "cores": os.cpu_count(),
            "processor": platform.processor() or platform.machine(),
            "platform": platform.system(),
            "machine": platform.machine(),
        },
        "ram": {
            "total_bytes": total,
            "available_bytes": avail,
            "available_pct":
                (round(100.0 * avail / total, 1)
                 if total and avail is not None else None),
        },
        "storage": ({"total_bytes": usage.total,
                     "free_bytes": usage.free,
                     "free_pct": round(100.0 * usage.free / usage.total, 1)}
                    if usage else None),
        "gpu": ({"status": _STATUS_AVAILABLE, "devices": gpus}
                if gpus else
                {"status": _STATUS_NOT_DETECTED,
                 "note": "no NVIDIA GPU detected (only nvidia-smi is queried)"}),
        "network": {"connected": network,
                    "status": _STATUS_AVAILABLE if network
                              else "OFFLINE"},
        "mic": {"status": mic, "note": mic_note},
        "speaker": {"status": speaker, "note": speaker_note},
        "camera": {"status": cam, "note": cam_note},
    }


def _probe_software():
    """Key toolchain binaries / modules. Honest present-or-absent."""
    result = {}
    for name, (module, binary) in _SOFTWARE_CHECKS.items():
        entry = {"available": False}
        if module == "python_toolcheck":
            entry = {"available": True, "path": sys.executable,
                     "version": platform.python_version()}
        elif binary is not None:
            path = shutil.which(binary)
            if path:
                entry = {"available": True, "path": path}
        else:
            spec = importlib.util.find_spec(module)
            if spec is not None:
                entry = {"available": True, "module": module,
                         "origin": getattr(spec, "origin", "builtin")}
        result[name] = entry
    return result


def _probe_providers():
    from core.providers.registry import providers_registry
    _ensure_providers_registered()
    rows = providers_registry.status_all()
    return {r.get("name"): r.get("status") for r in rows}


def _ensure_providers_registered():
    """Import concrete provider modules so their register_* hooks run.

    Matches the Day 2 lazy-registration convention; importing a provider
    module only sets statuses — it never executes capabilities.
    """
    import importlib
    import pkgutil
    import core.providers as pkg
    try:
        for _info in pkgutil.iter_modules(pkg.__path__):
            if _info.name in ("base", "registry", "devices_world"):
                continue
            try:
                module = importlib.import_module(
                    f"core.providers.{_info.name}")
            except Exception:
                continue
            for attr in sorted(vars(module)):
                if attr.startswith("register_"):
                    try:
                        getattr(module, attr)()
                    except Exception:
                        continue
    except Exception:
        return


def _probe_permissions():
    """Read-only view of the access store — never creates or mutates it."""
    try:
        store = KeyValueStore("data/access.json")
        grants = store.get("_grants") or []
        roles = {k: v for k, v in store.as_dict().items()
                 if k.startswith("_role_")}
        return {
            "configured": bool(grants) or bool(roles),
            "grant_count": len(grants),
            "grants": grants,
            "roles": roles,
            "note": "read-only snapshot of data/access.json",
        }
    except Exception as exc:
        return {"configured": False, "grant_count": 0, "grants": [],
                "roles": {}, "note": f"permission probe failed: {exc}"}


def _probe_capabilities():
    from core.capabilities import capabilities
    return capabilities.status(offline=False)


class CapabilityAwareness:
    """Cached snapshot of resources + a self-answering capability graph."""

    def __init__(self, kv_path=None, ttl=_TTL):
        self.path = str(kv_path) if kv_path else _DEFAULT_PATH
        self.ttl = float(ttl)
        self.store = KeyValueStore(self.path)
        self._cache = None
        self._generated_at = 0.0

    # ------------------------------------------------------------------
    # probing / caching
    # ------------------------------------------------------------------
    def _build(self):
        return {
            "generated_at": time.time(),
            "hardware": _probe_hardware(),
            "software": _probe_software(),
            "providers": _probe_providers(),
            "permissions": _probe_permissions(),
            "capabilities": _probe_capabilities(),
        }

    def probe(self, force=False):
        now = time.time()
        if (not force and self._cache is not None
                and (now - self._generated_at) <= self.ttl):
            cached = dict(self._cache)
            cached["cached"] = True
            return cached
        snapshot = self._build()
        snapshot["cached"] = False
        self._cache = snapshot
        self._generated_at = snapshot["generated_at"]
        self.store.set("snapshot.latest", {
            "generated_at": snapshot["generated_at"],
            "hardware": snapshot["hardware"],
            "software": snapshot["software"],
            "providers": snapshot["providers"],
            "permissions": snapshot["permissions"],
            "capabilities": snapshot["capabilities"],
        })
        return snapshot

    def refresh(self):
        """Force a re-probe. Returns the fresh snapshot."""
        return self.probe(force=True)

    def restore(self):
        """Restart recovery: re-read the persisted snapshot from disk."""
        saved = self.store.get("snapshot.latest")
        if not saved:
            return {"restored": False, "stale": True,
                    "snapshot": None, "reason": "no persisted snapshot"}
        generated = float(saved.get("generated_at") or 0.0)
        stale = (time.time() - generated) > (2.0 * self.ttl)
        self._cache = dict(saved)
        self._cache["cached"] = True
        self._generated_at = generated
        return {"restored": True, "stale": stale, "snapshot": saved,
                "age_seconds": round(time.time() - generated, 1)}

    # ------------------------------------------------------------------
    # capability graph
    # ------------------------------------------------------------------
    def graph(self, question=None):
        snapshot = self.probe()
        caps = snapshot.get("capabilities", {})
        answers = {
            "what_exists": {
                "answer": "ARVEN catalogs its feature set; the registry is the "
                          "authoritative tool set",
                "catalog_total": None,  # filled from the catalog below
                "catalog_tool_refs": None,  # filled from the catalog below
                "registry_tools": None,  # filled from registry when available
            },
            "what_is_available": {
                "answer": "Capabilities resolved AVAILABLE plus every "
                          "registered tool",
                "capabilities": {k: v for k, v in caps.items()
                                 if v == "available"},
            },
            "what_needs_configuration": {
                "answer": "Providers/capabilities sitting NOT_CONFIGURED",
                "not_configured": self._status_bucket(
                    snapshot, ("NOT_CONFIGURED", "not_configured")),
            },
            "what_is_unavailable": {
                "answer": "Providers reported UNAVAILABLE/FAILED/OFFLINE",
                "unavailable": self._status_bucket(
                    snapshot, ("UNAVAILABLE", "FAILED", "OFFLINE")),
            },
            "what_resources": {
                "answer": "CPU cores, RAM, storage and GPU status",
                "resources": {
                    "cores": snapshot.get("hardware", {}).get("cpu", {}).get("cores"),
                    "ram": snapshot.get("hardware", {}).get("ram"),
                    "storage": snapshot.get("hardware", {}).get("storage"),
                    "gpu": snapshot.get("hardware", {}).get("gpu"),
                    "network": snapshot.get("hardware", {}).get("network"),
                },
            },
            "what_software": {
                "answer": "Key binaries/modules present on this machine",
                "software": {k: v for k, v in
                             snapshot.get("software", {}).items()
                             if v.get("available")},
                "missing": [k for k, v in
                            snapshot.get("software", {}).items()
                            if not v.get("available")],
            },
            "what_dependencies": {
                "answer": "Per-feature module/tool/dependency summary",
                "dependencies": self.dependencies(),
            },
            "what_permissions": {
                "answer": "Recorded access grants (read-only)",
                "permissions": snapshot.get("permissions", {}),
            },
            "what_to_fix": {
                "answer": "Honest recommendations from probe results",
                "recommendations": self._recommendations(snapshot),
            },
        }

        # Fill registry/catalog facts from the live registry (cheap snapshot).
        try:
            from core.features import list_features
            all_features = list_features()
            answers["what_exists"]["catalog_total"] = len(all_features)
            answers["what_exists"]["catalog_tool_refs"] = sum(
                len(f["tools"]) for f in all_features)
            from tools.builder import get_registry
            answers["what_exists"]["registry_tools"] = \
                len(get_registry().names())
            answers["what_is_available"]["registry_tools"] = \
                len(get_registry().names())
            answers["what_is_available"]["available_tools"] = \
                sum(1 for t in get_registry().all() if t.available)
        except Exception:
            pass

        if question is not None:
            key = str(question).lower().replace("?", "").strip()
            if key in answers:
                return {"question": key, "answer": answers[key]}
            return {"question": key, "error": "unknown question"}
        return answers

    def _status_bucket(self, snapshot, needles):
        needles = {str(n).lower() for n in needles}
        providers = snapshot.get("providers", {})
        caps = snapshot.get("capabilities", {})
        out = {"providers": {}, "capabilities": {}}
        for name, status in sorted(providers.items()):
            if str(status).lower() in needles:
                out["providers"][name] = status
        for name, status in sorted(caps.items()):
            if str(status).lower() in needles:
                out["capabilities"][name] = status
        return out

    def _recommendations(self, snapshot):
        recs = []
        hardware = snapshot.get("hardware", {})
        if hardware.get("gpu", {}).get("status") != _STATUS_AVAILABLE:
            recs.append({"item": "gpu",
                         "advice": "no GPU detected — vision/media rock no "
                                   "local accelerator"})
        if not hardware.get("network", {}).get("connected"):
            recs.append({"item": "network",
                         "advice": "offline — web/email/search will report "
                                   "OFFLINE honestly"})
        if not snapshot.get("software", {}).get("ollama", {}).get("available"):
            recs.append({"item": "ollama",
                         "advice": "ollama not installed — local model "
                                   "features report NOT_CONFIGURED"})
        not_conf = self._status_bucket(snapshot, ("NOT_CONFIGURED",))
        not_conf_providers = getattr(not_conf.get("providers", {}), "keys", [])()
        if not_conf_providers:
            recs.append({"item": "providers",
                         "advice": "configure or decline: "
                                   + ", ".join(sorted(not_conf_providers))})
        return recs

    # ------------------------------------------------------------------
    # dependency map
    # ------------------------------------------------------------------
    def dependencies(self, feature_id=None):
        from core.features import feature, list_features
        if feature_id is not None:
            row = feature(feature_id)
            if row is None:
                return {"error": f"unknown feature id {feature_id}"}
            return {
                "feature_id": row["id"],
                "name": row["name"],
                "modules": list(row["modules"]),
                "tools": list(row["tools"]),
                "dependency": row["dependency"],
                "offline": row["offline"],
                "persistence": row["persistence"],
                "recovery": row["recovery"],
            }
        modules = []
        tools = []
        for row in list_features():
            modules.extend(row["modules"])
            tools.extend(row["tools"])
        return {
            "feature_count": len(list_features()),
            "module_refs": len(set(modules)),
            "tool_refs": len(set(tools)),
            "offline_full": sum(1 for r in list_features()
                                if r["offline"] is True),
            "offline_partial": sum(1 for r in list_features()
                                   if r["offline"] == "partial"),
            "offline_network": sum(1 for r in list_features()
                                   if r["offline"] is False),
        }


capability_awareness = CapabilityAwareness()

__all__ = [
    "CapabilityAwareness",
    "capability_awareness",
    "_probe_hardware",
    "_probe_software",
    "_probe_providers",
    "_probe_permissions",
    "_probe_capabilities",
    "_GRAPH_QUESTIONS",
]