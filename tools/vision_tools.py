"""Vision tools — analyse a local image with an installed vision-capable model.

Backend strategy: use an ONNX-style local captioner if available; otherwise
an honest unavailable status. No internet is required and no image is sent
anywhere — analysis is fully local.
"""

from pathlib import Path

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:  # pragma: no cover
    HAVE_PIL = False

try:
    import ollama as _ollama
    HAVE_OLLAMA = True
except Exception:
    _ollama = None
    HAVE_OLLAMA = False


def _vision_backend():
    """Local vision backends tried in order (no image leaves the machine)."""
    return {"name": "ollama", "model": "llava", "available": HAVE_OLLAMA}


def image_analyze(image_path, prompt="Describe this image briefly.", **kwargs):
    path_str = str(image_path)
    target = Path(path_str)
    if not target.exists():
        return {"success": False, "action": "image_analyze",
                "message": f"Image not found: {image_path}"}
    if not HAVE_PIL:
        return {"success": False, "action": "image_analyze", "available": False,
                "message": "Pillow unavailable — cannot decode the image."}
    backend = _vision_backend()
    backend_ready = backend["available"] and backend["model"]
    if not backend_ready:
        return {"success": False, "action": "image_analyze", "available": False,
                "backend": backend["name"],
                "message": ("Vision analysis backend unavailable — no local "
                            "vision model is installed (would need ollama+llava).")}
    try:
        if _ollama is not None:
            response = _ollama.generate(
                model=backend["model"],
                prompt=str(prompt),
                images=[str(target)],
            )
            text = (response.get("response") or "").strip()
            return {"success": True, "action": "image_analyze",
                    "backend": backend["name"], "description": text,
                    "message": "Image analysed locally."}
        return {"success": False, "action": "image_analyze", "available": False,
                "message": "Vision backend driver not wired."}
    except Exception as exc:
        return {"success": False, "action": "image_analyze", "available": False,
                "backend": backend["name"],
                "message": f"image_analyze error: {exc}"}


def vision_status(**kwargs):
    backend = _vision_backend()
    return {"success": True, "action": "vision_status", "available": backend["available"],
            "backend": backend["name"], "model": backend["model"],
            "message": ("Vision backend available." if backend["available"]
                        else "No local vision model installed.")}


TOOLS = [
    {"name": "image_analyze", "function": image_analyze, "category": "Vision",
     "backend": "ollama", "risk": "low",
     "parameters": [{"name": "image_path", "required": True, "hint": "str"},
                    {"name": "prompt", "required": False, "hint": "str"}]},
    {"name": "vision_status", "function": vision_status, "category": "Vision",
     "backend": "ollama", "risk": "safe"},
]