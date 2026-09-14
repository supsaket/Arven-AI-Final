"""Android + IoT device tools.

Other devices are external dependencies: ADB is not present and no IoT hub
endpoint is configured, so status tools are real, read-only and honest.
"""

import shutil


def _adb():
    return shutil.which("adb")


def android_status(**kwargs):
    adb = _adb()
    if not adb:
        return {"success": True, "action": "android_status", "available": False,
                "backend": "adb", "devices": [],
                "message": "Android backend (adb) not found on this machine."}
    return {"success": True, "action": "android_status", "available": False,
            "backend": "adb", "devices": [],
            "message": "ADB present but no devices connected."}


def android_command(command, target=None, **kwargs):
    command = str(command).strip()
    if command in ("", "screenshot", "shell", "open_app", "tap", "swipe"):
        return {"success": False, "action": "android_command", "available": False,
                "backend": "adb",
                "message": f"Android command '{command}' cannot run without a connected device."}
    return {"success": False, "action": "android_command", "available": False,
            "backend": "adb",
            "message": "Invalid or unsupported Android command."}


def iot_status(**kwargs):
    return {"success": True, "action": "iot_status", "available": False,
            "backend": "none configured",
            "message": "IoT integration is not configured (no hub endpoint)."}


TOOLS = [
    {"name": "android_status", "function": android_status, "category": "Device",
     "backend": "adb", "risk": "safe"},
    {"name": "android_command", "function": android_command, "category": "Device",
     "backend": "adb", "risk": "high",
     "parameters": [{"name": "command", "required": True, "hint": "str"},
                    {"name": "target", "required": False, "hint": "str"}]},
    {"name": "iot_status", "function": iot_status, "category": "Device",
     "backend": "iot", "risk": "safe"},
]