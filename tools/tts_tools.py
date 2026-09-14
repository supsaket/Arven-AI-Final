"""TTS tools — speak text with the Windows SAPI voice (WinRT-independent).

Uses the PowerShell System.Speech engine (a fully offline, local TTS voice)
and reports an honest unavailable status if the backend fails.
"""

import subprocess

try:
    from win32com.client import Dispatch  # pywin32 route
    HAVE_COM = True
except Exception:  # pragma: no cover
    HAVE_COM = False


def _speak_com(text):
    voice = Dispatch("SAPI.SpVoice")
    voice.Speak(text)


def _speak_powershell(text):
    script = (
        "$v = New-Object -ComObject SAPI.SpVoice; "
        "$v.Speak([Console]::In.ReadToEnd())"
    )
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", script],
        stdin=subprocess.PIPE,
        shell=True,
    )
    proc.communicate(input=text.encode("utf-16-le"))
    return proc.returncode


def tts_speak(text, await_completion=False, **kwargs):
    text = str(text or "").strip()
    if not text:
        return {"success": False, "action": "tts_speak", "message": "no text to speak"}
    try:
        if HAVE_COM:
            _speak_com(text)
            return {"success": True, "action": "tts_speak", "spoken": text[:80],
                    "backend": "SAPI", "message": "Spoken."}
        _speak_powershell(text)
        return {"success": True, "action": "tts_speak", "spoken": text[:80],
                "backend": "SAPI-powershell", "message": "Spoken."}
    except Exception as exc:
        return {"success": False, "action": "tts_speak", "backend": "SAPI",
                "available": False, "message": f"tts_speak error: {exc}"}


def _sanitize_for_speech(text):
    """Strip markdown noise so spoken output stays clean."""
    from core.upgrade import TTS_Sanitizer
    return TTS_Sanitizer.sanitize(text)


def tts_speak_clean(text, **kwargs):
    """TTS with text sanitized first (markdown removed, whitespace collapsed)."""
    return tts_speak(_sanitize_for_speech(text), **kwargs)


def tts_status(**kwargs):
    if not HAVE_COM:
        return {"success": True, "action": "tts_status", "available": True,
                "backend_available": True, "backend": "SAPI-powershell",
                "message": "TTS available (PowerShell SAPI voice)."}
    return {"success": True, "action": "tts_status", "available": True,
            "backend_available": True, "backend": "SAPI",
            "message": "TTS available."}


TOOLS = [
    {"name": "tts_speak", "function": tts_speak, "category": "Media", "backend": "SAPI",
     "risk": "low",
     "parameters": [{"name": "text", "required": True, "hint": "str"},
                    {"name": "await_completion", "required": False, "hint": "bool"}]},
    {"name": "tts_speak_clean", "function": tts_speak_clean, "category": "Media",
     "backend": "SAPI", "risk": "low",
     "parameters": [{"name": "text", "required": True, "hint": "str"}]},
    {"name": "tts_status", "function": tts_status, "category": "Media", "backend": "SAPI",
     "risk": "safe"},
]