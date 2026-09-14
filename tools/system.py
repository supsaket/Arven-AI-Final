"""System tools — read-only system introspection + gated shell.

Registered into the ToolRegistry by ``tools.builder``.

Safety: ``run_shell`` is HIGH risk (confirmation required) and never used to
bypass the safety engine. All *read-only* tools are low risk.
"""

import datetime
import os
import platform
import subprocess

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None
    HAVE_PSUTIL = False


def system_info(**kwargs):
    uname = platform.uname()
    info = {
        "os": platform.system(),
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "processor": platform.processor(),
        "hostname": uname.node,
        "python": platform.python_version(),
    }
    if HAVE_PSUTIL:
        vm = psutil.virtual_memory()
        info["memory_total_mb"] = round(vm.total / (1024 ** 2))
        info["memory_used_mb"] = round(vm.used / (1024 ** 2))
        info["memory_percent"] = vm.percent
        info["cpu_percent"] = psutil.cpu_percent(interval=0.2)
        info["cpu_count"] = psutil.cpu_count()
        info["disk_used_mb"] = None
        try:
            du = psutil.disk_usage(os.getcwd())
            info["disk_percent"] = du.percent
        except Exception:
            info["disk_percent"] = None
    return {
        "success": True,
        "system": info,
        "message": "System info collected.",
    }


def date_time(**kwargs):
    now = datetime.datetime.now()
    return {
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": datetime.datetime.now().astimezone().tzname(),
        "message": f"The current date and time is {now.strftime('%Y-%m-%d %H:%M:%S')}.",
    }


def running_processes(**kwargs):
    if not HAVE_PSUTIL:
        return {"success": False, "message": "psutil unavailable", "processes": []}
    processes = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            processes.append({"pid": proc.info["pid"], "name": proc.info["name"]})
        except Exception:
            continue
    processes.sort(key=lambda p: str(p["name"]).lower())
    return {
        "success": True,
        "count": len(processes),
        "processes": processes[:200],
        "message": f"{len(processes)} running processes listed.",
    }


def wifi_status(**kwargs):
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=10,
        )
        connected = "State                   : connected" in result.stdout
        return {
            "success": True,
            "connected": connected,
            "message": "Wi-Fi connected." if connected else "Wi-Fi not connected.",
        }
    except Exception as exc:
        return {"success": False, "message": f"wifi_status error: {exc}", "connected": False}


def run_shell(command, **kwargs):
    """Execute a shell command. HIGH RISK — confirmation required at registry."""
    if not command or not str(command).strip():
        return {"success": False, "message": "empty command"}
    try:
        result = subprocess.run(
            str(command), shell=True, capture_output=True, text=True, timeout=30,
        )
        return {
            "success": True,
            "exit_code": result.returncode,
            "stdout": (result.stdout or "")[-4000:],
            "stderr": (result.stderr or "")[-2000:],
            "message": "Command executed.",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "command timed out after 30s"}
    except Exception as exc:
        return {"success": False, "message": f"shell error: {exc}"}


TOOLS = [
    {"name": "system_info", "function": system_info, "category": "System", "backend": "local",
     "risk": "safe"},
    {"name": "date_time", "function": date_time, "category": "System", "backend": "local",
     "risk": "safe"},
    {"name": "running_processes", "function": running_processes, "category": "System",
     "backend": "psutil", "risk": "safe"},
    {"name": "wifi_status", "function": wifi_status, "category": "System", "backend": "netsh",
     "risk": "low"},
    {"name": "run_shell", "function": run_shell, "category": "System", "backend": "shell",
     "risk": "high", "parameters": [{"name": "command", "required": True, "hint": "str"}]},
]