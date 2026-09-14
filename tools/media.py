"""Media control — volume/screen brightness via pycaw + comtypes.

Real Windows Core Audio volume control, falling back to honest
unavailable status when the backend is missing.
"""

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    HAVE_PYCAW = True
except Exception:  # pragma: no cover
    CLSCTX_ALL = None
    HAVE_PYCAW = False

try:
    import winsound
    HAVE_WINSOUND = True
except Exception:  # pragma: no cover
    HAVE_WINSOUND = False


def _endpoint():
    """Fetch the default audio endpoint volume interface (pycaw versions differ)."""
    if not HAVE_PYCAW:
        return None
    try:
        device = AudioUtilities.GetSpeakers()
        activate = getattr(device, "Activate", None)
        if activate is not None:
            return activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            ).QueryInterface(IAudioEndpointVolume)
        endpoint = getattr(device, "EndpointVolume", None)
        if endpoint is not None and hasattr(endpoint, "GetMasterVolumeLevelScalar"):
            return endpoint
        return None
    except Exception:
        return None


def media_command(command, **kwargs):
    """Control media: volume_up / volume_down / mute / unmute / set_volume."""
    command = str(command).strip().lower()
    endpoint = _endpoint()
    if endpoint is None:
        return {"success": False, "action": "media_command", "backend": "pycaw",
                "available": False,
                "message": "Media backend (pycaw) unavailable."}
    try:
        current = endpoint.GetMasterVolumeLevelScalar()
        if command in ("mute", "unmute"):
            endpoint.SetMute(1 if command == "mute" else 0, None)
            return {"success": True, "action": "media_command", "command": command,
                    "muted": command == "mute", "message": f"Audio {command}d."}
        if command == "volume_up":
            endpoint.SetMasterVolumeLevelScalar(min(1.0, current + 0.1), None)
        elif command == "volume_down":
            endpoint.SetMasterVolumeLevelScalar(max(0.0, current - 0.1), None)
        elif command.startswith("set_volume"):
            try:
                value = float(command.split("_")[-1])
            except (ValueError, IndexError):
                return {"success": False, "action": "media_command",
                        "message": "set_volume needs a value, e.g. set_volume_0.4"}
            endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, value)), None)
        else:
            return {"success": False, "action": "media_command",
                    "message": f"Unknown media command '{command}'."}
        new_level = round(endpoint.GetMasterVolumeLevelScalar(), 2)
        return {"success": True, "action": "media_command", "command": command,
                "volume": new_level, "message": f"Volume set to {int(new_level * 100)}%."}
    except Exception as exc:
        return {"success": False, "action": "media_command", "message": f"media_command error: {exc}"}


def _phrase_to_command(text):
    """Map a natural media phrase to a media_command token."""
    lowered = str(text or "").lower()
    set_match = None
    for marker in ("volume to ", "volume at "):
        if marker in lowered:
            tail = lowered.split(marker, 1)[1].split()[0]
            try:
                fraction = float(tail) / 100.0
            except ValueError:
                fraction = None
            if fraction is not None:
                set_match = f"set_volume_{max(0.0, min(1.0, fraction))}"
            break
    phrases = [
        (("turn up", "volume up", "louder", "increase volume", "raise volume"),
         "volume_up"),
        (("turn down", "volume down", "quieter", "decrease volume", "lower volume"),
         "volume_down"),
        (("mute",), "mute"),
        (("unmute", "turn sound on"), "unmute"),
        (("max volume", "volume max", "full volume"), "volume"),
    ]
    for needles, command in phrases:
        if any(needle in lowered for needle in needles):
            return command
    return set_match


def media_command_phrase(phrase, **kwargs):
    """Media control from a natural-language phrase (real status when available)."""
    command = _phrase_to_command(phrase)
    if command is None:
        return {"success": False, "action": "media_command_phrase",
                "unknown": True,
                "message": f"I couldn't parse that media request: {phrase}"}
    return media_command(command)


def media_status(**kwargs):
    endpoint = _endpoint()
    if endpoint is None:
        return {"success": True, "action": "media_status", "available": False,
                "backend": "pycaw", "message": "Media backend unavailable."}
    try:
        volume = round(endpoint.GetMasterVolumeLevelScalar(), 2)
        muted = bool(endpoint.GetMute())
        return {"success": True, "action": "media_status", "available": True,
                "volume": volume, "muted": muted,
                "message": f"Volume {int(volume * 100)}% and {'muted' if muted else 'unmuted'}."}
    except Exception as exc:
        return {"success": False, "action": "media_status", "message": f"media_status error: {exc}"}


TOOLS = [
    {"name": "media_command", "function": media_command, "category": "Media",
     "backend": "pycaw", "risk": "medium",
     "parameters": [{"name": "command", "required": True, "hint": "str"}]},
    {"name": "media_command_phrase", "function": media_command_phrase,
     "category": "Media", "backend": "pycaw", "risk": "medium",
     "parameters": [{"name": "phrase", "required": True, "hint": "str"}]},
    {"name": "media_status", "function": media_status, "category": "Media",
     "backend": "pycaw", "risk": "safe"},
]