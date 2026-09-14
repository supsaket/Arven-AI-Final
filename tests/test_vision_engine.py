"""Vision engine contract (row 33) — validation, metadata, honest analysis."""

import os

from brain.vision_engine import VisionEngine, vision_engine


class TestValidate:

    def test_missing_path(self):
        outcome = vision_engine.validate("C:/definitely/missing.png")
        assert outcome["valid"] is False

    def test_none_path(self):
        assert vision_engine.validate(None)["valid"] is False

    def test_no_unsupported_types_claimed(self, tmp_path):
        bad = tmp_path / "notes.txt"
        bad.write_text("hi", encoding="utf-8")
        assert vision_engine.validate(str(bad))["valid"] is False

    def test_real_image_validated(self, tmp_path):
        from PIL import Image
        image = tmp_path / "pic.png"
        Image.new("RGB", (4, 4), "red").save(image)
        assert vision_engine.validate(str(image))["valid"] is True


class TestMetadata:

    def test_metadata_reads_real_values(self, tmp_path):
        from PIL import Image
        image = tmp_path / "pic.png"
        Image.new("RGB", (8, 6), "blue").save(image)
        outcome = vision_engine.image_metadata(str(image))
        assert outcome["success"] is True
        assert outcome["metadata"]["size"] == [8, 6]
        assert outcome["metadata"]["format"] == "PNG"

    def test_metadata_missing_file(self):
        outcome = vision_engine.image_metadata("C:/nope.png")
        assert outcome["success"] is False


class TestNoProvider:

    def test_describe_without_provider_is_none(self, tmp_path):
        from PIL import Image
        image = tmp_path / "pic.png"
        Image.new("RGB", (4, 4), "red").save(image)
        engine = VisionEngine(provider=None)
        assert engine.describe(str(image)) is None

    def test_analyze_without_provider_never_claims_recognition(self, tmp_path):
        from PIL import Image
        image = tmp_path / "pic.png"
        Image.new("RGB", (4, 4), "red").save(image)
        engine = VisionEngine(provider=None)
        outcome = engine.analyze(str(image))
        assert outcome["analyzed"] is False
        assert outcome["description"] is None

    def test_ocr_without_provider_is_honest(self, tmp_path):
        from PIL import Image
        image = tmp_path / "pic.png"
        Image.new("RGB", (4, 4), "red").save(image)
        engine = VisionEngine(provider=None)
        outcome = engine.ocr(str(image))
        assert outcome["success"] is False
        assert "OCR" in outcome["message"] or "no" in outcome["message"].lower()


class TestWithProvider:

    def test_provider_results_surfaced(self, tmp_path):
        from PIL import Image
        image = tmp_path / "pic.png"
        Image.new("RGB", (4, 4), "red").save(image)
        engine = VisionEngine(
            provider={"available": True,
                      "analyze": lambda path: "a red square"})
        description = engine.describe(str(image))
        assert description == "a red square"