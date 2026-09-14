"""ArvenBridge — the single GUI->backend interface.

All ARVEN backend access happens here. The GUI never talks to core modules
directly; this keeps the dependency direction one way (GUI -> core) and the
whole GUI removable by deleting the ``gui/`` directory.

Routing (same master chain as the terminal CLI):
    1. ``TerminalEngine.act()`` — the Day-3 capability chain
       (intent -> authorization -> confirmation -> registry -> audit/memory/
       event). This is what reaches the existing 123 features.
    2. On honest ``NO_MATCH`` the Day-1 conversational ``Brain.process()`` is
       used (identity / app actions / reason / plan / Ollama chat) — exactly
       the path the existing voice mode uses, so GUI text and voice reach the
       same appropriate backend.

Scheduler, media, camera, voice STT/TTS, files and the registry are all reused
from the existing modules (core.scheduler, tools.builder, voice.input/output).
Nothing here re-implements ARVEN features; every capability goes through the
existing system.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# In-memory KV for Incognito mode (nothing is written to disk)
# ---------------------------------------------------------------------------
class _InMemoryKV:
    """Duck-typed KeyValueStore that never touches disk."""

    def __init__(self):
        self._data = {}
        self._lock = threading.RLock()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
        return True

    def update(self, key, fn, default=None):
        with self._lock:
            old = self._data.get(key, default)
            new = fn(old)
            self._data[key] = new
            return new

    def keys(self, prefix=None):
        keys = sorted(self._data.keys())
        return keys if prefix is None else [k for k in keys if k.startswith(prefix)]

    def as_dict(self):
        return dict(self._data)


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------
class ArvenBridge:
    """Plain, thread-safe backend facade. Methods may be called from any thread."""

    def __init__(self, terminal_kv=None, pins_path=None):
        self._lock = threading.RLock()
        self._terminal_kv = terminal_kv or str(ROOT / "data" / "terminal_engine.json")
        self._pins_path = Path(pins_path) if pins_path else ROOT / "gui" / ".state" / "pins.json"
        self._engine = None
        self._brain = None
        self._scheduler = None
        self._registry = None
        self._incognito_phase = 0

    # ------------------------------------------------------------------ deps
    def registry(self):
        if self._registry is None:
            from tools.builder import build_registry, get_registry
            registry = get_registry()
            if registry is None:
                registry = build_registry()
            self._registry = registry
        return self._registry

    def _new_engine(self, kv):
        from core.kv import KeyValueStore
        from core.planner import AdaptivePlanner
        from core.event_response import EventResponder
        from core.missions import MissionsEngine
        from core.terminal_engine import TerminalEngine
        base = kv if isinstance(kv, _InMemoryKV) else KeyValueStore(str(kv))
        return TerminalEngine(
            kv=base,
            planner=AdaptivePlanner(kv=KeyValueStore("data/planner.json")),
            responder=EventResponder(kv=KeyValueStore("data/event_response.json")),
            missions=MissionsEngine(path="data/runtime/missions.json"),
        )

    def engine(self, incognito=False):
        with self._lock:
            if incognito:
                phase = self._incognito_phase
                self._incognito_phase += 1
                return self._new_engine(_InMemoryKV()), phase
            if self._engine is None:
                self._engine = self._new_engine(self._terminal_kv)
            return self._engine, -1

    def brain(self):
        if self._brain is None:
            from brain.brain import Brain
            self._brain = Brain()
        return self._brain

    def scheduler(self):
        if self._scheduler is None:
            from core.scheduler import Scheduler, TaskStore
            self._scheduler = Scheduler(TaskStore())
        return self._scheduler

    # ------------------------------------------------------------- messaging
    def send(self, text, approve=False, incognito=False, principal="boss"):
        """Run one user message through the real ARVEN routing. Returns a
        plain dict (safe to cross threads). Never raises."""
        text = str(text or "").strip()
        try:
            engine, _phase = self.engine(incognito=incognito)
            result = engine.act(text, approve=approve, principal=principal)
            return self._normalise(result, source="feature", incognito=incognito)
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "ok": False, "source": "error", "status": "ERROR",
                "title": "Backend error", "text": f"{exc}",
                "confirm": False, "request_id": None, "incognito": incognito,
            }

    def _normalise(self, result, source, incognito):
        status = result.get("status") or "ok"
        confirm = bool(result.get("request_id")) or status == "confirm_required"
        title = result.get("action") or status
        body = (result.get("message") or "").strip()
        if status == "NO_MATCH":
            return self._brain_fallback(result, incognito)
        if body and title not in (status, title):
            text = f"{title}: {body}" if source == "feature" else body
        else:
            text = body or status
        data = result.get("result") if isinstance(result.get("result"), dict) else None
        return {
            "ok": bool(result.get("success") is True),
            "source": source, "status": status, "title": title,
            "text": text, "confirm": confirm,
            "request_id": result.get("request_id"),
            "incognito": incognito, "data": data or {},
        }

    def _brain_fallback(self, result, incognito):
        """NO_MATCH -> the Day-1 conversational brain (shared with Voice)."""
        try:
            brain_out = self.brain().process(result.get("action") or "")
            response = str(brain_out.get("response") or "").strip()
            if not response:
                response = result.get("message") or \
                    "I could not find an ARVEN capability for that. " \
                    "State a capability or ask me something conversational."
            return {
                "ok": True, "source": "brain", "status": "chat",
                "title": "ARVEN", "text": response, "confirm": False,
                "request_id": None, "incognito": incognito, "data": {},
            }
        except Exception as exc:
            return {
                "ok": False, "source": "brain", "status": "ERROR",
                "title": "ARVEN", "text": f"Conversation brain unavailable: {exc}",
                "confirm": False, "request_id": None,
                "incognito": incognito, "data": {},
            }

    def perform(self, text, param=None, approve=False, incognito=False,
                principal="boss"):
        """Direct tool invocation by explicit tool name (used by GUI actions
        that already know the exact capability)."""
        text = str(text or "").strip()
        try:
            engine, _phase = self.engine(incognito=incognito)
            result = engine.act(text, param=param or None,
                                approve=approve, principal=principal)
            return self._normalise(result, source="feature", incognito=incognito)
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "ok": False, "source": "error", "status": "ERROR",
                "title": "Backend error", "text": f"{exc}",
                "confirm": False, "request_id": None, "incognito": incognito,
            }

    # ----------------------------------------------------------- confirmation
    def confirm(self, request_id, verdict):
        """Resolve a pending ARVEN confirmation request through the existing
        CONFIRMATION system (yes keeps safety intact; no declines)."""
        try:
            engine, _phase = self.engine()
            return engine.answer(str(request_id), verdict)
        except Exception as exc:
            return {"ok": False, "message": repr(exc), "request_id": request_id}

    # --------------------------------------------------------------- scheduler
    def scheduled_items(self, limit=6):
        try:
            store = self.scheduler().store
            rows = store.upcoming(limit=limit)
            if not rows:
                rows = []
            return {
                "ok": True, "items": [
                    {"id": r.get("id"), "text": r.get("text"),
                     "time": r.get("when") or r.get("time")} for r in rows],
            }
        except Exception as exc:
            return {"ok": False, "items": [], "message": str(exc)}

    def add_scheduled(self, text):
        try:
            out = self.scheduler().schedule(str(text or "").strip())
            return out
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def cancel_scheduled(self, text=None, task_id=None):
        try:
            return self.scheduler().cancel(text=text, task_id=task_id)
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------ media
    def latest_media(self):
        """Most recent generated artwork (image) across ARVEN output dirs."""
        roots = [
            Path(os.environ.get("ARVEN_OUTPUT", "")) if os.environ.get("ARVEN_OUTPUT") else ROOT / "Output",
            ROOT / "GeneratedImages",
            ROOT / "Output" / "ImageGeneration",
        ]
        exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
        best = None
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in exts:
                    if best is None or path.stat().st_mtime > best.stat().st_mtime:
                        best = path
        return {"ok": best is not None, "path": str(best) if best else None}

    def generate_image(self, prompt, width=384, height=384):
        reg = self.registry()
        r = reg.invoke("image_generate", prompt=str(prompt or "ARVEN"),
                       width=int(width), height=int(height))
        path = None
        if isinstance(r.get("result"), dict):
            artefact = r["result"].get("artefact") or {}
            path = artefact.get("path") or r["result"].get("path")
        return {"ok": r.get("success") is True, "status": r.get("status"),
                "message": r.get("message"), "path": path, "result": r}

    def capture_screen(self):
        reg = self.registry()
        return reg.invoke("screen_capture")

    def camera_capture(self):
        reg = self.registry()
        return reg.invoke("camera_capture")

    def grant_camera(self):
        reg = self.registry()
        return reg.invoke("camera_permission_grant")

    # ------------------------------------------------------------------ files
    def read_file(self, path):
        reg = self.registry()
        return reg.invoke("read_file", path=str(path))

    # ------------------------------------------------------------------- voice
    def transcribe(self, duration=5):
        from voice.input import voice_input
        return voice_input.transcribe(duration=int(duration))

    def speak(self, text):
        from voice.output import voice_output
        return voice_output.speak(text)

    def voice_probe(self):
        from voice.input import voice_input
        from voice.output import voice_output
        return {
            "mic": bool(voice_input.microphone_available()),
            "stt": "faster-whisper",
            "tts": voice_output.available(),
        }

    # ------------------------------------------------------------------- health
    def health(self):
        try:
            engine, _ = self.engine()
            h = engine.health()
            worst = h.get("worst_status", "AVAILABLE")
            return {
                "ok": True, "worst": worst, "tools": h.get("registry_tools", 0),
                "providers": h.get("provider_statuses", {}),
            }
        except Exception as exc:
            return {"ok": False, "worst": "ERROR", "tools": 0,
                    "providers": {}, "message": str(exc)}

    # -------------------------------------------------------------------- pins
    def _pins_store(self):
        from core.kv import KeyValueStore
        self._pins_path.parent.mkdir(parents=True, exist_ok=True)
        return KeyValueStore(str(self._pins_path))

    def pin_chat(self, title, turns):
        store = self._pins_store()
        pins = store.get("pins", [])
        entry = {
            "id": f"pin_{int(datetime.now().timestamp() * 100)}",
            "title": str(title or "")[:60] or "Pinned chat",
            "turns": turns[-40:],
            "at": datetime.now().isoformat(),
        }
        pins.append(entry)
        store.set("pins", pins[-50:])
        return {"ok": True, "id": entry["id"]}

    def list_pins(self):
        store = self._pins_store()
        pins = store.get("pins", [])
        return {"ok": True, "pins": [
            {"id": p.get("id"), "title": p.get("title"),
             "at": p.get("at"), "count": len(p.get("turns") or [])}
            for p in pins]}

    def load_pin(self, pin_id):
        store = self._pins_store()
        for p in store.get("pins", []):
            if p.get("id") == pin_id:
                return {"ok": True, "turns": p.get("turns") or [],
                        "title": p.get("title")}
        return {"ok": False, "turns": [], "title": None}

    def remove_pin(self, pin_id):
        store = self._pins_store()
        pins = store.get("pins", [])
        store.set("pins", [p for p in pins if p.get("id") != pin_id])
        return {"ok": True}


__all__ = ["ArvenBridge", "_InMemoryKV"]