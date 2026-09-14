"""CameraProvider — Feature 46 (Camera/Capture).

Capabilities: screen_capture, camera_capture.
screen_capture uses pyautogui when available.
camera_capture is gated by permissions.camera_access and requires cv2 backend.
"""

import importlib.util
import os
import time

from core.kv import KeyValueStore
from core.output import output_manager
from core.providers.base import (
    Provider,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_REQUIRES_PERMISSION,
    ok,
    reject,
)

CAPABILITIES = ("screen_capture", "camera_capture")


class CameraProvider(Provider):
    name = "camera"
    capabilities = CAPABILITIES
    category = "capture"
    requires_network = False

    def __init__(self, settings=None, kv_path=None, output_root=None):
        super().__init__(settings)
        self._kv_path = kv_path
        self._output_root = output_root
        self._kv = None
        self._backend_forced = None
        self._init_kv()

    def _init_kv(self):
        path = self._kv_path or "data/camera_permissions.json"
        self._kv = KeyValueStore(path)

    # ------------------------------------------------------------------
    # Test hooks
    # ------------------------------------------------------------------
    def set_backend(self, found):
        self._backend_forced = bool(found)

    def _has_backend(self):
        if self._backend_forced is not None:
            return self._backend_forced
        return importlib.util.find_spec("cv2") is not None

    def _has_pyautogui(self):
        return importlib.util.find_spec("pyautogui") is not None

    def _camera_permission_granted(self):
        return self._kv.get("permissions.camera_access") == "granted"

    def grant_camera_permission(self):
        self._kv.set("permissions.camera_access", "granted")

    def revoke_camera_permission(self):
        self._kv.set("permissions.camera_access", "revoked")

    # ------------------------------------------------------------------
    # check
    # ------------------------------------------------------------------
    def check(self):
        sa = self._has_pyautogui()
        ca = self._has_backend()
        perm = self._camera_permission_granted()
        if sa or (ca and perm):
            return self.set_status(
                STATUS_AVAILABLE,
                "capture backends available",
                {"pyautogui": sa, "cv2": ca, "camera_permission": perm},
            )
        return self.set_status(
            STATUS_NOT_CONFIGURED,
            "capture backends not fully available",
            {"pyautogui": sa, "cv2": ca, "camera_permission": perm},
        )

    # ------------------------------------------------------------------
    # _cap_screen_capture — REAL local via pyautogui
    # ------------------------------------------------------------------
    def _cap_screen_capture(self, filename=None, directory=None, **_kw):
        if not self._has_pyautogui():
            return reject(
                STATUS_NOT_CONFIGURED,
                "pyautogui not installed; pip install pyautogui",
            )

        try:
            import pyautogui

            screenshot = pyautogui.screenshot()
            ts = int(time.time())
            fname = filename or f"screenshot_{ts}.png"

            out_dir = directory
            if not out_dir:
                out_dir = str(output_manager.root / "Screenshots")

            from pathlib import Path
            Path(out_dir).mkdir(parents=True, exist_ok=True)

            result = output_manager.write(
                out_dir,
                fname,
                content=b"",
                metadata={"type": "screenshot", "tool": "pyautogui"},
            )
            actual_path = result["path"]
            screenshot.save(actual_path, "PNG")
            return ok(
                "screenshot captured",
                data={"path": actual_path, "sidecar": result["sidecar"]},
            )
        except Exception as exc:
            return reject(STATUS_FAILED, f"screen capture failed: {exc}")

    # ------------------------------------------------------------------
    # _cap_camera_capture — gated by permission, requires cv2
    # ------------------------------------------------------------------
    def _cap_camera_capture(self, **_kw):
        if not self._camera_permission_granted():
            return reject(
                STATUS_REQUIRES_PERMISSION,
                "camera access not granted; grant via permissions.camera_access='granted'",
            )
        if not self._has_backend():
            return reject(
                STATUS_NOT_CONFIGURED,
                "opencv (cv2) not installed; pip install opencv-python",
            )
        try:
            import cv2

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                cap.release()
                return reject(STATUS_FAILED, "could not open webcam")
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return reject(STATUS_FAILED, "could not read frame from webcam")

            ts = int(time.time())
            fname = f"capture_{ts}.png"
            out_dir = self._output_root or "Screenshots"
            from pathlib import Path

            root_path = Path(out_dir)
            root_path.mkdir(parents=True, exist_ok=True)

            result = output_manager.write(
                str(root_path),
                fname,
                content=b"",
                metadata={"type": "camera_capture", "tool": "cv2"},
            )
            actual_path = result["path"]
            cv2.imwrite(actual_path, frame)
            return ok(
                "photo captured",
                data={"path": actual_path, "sidecar": result["sidecar"]},
            )
        except Exception as exc:
            return reject(STATUS_FAILED, f"camera capture failed: {exc}")


# ---- Registration at import time ----
from core.providers.registry import providers_registry  # noqa: E402

if not providers_registry.has("camera"):
    providers_registry.register(CameraProvider())

__all__ = ["CameraProvider"]
