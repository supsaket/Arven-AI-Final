"""Media generation providers — Features 41 (Image Generation) and 42 (Video Generation).

ImageGenProvider: local canvas placeholder when provider is "canvas", honest
NOT_CONFIGURED otherwise.
VideoGenProvider: real job lifecycle via background_executor, local storyboard
mode only.
"""

import importlib.util
import os
import time

from core.background import background_executor
from core.output import output_manager
from core.providers.base import (
    Provider,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    ok,
    reject,
)


# ======================================================================
# ImageGenProvider  (Feature 41)
# ======================================================================
class ImageGenProvider(Provider):
    name = "image_gen"
    capabilities = ("image_generate",)
    category = "media_generation"
    requires_network = False

    def __init__(self, settings=None, output_root=None):
        super().__init__(settings)
        self._output_root = output_root

    def _provider_name(self):
        return self.settings.get("IMAGE_GENERATION_PROVIDER", "")

    # ------------------------------------------------------------------
    def check(self):
        prov = self._provider_name()
        if prov == "canvas":
            pil = importlib.util.find_spec("PIL") is not None
            if pil:
                return self.set_status(
                    STATUS_AVAILABLE,
                    "local canvas placeholder generator available",
                    {"provider": "canvas", "pil": True},
                )
            return self.set_status(
                STATUS_NOT_CONFIGURED,
                "PIL not installed; pip install Pillow for local canvas generator",
                {"provider": "canvas", "pil": False},
            )
        if prov:
            return self.set_status(
                STATUS_NOT_CONFIGURED,
                f"provider '{prov}' not implemented; only 'canvas' is supported locally",
                {"provider": prov},
            )
        return self.set_status(
            STATUS_NOT_CONFIGURED,
            "IMAGE_GENERATION_PROVIDER is empty",
            {"provider": ""},
        )

    # ------------------------------------------------------------------
    def _cap_image_generate(self, prompt=None, width=512, height=512, **_kw):
        prov = self._provider_name()
        if prov != "canvas":
            return reject(
                STATUS_NOT_CONFIGURED,
                f"IMAGE_GENERATION_PROVIDER={prov!r} has no real backend; "
                'set to "canvas" for local placeholder generation',
            )
        if not importlib.util.find_spec("PIL"):
            return reject(
                STATUS_NOT_CONFIGURED,
                "Pillow not installed; pip install Pillow",
            )

        try:
            from PIL import Image, ImageDraw, ImageFont

            w = int(width) if width else 512
            h = int(height) if height else 512
            img = Image.new("RGB", (w, h), color=(240, 240, 240))
            draw = ImageDraw.Draw(img)

            label = f"PLACEHOLDER\n{prompt or '(no prompt)'}"

            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except Exception:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((w - tw) // 2, (h - th) // 2),
                label,
                fill=(100, 100, 100),
                font=font,
            )

            out_dir = self._output_root or "Output/ImageGeneration"
            from pathlib import Path

            root_path = Path(self._output_root) if self._output_root else output_manager.root / "Output" / "ImageGeneration"
            root_path.mkdir(parents=True, exist_ok=True)

            filename = f"canvas_{int(time.time())}.png"
            result = output_manager.write(
                str(root_path),
                filename,
                content=b"",
                metadata={},
            )
            actual_path = result["path"]
            img.save(actual_path, "PNG")

            meta = {
                "prompt": prompt,
                "placeholder": True,
                "generated": True,
                "provider": "canvas",
                "width": w,
                "height": h,
                "artefact": result,
            }
            return ok("placeholder image generated", data=meta)
        except Exception as exc:
            return reject(STATUS_FAILED, f"image generation failed: {exc}")


# ======================================================================
# VideoGenProvider  (Feature 42)
# ======================================================================
def _video_render_job(prompt, storyboard_dir, width, height, fps):
    """Background job: writes a storyboard text manifest (not a real video)."""
    from pathlib import Path

    path = Path(storyboard_dir) / "storyboard.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(1, 4):
        frames.append(f"Frame {i}: Scene description for '{prompt}' (placeholder)")
    content = "\n".join(frames)
    path.write_text(content, encoding="utf-8")
    return {
        "storyboard_path": str(path),
        "prompt": prompt,
        "frames": frames,
        "generated": True,
        "video": False,
    }


class VideoGenProvider(Provider):
    name = "video_gen"
    capabilities = ("video_generate", "video_status", "video_cancel")
    category = "media_generation"
    requires_network = False
    confirm_capabilities = ("video_generate",)

    def __init__(self, settings=None, output_root=None):
        super().__init__(settings)
        self._output_root = output_root

    def _provider_name(self):
        return self.settings.get("VIDEO_GENERATION_PROVIDER", "")

    # ------------------------------------------------------------------
    def check(self):
        prov = self._provider_name()
        if prov == "storyboard":
            return self.set_status(
                STATUS_AVAILABLE,
                "storyboard mode (text-based, not real video)",
                {"provider": "storyboard"},
            )
        if prov:
            return self.set_status(
                STATUS_NOT_CONFIGURED,
                f"provider '{prov}' not implemented; only 'storyboard' is supported",
                {"provider": prov},
            )
        return self.set_status(
            STATUS_NOT_CONFIGURED,
            "VIDEO_GENERATION_PROVIDER is empty",
            {"provider": ""},
        )

    # ------------------------------------------------------------------
    def _cap_video_generate(self, prompt=None, **_kw):
        prov = self._provider_name()
        if prov != "storyboard":
            return reject(
                STATUS_NOT_CONFIGURED,
                f"VIDEO_GENERATION_PROVIDER={prov!r} has no real backend; "
                'set to "storyboard" for text-based storyboard mode',
            )

        out_dir = self._output_root or "Output/VideoGeneration"
        from pathlib import Path
        root_path = Path(out_dir)

        task = background_executor.submit(
            "video_storyboard",
            _video_render_job,
            prompt or "(no prompt)",
            str(root_path),
            640,
            480,
            24,
        )
        return ok(
            "storyboard job submitted",
            data={
                "job_id": task.task_id,
                "provider": "storyboard",
                "prompt": prompt,
                "generated": True,
                "video": False,
            },
        )

    # ------------------------------------------------------------------
    def _cap_video_status(self, job_id=None, **_kw):
        if not job_id:
            return reject(STATUS_NOT_CONFIGURED, "job_id is required")
        task = background_executor.get(job_id)
        if task is None:
            return reject(STATUS_NOT_CONFIGURED, f"no such job: {job_id}")
        result = {
            "job_id": task.task_id,
            "status": task.status,
            "error": repr(task.error) if task.error else None,
            "result": task.result,
        }
        return ok(f"job status: {task.status}", data=result)

    # ------------------------------------------------------------------
    def _cap_video_cancel(self, job_id=None, **_kw):
        if not job_id:
            return reject(STATUS_NOT_CONFIGURED, "job_id is required")
        task = background_executor.get(job_id)
        if task is None:
            return reject(STATUS_NOT_CONFIGURED, f"no such job: {job_id}")
        task.cancel()
        return ok("job cancelled", data={"job_id": job_id, "status": task.status})


# ---- Registration at import time ----
from core.providers.registry import providers_registry  # noqa: E402

if not providers_registry.has("image_gen"):
    providers_registry.register(ImageGenProvider())
if not providers_registry.has("video_gen"):
    providers_registry.register(VideoGenProvider())

__all__ = ["ImageGenProvider", "VideoGenProvider"]
