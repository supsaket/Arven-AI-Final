"""Focused tests for ARVEN Day 2 providers (features 39/40/41/42/46).

Covers: honest NOT_CONFIGURED paths, bookmark CRUD + search, real image
metadata reads, screen-coordinate math, camera permission gating, real
video job submit/status/cancel lifecycle, and canvas placeholder PNG output.
"""

import os
import time

from core.background import background_executor
from core.providers.base import (
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_REQUIRES_PERMISSION,
)
from core.providers.browser_provider import BrowserProvider
from core.providers.camera_provider import CameraProvider
from core.providers.media_gen import ImageGenProvider, VideoGenProvider
from core.providers.vision_provider import VisionProvider


class FakeSettings:
    """Minimal settings shim with .get(name, default)."""

    def __init__(self, **kw):
        self._kw = dict(kw)

    def get(self, name, default=None):
        return self._kw.get(name, default)


def make_png(path, width=100, height=50):
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(10, 20, 30))
    img.save(str(path), "PNG")
    return str(path)


class TestBrowserProvider:

    def test_status_honest_none_configured(self, tmp_path):
        prov = BrowserProvider(kv_path=str(tmp_path / "bookmarks.json"))
        prov.set_backend(False)
        result = prov.execute("browser_status")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert "playwright" in result["message"].lower()

        check = prov.check()
        assert check in ("AVAILABLE", "NOT_CONFIGURED", "OFFLINE", "UNAVAILABLE",
                         "REQUIRES_AUTH", "REQUIRES_PERMISSION", "FAILED")
        assert prov.status_code == STATUS_NOT_CONFIGURED

    def test_status_available_when_backend_forced(self, tmp_path):
        prov = BrowserProvider(kv_path=str(tmp_path / "bookmarks.json"))
        prov.set_backend(True)
        result = prov.execute("browser_status")
        assert result["success"] is True
        assert result["status"] == STATUS_AVAILABLE
        assert result["data"]["available"] is True

    def test_search_honest_no_backend(self, tmp_path):
        prov = BrowserProvider(kv_path=str(tmp_path / "bookmarks.json"))
        prov.set_backend(False)
        result = prov.execute("browser_search", query="arven")
        assert result["success"] is False
        assert result["status"] in (STATUS_NOT_CONFIGURED, "OFFLINE")
        assert "playwright" in result["message"].lower()

    def test_bookmark_crud_and_search(self, tmp_path):
        prov = BrowserProvider(kv_path=str(tmp_path / "bookmarks.json"))
        added = prov.execute("bookmarks", action="add",
                             url="https://example.com/docs",
                             title="Docs", tags=["python", "docs"])
        assert added["success"] is True
        assert added["data"]["bookmark"]["url"] == "https://example.com/docs"

        listed = prov.execute("bookmarks")
        assert listed["success"] is True
        assert len(listed["data"]["bookmarks"]) == 1

        searched = prov.execute("bookmarks", action="search", keyword="python")
        assert searched["success"] is True
        assert len(searched["data"]["bookmarks"]) == 1
        assert searched["data"]["bookmarks"][0]["url"] == "https://example.com/docs"

        miss = prov.execute("bookmarks", action="search", keyword="xxx")
        assert miss["success"] is True
        assert miss["data"]["bookmarks"] == []

    def test_bookmark_alias_methods(self, tmp_path):
        prov = BrowserProvider(kv_path=str(tmp_path / "bookmarks.json"))
        result = prov.execute("browser_bookmark_add",
                              url="https://x.test/1", title="X")
        assert result["success"] is True
        result = prov.execute("browser_bookmarks_list")
        assert result["data"]["bookmarks"][0]["url"] == "https://x.test/1"
        result = prov.execute("browser_bookmarks_search", keyword="x.test")
        assert len(result["data"]["bookmarks"]) == 1


