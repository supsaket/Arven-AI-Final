"""Android Integration / ADB (feature 43).

Capabilities:
* ``android_status``        - report ADB presence + version (real ``adb version``)
* ``android_list_devices``  - run real ``adb devices`` when the binary exists
* ``android_shell``         - run a shell command on a connected device **only**
  after an approved CONFIRMATION gate (confirmed + approved request_id).

Honesty rules:
* no adb on PATH            -> NOT_CONFIGURED (requirement listed in the reason)
* device shell output       -> captured from a REAL ``adb shell`` call, never
  fabricated
* ``set_backend(found)``    -> test hook; ``found=False`` forces NOT_CONFIGURED
  for everything (a fake/unavailable backend is never reported as working).

``android_shell`` is a confirm-gated capability, but the base gate classifies
the action as medium risk (it does not auto-refuse) — so this provider ships a
strict ``execute()`` that requires an explicit, still-pending confirmation
token for every capability listed in ``confirm_capabilities``.
"""

import shutil
import subprocess

from core.confirmation import CONFIRMATION
from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
)


class AndroidProvider(Provider):
    name = "android"
    capabilities = (
        "android_status",
        "android_shell",
        "android_list_devices",
    )
    category = "devices"
    requires_network = False
    confirm_capabilities = ("android_shell",)

    def __init__(self, settings=None):
        super().__init__(settings)
        self._backend_found = None
        self._backend_probed = False
        self.set_status(STATUS_NOT_CONFIGURED, "android backend not probed")

    def set_backend(self, found):
        """Test hook: declare whether a real adb backend exists."""
        self._backend_found = bool(found)
        self._backend_probed = True

    def _have_adb(self):
        if self._backend_probed:
            return bool(self._backend_found)
        return shutil.which("adb") is not None

    def _adb_version(self):
        try:
            result = subprocess.run(
                ["adb", "version"], capture_output=True, text=True, timeout=5
            )
            return (result.stdout or result.stderr).strip()
        except Exception:
            return ""

    def check(self):
        if not self._have_adb():
            return self.set_status(
                STATUS_NOT_CONFIGURED,
                "android/ADB not installed — install Android platform-tools and "
                "add adb to PATH",
                {"requirement": "adb executable on PATH"},
            )
        return self.set_status(
            STATUS_AVAILABLE,
            "adb present and usable",
            {"version": self._adb_version()},
        )

    # ------------------------------------------------------------------
    def execute(self, capability, **kwargs):
        """Strict gate for ``android_shell`` (medium-classified risk).

        Mirrors the base dispatcher but refuses confirm capabilities unless an
        explicit ``confirmed`` PLUS an approved (still pending) ``request_id``
        is supplied. Never raises.
        """
        try:
            target = self.describe_capability(capability)
            method = getattr(self, f"_cap_{target.replace('-', '_')}", None)
            if self.needing_network():
                return self._honest(STATUS_OFFLINE,
                                    f"{self.name} requires network access")
            if method is None:
                return self._honest(
                    STATUS_NOT_CONFIGURED,
                    f"{self.name} does not implement capability '{capability}'")
            if target in self.confirm_capabilities:
                confirmed = bool(kwargs.get("confirmed", False))
                trusted = bool(kwargs.get("trusted", False))
                request_id = kwargs.get("request_id")
                allowed, _reason = CONFIRMATION.gate(
                    f"{self.name}.{target}",
                    confirmed=confirmed,
                    trusted=trusted,
                    request_id=request_id,
                )
                approved = bool(
                    allowed and confirmed and request_id
                    and CONFIRMATION.is_pending_ok(request_id))
                if not approved:
                    payload = self._honest(
                        STATUS_REQUIRES_AUTH, f"{target} requires confirmation")
                    payload["requires_confirmation"] = True
                    return payload
                kwargs["_cleared"] = True
                kwargs.pop("confirmed", None)
                kwargs.pop("trusted", None)
                kwargs.pop("request_id", None)
            return method(**kwargs)
        except Exception as exc:
            return self._honest(STATUS_FAILED, f"{self.name} error: {exc}")

    # ------------------------------------------------------------------
    def _cap_android_status(self, **_kw):
        if not self._have_adb():
            return reject(
                STATUS_NOT_CONFIGURED,
                "android/ADB not installed — install Android platform-tools and "
                "add adb to PATH",
                {"requirement": "adb executable on PATH"},
            )
        return ok(
            "adb present",
            {"available": True, "adb": shutil.which("adb"),
             "version": self._adb_version()},
        )

    def _cap_android_list_devices(self, **_kw):
        if not self._have_adb():
            return reject(
                STATUS_NOT_CONFIGURED,
                "android/ADB not installed — cannot enumerate devices",
                {"requirement": "adb executable on PATH"},
            )
        try:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=5
            )
            lines = (result.stdout or "").splitlines()
            devices = []
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    devices.append({"serial": parts[0], "state": parts[1]})
            return ok("adb devices enumerated", {"devices": devices})
        except Exception as exc:
            return reject(STATUS_NOT_CONFIGURED, f"adb devices failed: {exc}")

    def _cap_android_shell(self, command=None, **_kw):
        if not self._have_adb():
            return reject(
                STATUS_NOT_CONFIGURED,
                "android/ADB not installed — cannot run device shell",
                {"requirement": "adb executable on PATH"},
            )
        if not command or not str(command).strip():
            return reject(STATUS_REQUIRES_AUTH,
                          "android_shell requires a non-empty command")
        try:
            result = subprocess.run(
                ["adb", "shell", str(command)],
                capture_output=True, text=True, timeout=15,
            )
            output = (result.stdout or result.stderr).strip()
            return ok(
                "device shell executed (real output captured)",
                {"command": str(command), "exit_code": result.returncode,
                 "output": output},
            )
        except Exception as exc:
            return reject(STATUS_FAILED, f"android_shell failed: {exc}")


def register_android():
    from core.providers.registry import providers_registry
    if not providers_registry.has("android"):
        providers_registry.register(AndroidProvider())
    return providers_registry.get("android")


__all__ = ["AndroidProvider", "register_android"]