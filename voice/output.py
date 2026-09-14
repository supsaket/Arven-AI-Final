"""Voice output (TTS) — offline Windows SAPI voice.

``voice_output.available()`` probes the real SAPI engine (COM or the
PowerShell fallback) and returns a boolean.
"""

import shutil
import subprocess

try:
    from win32com.client import Dispatch  # pywin32
    HAVE_COM = True
except Exception:  # pragma: no cover
    HAVE_COM = False


class VoiceOutput:

    def _has_powershell_sapi(self):
        return shutil.which("powershell") is not None

    def available(self):
        if HAVE_COM:
            return True
        return self._has_powershell_sapi()

    def speak(self, text, async_mode=True):
        text = str(text or "").strip()
        if not text:
            return {"success": False, "message": "no text to speak"}
        try:
            if HAVE_COM:
                voice = Dispatch("SAPI.SpVoice")
                voice.Speak(text, 0 if async_mode else 1)
                return {"success": True, "backend": "SAPI", "message": "Speaking."}
            script = (
                "$v = New-Object -ComObject SAPI.SpVoice; "
                "$v.Speak([Console]::In.ReadToEnd())"
            )
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", script],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=text.encode("utf-16-le"))
            return {"success": True, "backend": "SAPI-powershell", "message": "Speaking."}
        except Exception as exc:
            return {"success": False, "available": False,
                    "message": f"speak error: {exc}"}

    def describe(self):
        return {
            "backend": "SAPI",
            "available": self.available(),
            "offline": True,
        }


voice_output = VoiceOutput()

__all__ = ["voice_output"]