class TestVisionProvider:

    def test_analyze_honest_no_provider(self, tmp_path):
        png = make_png(tmp_path / "img.png", 40, 30)
        prov = VisionProvider(settings=FakeSettings(VISION_PROVIDER=""))
        prov.set_backend(False)
        result = prov.execute("vision_analyze", image_path=png)
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert "VISION_PROVIDER" in result["message"] or "vision" in result["message"].lower()

    def test_image_metadata_real_read(self, tmp_path):
        png = make_png(tmp_path / "meta.png", 60, 40)
        prov = VisionProvider()
        result = prov.execute("image_metadata", image_path=png)
        assert result["success"] is True
        data = result["data"]
        assert data["width"] == 60
        assert data["height"] == 40
        assert data["format"] == "PNG"
        assert data["mode"] == "RGB"
        assert data["size_bytes"] == os.path.getsize(png)

    def test_screen_coordinates_center_math(self, tmp_path):
        png = make_png(tmp_path / "coords.png", 200, 100)
        prov = VisionProvider()
        result = prov.execute("screen_coordinates", image_path=png)
        assert result["success"] is True
        data = result["data"]
        assert data["normalized_x"] == 0.5
        assert data["normalized_y"] == 0.5
        assert data["absolute_x"] == 100
        assert data["absolute_y"] == 50

    def test_screen_coordinates_custom_point(self, tmp_path):
        png = make_png(tmp_path / "coords2.png", 200, 100)
        prov = VisionProvider()
        result = prov.execute("screen_coordinates", image_path=png, x=50, y=25)
        assert result["success"] is True
        data = result["data"]
        assert data["normalized_x"] == 0.25
        assert data["normalized_y"] == 0.25

    def test_screen_coordinates_relative_to_screen(self, tmp_path):
        png = make_png(tmp_path / "coords3.png", 200, 100)
        prov = VisionProvider()
        result = prov.execute("screen_coordinates", image_path=png,
                              relative_to_screen=True)
        assert result["success"] is True
        assert result["data"]["normalized_x"] == 0.5
        assert isinstance(result["data"]["absolute_x"], int)
        assert isinstance(result["data"]["absolute_y"], int)

    def test_screen_coordinates_missing_file(self, tmp_path):
        prov = VisionProvider()
        result = prov.execute("screen_coordinates",
                              image_path=str(tmp_path / "nope.png"))
        assert result["success"] is False
        assert result["status"] == "FAILED"


class TestImageGenProvider:

    def test_not_configured_when_provider_empty(self, tmp_path):
        prov = ImageGenProvider(
            settings=FakeSettings(IMAGE_GENERATION_PROVIDER=""),
            output_root=str(tmp_path),
        )
        result = prov.execute("image_generate", prompt="cat")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert list(tmp_path.iterdir()) == []

    def test_not_configured_when_unknown_provider(self, tmp_path):
        prov = ImageGenProvider(
            settings=FakeSettings(IMAGE_GENERATION_PROVIDER="dalle"),
            output_root=str(tmp_path),
        )
        result = prov.execute("image_generate", prompt="cat")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert "canvas" in result["message"]

    def test_canvas_placeholder_png_written(self, tmp_path):
        prov = ImageGenProvider(
            settings=FakeSettings(IMAGE_GENERATION_PROVIDER="canvas"),
            output_root=str(tmp_path),
        )
        result = prov.execute("image_generate", prompt="sunset", width=64, height=48)
        assert result["success"] is True
        assert result["data"]["placeholder"] is True
        assert result["data"]["generated"] is True
        path = result["data"]["artefact"]["path"]
        assert os.path.isfile(path)
        with open(path, "rb") as handle:
            assert handle.read(4) == b"\x89PNG"
        from PIL import Image

        img = Image.open(path)
        assert img.size == (64, 48)
        img.close()


