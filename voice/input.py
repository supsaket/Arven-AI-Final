"""Voice input (STT) — microphone capture + faster-whisper transcription.

Interface contract (verify_voice.py / verify_stt.py):
* ``voice_input._resolve_backend()``  — which capture backend will be used
* ``voice_input.microphone_available()``  — real device probe (with retries)
* ``voice_input.list_microphones()`` — enumerated input devices
* ``voice_input.load_model()`` — safely (re)load faster-whisper
* ``voice_input.transcribe(duration, ...)`` — bounded capture + transcription
* ``create_stt_backend(provider=None)`` — factory returning a backend dict

Honesty: if no microphone is present, transcription reports unavailable
rather than faking audio. faster-whisper is installed, so once a mic exists
transcription is fully local and offline.
"""

import json
import time

from config import get_settings

try:
    import sounddevice as sd
    HAVE_SOUNDDEVICE = True
except Exception:  # pragma: no cover
    sd = None
    HAVE_SOUNDDEVICE = False

try:
    from faster_whisper import WhisperModel
    HAVE_FWHISPER = True
except Exception:  # pragma: no cover
    HAVE_FWHISPER = False


class VoiceInput:

    def __init__(self):
        self.model = None
        self.model_path = None

    # ------------------------------------------------------------------
    def _resolve_backend(self):
        if HAVE_SOUNDDEVICE:
            return "sounddevice"
        return "none"

    def microphone_available(self):
        if not HAVE_SOUNDDEVICE:
            return False
        # retries: com/audio init can be flaky on first call
        for attempt in range(3):
            try:
                devices = sd.query_devices()
                for device in devices:
                    if device.get("max_input_channels", 0) > 0:
                        return True
            except Exception:
                time.sleep(0.1)
        return False

    def list_microphones(self):
        mics = []
        if not HAVE_SOUNDDEVICE:
            return mics
        try:
            devices = sd.query_devices()
            for index, device in enumerate(devices):
                if device.get("max_input_channels", 0) > 0:
                    mics.append({
                        "index": index,
                        "name": device.get("name", f"input {index}"),
                        "channels": device["max_input_channels"],
                        "backend": "sounddevice",
                    })
        except Exception:
            pass
        return mics

    # ------------------------------------------------------------------
    def load_model(self):
        settings = get_settings()
        size = settings.get("STT_MODEL_SIZE", "base")
        device = settings.get("STT_DEVICE", "auto")
        compute = settings.get("STT_COMPUTE_TYPE", "int8")
        if not HAVE_FWHISPER:
            return False
        try:
            self.model = WhisperModel(
                str(size),
                device=str(device),
                compute_type=str(compute),
            )
            self.model_path = size
            return True
        except Exception:
            self.model = None
            self.model_path = None
            return False

    def _model_available(self):
        if self.model is None:
            return False
        return True

    def transcribe(self, duration=5, sample_rate=16000, filename=None):
        """Capture N seconds from the default mic and transcribe locally.

        Returns a structured dict. Never raises.
        """
        if not HAVE_SOUNDDEVICE:
            return {"success": False, "available": False, "text": "",
                    "message": "Sound capture backend (sounddevice) unavailable."}
        if not self.microphone_available():
            return {"success": False, "available": False, "text": "",
                    "message": "No microphone detected — transcription unavailable."}
        if not self._model_available():
            loaded = self.load_model()
            if not loaded:
                return {"success": False, "text": "",
                        "message": "Faster-Whisper model could not be loaded."}
        try:
            recording = sd.rec(
                int(float(duration) * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
        except Exception as exc:
            return {"success": False, "text": "",
                    "message": f"Recording failed: {exc}"}
        try:
            segments, _info = self.model.transcribe(recording[:, 0] if recording.ndim > 1
                                                    else recording)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            return {"success": False, "text": "",
                    "message": f"Transcription failed: {exc}"}
        if filename:
            try:
                from pathlib import Path
                Path(filename).write_text(
                    json.dumps({"text": text, "duration": float(duration)},
                               indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
        return {"success": True, "text": text, "duration": float(duration),
                "message": "Transcribed successfully." if text else "No speech detected."}


voice_input = VoiceInput()


def create_stt_backend(provider=None):
    """Factory — returns the backend descriptor or None when no STT stack."""
    if not HAVE_FWHISPER:
        return None
    settings = get_settings()
    selected = provider or settings.get("STT_PROVIDER", "faster-whisper")
    return {
        "provider": selected,
        "module": "faster_whisper",
        "model_size": settings.get("STT_MODEL_SIZE", "base"),
        "microphone": bool(voice_input.microphone_available()),
    }


__all__ = ["voice_input", "create_stt_backend"]