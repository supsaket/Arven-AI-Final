"""Vision engine (row 33) — validation, metadata, and honest analysis.

* validates existence and supported file types before anything runs
* extracts real image metadata via PIL — never fabricated
* analysis routes to an injected provider (``{"available": True,
  "analyze": callable}``); without a configured provider it reports
  metadata-only and NEVER claims to have recognized the image
"""

import time
from pathlib import Path

_SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


class VisionEngine:

    def __init__(self, provider=None):
        self.provider = provider  # provider dict with analyze() or None

    # ------------------------------------------------------------------
    def validate(self, path):
        if not path:
            return {"valid": False, "reason": "no image path provided"}
        file_path = Path(path)
        if not file_path.exists():
            return {"valid": False, "reason": "file not found", "path": str(path)}
        if not file_path.is_file():
            return {"valid": False, "reason": "not a file", "path": str(path)}
        suffix = file_path.suffix.lower()
        if suffix not in _SUPPORTED:
            return {"valid": False, "reason": f"unsupported image type: {suffix}",
                    "path": str(path)}
        return {"valid": True, "path": str(path)}

    # ------------------------------------------------------------------
    def image_metadata(self, path):
        validated = self.validate(path)
        if not validated["valid"]:
            return {"success": False, "reason": validated["reason"],
                    "metadata": {}}
        try:
            from PIL import Image
            with Image.open(path) as image:
                metadata = {"format": image.format,
                            "size": list(image.size),
                            "mode": image.mode}
            return {"success": True, "path": str(path),
                    "metadata": metadata}
        except Exception as exc:
            return {"success": False, "reason": f"could not read metadata: {exc}",
                    "metadata": {}}

    # ------------------------------------------------------------------
    def analyze(self, path, timeout=10):
        validated = self.validate(path)
        if not validated["valid"]:
            return {"success": False, "message": validated["reason"],
                    "path": str(path)}
        metadata = self.image_metadata(path)
        provider = self.provider
        if provider is None or not provider.get("available"):
            return {
                "success": True,
                "message": "No vision model is configured — metadata only.",
                "path": str(path), "metadata": metadata.get("metadata", {}),
                "analyzed": False, "description": None,
            }
        started = time.monotonic()
        try:
            description = provider["analyze"](path)
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                return {"success": False,
                        "message": "the vision model timed out",
                        "path": str(path), "analyzed": False, "timeout": True}
            return {"success": True, "path": str(path),
                    "metadata": metadata.get("metadata", {}),
                    "analyzed": True, "description": description}
        except Exception as exc:
            return {"success": False,
                    "message": f"analysis failed: {exc}",
                    "path": str(path), "analyzed": False}

    def describe(self, path, **kwargs):
        outcome = self.analyze(path, **kwargs)
        if outcome.get("success") and outcome.get("analyzed"):
            return outcome["description"]
        return None

    def ocr(self, path):
        """OCR routes through the same provider (none configured → honest)."""
        outcome = self.analyze(path)
        if outcome.get("analyzed"):
            return {"success": True, "text": outcome.get("description")}
        return {"success": False, "message": "no OCR provider configured",
                "text": None}


vision_engine = VisionEngine()

__all__ = ["VisionEngine", "vision_engine"]