class TestVideoGenProvider:

    def test_reject_when_no_provider(self, tmp_path):
        prov = VideoGenProvider(
            settings=FakeSettings(VIDEO_GENERATION_PROVIDER=""),
            output_root=str(tmp_path),
        )
        result = prov.execute("video_generate", prompt="clip")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED

    def test_storyboard_job_lifecycle(self, tmp_path):
        prov = VideoGenProvider(
            settings=FakeSettings(VIDEO_GENERATION_PROVIDER="storyboard"),
            output_root=str(tmp_path),
        )
        result = prov.execute("video_generate", prompt="campfire")
        assert result["success"] is True
        assert result["data"]["video"] is False
        job_id = result["data"]["job_id"]
        assert job_id

        status_data = None
        deadline = time.time() + 5
        while time.time() < deadline:
            status = prov.execute("video_status", job_id=job_id)
            status_data = status["data"]
            if status["data"]["status"] in ("done", "failed", "cancelled"):
                break
            time.sleep(0.05)
        assert status_data["status"] == "done"
        assert status_data["result"]["generated"] is True
        assert status_data["result"]["video"] is False
        storyboard = status_data["result"]["storyboard_path"]
        assert os.path.isfile(storyboard)
        with open(storyboard, "r", encoding="utf-8") as handle:
            assert "Frame" in handle.read()

    def test_video_cancel_local_job(self, tmp_path):
        prov = VideoGenProvider(
            settings=FakeSettings(VIDEO_GENERATION_PROVIDER="storyboard"),
            output_root=str(tmp_path),
        )

        def slow_job():
            time.sleep(30)
            return "never"

        task = background_executor.submit("test_slow_job", slow_job)
        cancelled = prov.execute("video_cancel", job_id=task.task_id)
        assert cancelled["success"] is True
        status = prov.execute("video_status", job_id=task.task_id)
        assert status["success"] is True
        assert status["data"]["status"] == "cancelled"

    def test_status_unknown_job(self, tmp_path):
        prov = VideoGenProvider(
            settings=FakeSettings(VIDEO_GENERATION_PROVIDER="storyboard"),
            output_root=str(tmp_path),
        )
        result = prov.execute("video_status", job_id="does-not-exist")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED


class TestCameraProvider:

    def test_camera_requires_permission_first(self, tmp_path):
        prov = CameraProvider(kv_path=str(tmp_path / "perms.json"))
        prov.set_backend(False)
        result = prov.execute("camera_capture")
        assert result["success"] is False
        assert result["status"] == STATUS_REQUIRES_PERMISSION
        assert "permission" in result["message"].lower()

    def test_camera_not_configured_after_grant_but_no_backend(self, tmp_path):
        prov = CameraProvider(kv_path=str(tmp_path / "perms.json"))
        prov.set_backend(False)
        prov.grant_camera_permission()
        result = prov.execute("camera_capture")
        assert result["success"] is False
        assert result["status"] == STATUS_NOT_CONFIGURED
        assert "cv2" in result["message"].lower()

    def test_permission_state_persisted(self, tmp_path):
        store_path = str(tmp_path / "perms.json")
        prov = CameraProvider(kv_path=store_path)
        assert prov._camera_permission_granted() is False
        prov.grant_camera_permission()
        assert prov._camera_permission_granted() is True

        reloaded = CameraProvider(kv_path=store_path)
        assert reloaded._camera_permission_granted() is True
        reloaded.revoke_camera_permission()
        assert reloaded._camera_permission_granted() is False

    def test_screen_capture_real_or_honest(self, tmp_path):
        prov = CameraProvider(kv_path=str(tmp_path / "perms.json"))
        if not prov._has_pyautogui():
            result = prov.execute("screen_capture", directory=str(tmp_path),
                                  filename="shot.png")
            assert result["success"] is False
            assert result["status"] in ("NOT_CONFIGURED", "FAILED")
            return
        result = prov.execute("screen_capture", directory=str(tmp_path),
                              filename="shot.png")
        if result["success"]:
            path = result["data"]["path"]
            assert os.path.isfile(path)
            with open(path, "rb") as handle:
                assert handle.read(4) == b"\x89PNG"
        else:
            assert result["status"] in ("FAILED", "NOT_CONFIGURED")


class TestRegistryContract:

    def test_providers_registered_with_expected_capabilities(self):
        from core.providers import providers_registry

        browser = providers_registry.get("browser")
        assert browser is not None
        assert "bookmarks" in browser.capabilities

        vision = providers_registry.get("vision")
        assert vision is not None
        assert "image_metadata" in vision.capabilities

        image_gen = providers_registry.get("image_gen")
        assert image_gen is not None
        assert "image_generate" in image_gen.capabilities

        video_gen = providers_registry.get("video_gen")
        assert video_gen is not None
        assert "video_status" in video_gen.capabilities

        camera = providers_registry.get("camera")
        assert camera is not None
        assert "camera_capture" in camera.capabilities