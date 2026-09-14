"""VisionProvider — Feature 40 (Vision/Image Understanding).

Capabilities: vision_analyze, image_metadata, screen_coordinates.
image_metadata and screen_coordinates are REAL local operations.
vision_analyze requires an ML vision backend.
"""

import importlib.util
import os

from core.providers.base import (
    Provider,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    ok,
    reject,
)

CAPABILITIES = ("vision_analyze", "image_metadata", "screen_coordinates")


class VisionProvider(Provider):
    name = "vision"
    capabilities = CAPABILITIES
    category = "vision"
    requires_network = False

    def __init__(self, settings=None, backend_found=None):
        super().__init__(settings)
        self._backend_forced = backend_found

    # ------------------------------------------------------------------
    # Test hook
    # ------------------------------------------------------------------
    def set_backend(self, found):
        self._backend_forced = bool(found)

    def _has_backend(self):
        if self._backend_forced is not None:
            return self._backend_forced
        provider_name = self.settings.get("VISION_PROVIDER", "")
        if not provider_name:
            return False
        if provider_name in ("ollama",):
            return importlib.util.find_spec("ollama") is not None
        if provider_name in ("openai",):
            return importlib.util.find_spec("openai") is not None
        return False

    def _has_pil(self):
        return importlib.util.find_spec("PIL") is not None

    # ------------------------------------------------------------------
    # check
    # ------------------------------------------------------------------
    def check(self):
        pil = self._has_pil()
        ml = self._has_backend()
        if ml:
            return self.set_status(
                STATUS_AVAILABLE,
                "ML vision backend available",
                {"pil": pil, "ml_backend": True},
            )
        reason = (
            "No ML vision provider configured (VISION_PROVIDER is empty or backend not installed). "
            "Set VISION_PROVIDER and install the corresponding package."
        )
        return self.set_status(
            STATUS_NOT_CONFIGURED,
            reason,
            {"pil": pil, "ml_backend": False},
        )

    # ------------------------------------------------------------------
    # _cap_image_metadata  — REAL local, only needs PIL
    # ------------------------------------------------------------------
    def _cap_image_metadata(self, image_path=None, **_kw):
        if not image_path:
            return reject(STATUS_NOT_CONFIGURED, "image_path is required")
        if not os.path.isfile(image_path):
            return reject(STATUS_FAILED, f"file not found: {image_path}")
        if not self._has_pil():
            return reject(STATUS_NOT_CONFIGURED, "Pillow not installed; pip install Pillow")

        try:
            from PIL import Image

            img = Image.open(image_path)
            data = {
                "path": image_path,
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "size_bytes": os.path.getsize(image_path),
            }
            img.close()
            return ok("image metadata read", data=data)
        except Exception as exc:
            return reject(STATUS_FAILED, f"failed to read image: {exc}")

    # ------------------------------------------------------------------
    # _cap_vision_analyze  — requires ML backend
    # ------------------------------------------------------------------
    def _cap_vision_analyze(self, image_path=None, **_kw):
        if not os.path.isfile(image_path or ""):
            return reject(STATUS_NOT_CONFIGURED, "image_path is required and must exist")
        if not self._has_backend():
            provider_name = self.settings.get("VISION_PROVIDER", "")
            detail = (
                f"VISION_PROVIDER={provider_name!r}; install the corresponding package "
                "or set VISION_PROVIDER in config"
            )
            return reject(
                STATUS_NOT_CONFIGURED,
                "No ML vision backend available",
                {"detail": detail, "required": "configured VISION_PROVIDER + installed package"},
            )
        return reject(
            STATUS_NOT_CONFIGURED,
            "vision_analyze dispatch to live ML model not yet wired",
        )

    # ------------------------------------------------------------------
    # _cap_screen_coordinates  — REAL local math via PIL
    # ------------------------------------------------------------------
    def _cap_screen_coordinates(
        self,
        image_path=None,
        x=None,
        y=None,
        relative_to_screen=False,
        perform_action=False,
        **_kw,
    ):
        if not image_path:
            return reject(STATUS_NOT_CONFIGURED, "image_path is required")
        if not os.path.isfile(image_path):
            return reject(STATUS_FAILED, f"file not found: {image_path}")
        if not self._has_pil():
            return reject(STATUS_NOT_CONFIGURED, "Pillow not installed; pip install Pillow")

        try:
            from PIL import Image

            img = Image.open(image_path)
            w, h = img.size
            img.close()

            cx = x if x is not None else w // 2
            cy = y if y is not None else h // 2

            norm_x = cx / w if w else 0.0
            norm_y = cy / h if h else 0.0

            screen_abs_x = cx
            screen_abs_y = cy

            if relative_to_screen:
                has_pyautogui = importlib.util.find_spec("pyautogui") is not None
                if has_pyautogui:
                    try:
                        import pyautogui

                        sw, sh = pyautogui.size()
                        screen_abs_x = int(norm_x * sw)
                        screen_abs_y = int(norm_y * sh)
                    except Exception:
                        pass

            result = {
                "image_path": image_path,
                "image_width": w,
                "image_height": h,
                "normalized_x": round(norm_x, 6),
                "normalized_y": round(norm_y, 6),
                "absolute_x": screen_abs_x,
                "absolute_y": screen_abs_y,
            }

            if perform_action:
                has_pyautogui = importlib.util.find_spec("pyautogui") is not None
                if has_pyautogui:
                    return ok(
                        "mouse move requires confirmation",
                        data=result,
                        requires_confirmation=True,
                        action="mouse_move",
                        target={"x": screen_abs_x, "y": screen_abs_y},
                    )
                return reject(
                    STATUS_NOT_CONFIGURED,
                    "pyautogui not installed; cannot perform mouse action",
                    data=result,
                )

            return ok("coordinates computed", data=result)
        except Exception as exc:
            return reject(STATUS_FAILED, f"screen_coordinates failed: {exc}")


# ---- Registration at import time ----
from core.providers.registry import providers_registry  # noqa: E402

if not providers_registry.has("vision"):
    providers_registry.register(VisionProvider())

__all__ = ["VisionProvider"]
