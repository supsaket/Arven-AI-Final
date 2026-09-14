"""Application tools — open apps, list apps, capture screen.

``open_app`` maps friendly names to Windows executables; ``apps_list``
returns the known registry of launchable apps; ``capture_screen`` grabs the
screen with Pillow (used by vision + computer-use).
"""

import subprocess
from pathlib import Path

try:
    import pyautogui
    HAVE_PYAUTOGUI = True
except Exception:  # pragma: no cover
    pyautogui = None
    HAVE_PYAUTOGUI = False


def _launch(name):
    """Return a subprocess.Popen launchable or None."""
    name = str(name).strip().lower()
    apps = {
        "notepad": ["notepad.exe"],
        "calc": ["calc.exe"],
        "calculator": ["calc.exe"],
        "paint": ["mspaint.exe"],
        "mspaint": ["mspaint.exe"],
        "explorer": ["explorer.exe"],
        "file explorer": ["explorer.exe"],
        "cmd": ["cmd.exe"],
        "command prompt": ["cmd.exe"],
        "powershell": ["powershell.exe"],
        "task manager": ["taskmgr.exe"],
        "taskmgr": ["taskmgr.exe"],
        "edge": ["msedge.exe"],
        "chrome": ["chrome.exe"],
    }
    if name in apps:
        return apps[name]
    for exec_name in ("msedge.exe", "chrome.exe", "notepad.exe"):
        try_path = str(Path("C:\\Windows\\System32") / exec_name)
        if Path(try_path).exists():
            return [try_path] if name in (exec_name.replace(".exe", ""),) else None
    return None


def open_app(app, **kwargs):
    cmd = _launch(app)
    if not cmd:
        return {"success": False, "action": "open_app",
                "message": f"Unknown app '{app}'. Known apps: {KNOWN_APPS}."}
    try:
        subprocess.Popen(cmd)
        return {"success": True, "action": "open_app", "app": str(app),
                "message": f"Launched {app}."}
    except Exception as exc:
        return {"success": False, "action": "open_app", "message": f"open_app error: {exc}"}


KNOWN_APPS = [
    "notepad", "calc", "calculator", "paint", "explorer", "cmd",
    "powershell", "task manager", "edge", "chrome",
]


def apps_list(**kwargs):
    return {"success": True, "action": "apps_list", "apps": KNOWN_APPS,
            "message": f"{len(KNOWN_APPS)} apps available."}


def _screen_dir():
    base = Path(__file__).resolve().parent.parent
    shots = base / "Screenshots"
    try:
        shots.mkdir(parents=True, exist_ok=True)
        return shots
    except OSError:
        return Path().cwd()


def capture_screen(filename="screenshot.png", **kwargs):
    """Capture the primary screen and save a PNG (Pillow)."""
    if not HAVE_PYAUTOGUI:
        return {"success": False, "action": "capture_screen", "available": False,
                "message": "pyautogui unavailable — screen capture backend missing."}
    if Path(filename).suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp"):
        filename += ".png"
    try:
        from datetime import datetime
        safe_name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png" \
            if filename == "screenshot.png" else filename
        target = Path(filename) if ("/" in filename or "\\" in filename) \
            else Path(_screen_dir()) / safe_name
        image = pyautogui.screenshot()
        image.save(str(target))
        return {"success": True, "action": "capture_screen", "path": str(target),
                "width": image.width, "height": image.height,
                "message": f"Captured screen to {target.name}."}
    except Exception as exc:
        return {"success": False, "action": "capture_screen", "message": f"capture_screen error: {exc}"}


TOOLS = [
    {"name": "open_app", "function": open_app, "category": "Apps", "backend": "windows",
     "risk": "low", "parameters": [{"name": "app", "required": True, "hint": "str"}]},
    {"name": "apps_list", "function": apps_list, "category": "Apps", "backend": "windows",
     "risk": "safe"},
    {"name": "capture_screen", "function": capture_screen, "category": "Vision",
     "backend": "pyautogui", "risk": "low",
     "parameters": [{"name": "filename", "required": False, "hint": "str"}]},
]