"""Upgrade layer — brain-level helpers (calculator, TTS sanitizer, action
resolution, document detection, identity memory routing).

These power the "smart commands" the interactive Brain hands off to:
* safe expression calculator (plain + relative values)
* TTS text sanitizer (strip markdown, collapse whitespace)
* command resolution (open default browser / existing app / honest failure)
* document intent detection ("summarize this file" stays a document action)
* identity-guarded memory storage
"""

import ast
import re
import shutil
import subprocess

from brain.identity import identity_guard

_MARKDOWN_RE = re.compile(r"[*_#`>~\[\]\(\)]")
_WS_RE = re.compile(r"\s+")


class Calculator:
    """Safe arithmetic on plain expressions. Never executes code."""

    _safe_bins = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
                  ast.Mod, ast.Pow, ast.USub, ast.UAdd}

    @classmethod
    def eval_expression(cls, expression):
        text = str(expression or "").strip()
        if not text:
            return {"success": False, "message": "empty expression"}
        try:
            tree = ast.parse(text, mode="eval")
            value = cls._eval(tree.body)
            return {"success": True, "value": value,
                    "message": f"{text} = {value}"}
        except Exception as exc:
            return {"success": False, "message": f"could not evaluate: {exc}"}

    @classmethod
    def _eval(cls, node):
        if isinstance(node, ast.Expression):
            return cls._eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in cls._safe_bins:
            if isinstance(node.op, ast.Pow):
                base = float(cls._eval(node.left))
                exp = float(cls._eval(node.right))
                if base < 0 and not float(exp).is_integer():
                    raise ValueError("invalid negative power")
                return base ** exp
            return cls._binop(type(node.op))(cls._eval(node.left), cls._eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = cls._eval(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        raise ValueError("unsupported expression")

    @staticmethod
    def _binop(op):
        return {ast.Add: lambda a, b: a + b,
                ast.Sub: lambda a, b: a - b,
                ast.Mult: lambda a, b: a * b,
                ast.Div: lambda a, b: a / b,
                ast.FloorDiv: lambda a, b: a // b,
                ast.Mod: lambda a, b: a % b}[op]

    @classmethod
    def relative(cls, text, base=None):
        """'double it', 'add 10%', 'half' relative to a base value."""
        lowered = str(text or "").lower()
        if base is None:
            return None
        if "double" in lowered:
            return base * 2
        if "half" in lowered or "halve" in lowered:
            return base / 2
        match = re.search(r"([+-]\d+(?:\.\d+)?)%", lowered)
        if match:
            return round(base * (1 + float(match.group(1)) / 100.0), 6)
        match = re.search(r"add\s+([\d.]+)", lowered)
        if match:
            return base + float(match.group(1))
        match = re.search(r"minus\s+([\d.]+)", lowered)
        if match:
            return base - float(match.group(1))
        return None


class TTS_Sanitizer:
    """Prepare text for spoken output (expand shorthand, strip markdown)."""

    @staticmethod
    def sanitize(text):
        text = str(text or "")
        text = _MARKDOWN_RE.sub(" ", text)
        text = _WS_RE.sub(" ", text).strip()
        text = re.sub(r"\be\.g\.", " for example ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bi\.e\.", " that is ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bw/", " with ", text, flags=re.IGNORECASE)
        text = _WS_RE.sub(" ", text).strip()
        return text


class STT_MemoryCapper:
    """Cap STT-spoken memory captures so they cannot overwhelm real memory."""

    MAX_CHARS = 500

    @classmethod
    def cap(cls, text, max_chars=MAX_CHARS):
        text = str(text or "").strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."


class ActionResolver:
    """Resolve application actions honestly."""

    @staticmethod
    def default_browser():
        for name in ("msedge.exe", "chrome.exe"):
            if shutil.which(name) or (shutil.which(name) is None and
                                      _exists(name)):
                return name.replace(".exe", "")
        return "msedge"

    @staticmethod
    def resolve_existing_app(name):
        from tools.apps import _launch
        return _launch(name) is not None

    @staticmethod
    def resolve(name):
        from tools.apps import KNOWN_APPS
        target = str(name or "").strip()
        if target.lower() in [a for a in KNOWN_APPS]:
            return "ok", target
        return "unknown", target

    @staticmethod
    def open(name):
        _, resolved = ActionResolver.resolve(name)
        well_known = {"browser", "default browser", "the browser"} 
        if str(name).lower() in well_known:
            cmd = ActionResolver.default_browser()
            try:
                subprocess.Popen([cmd])
                return {"success": True, "action": "open", "target": cmd,
                        "message": f"Opened {cmd}."}
            except Exception as exc:
                return {"success": False, "message": str(exc)}
        from tools.apps import open_app
        result = open_app(app=name)
        return {"success": result["success"], "action": "open",
                "target": resolved, "message": result.get("message", "")}


def _exists(win_name):
    from pathlib import Path
    return (Path("C:\\Windows\\System32") / win_name).exists()


class DocumentDetector:
    """Recognize document-intent phrases without misrouting actions."""

    DOCUMENT_PHRASES = ["summarize this", "summarise this", "summarize ",
                        "summarise ", "extract the text from", "read the file"]

    @classmethod
    def is_document(cls, text):
        lowered = str(text).lower().strip()
        if lowered.startswith(("open", "close", "move", "copy", "rename")):
            return False
        return any(phrase in lowered for phrase in cls.DOCUMENT_PHRASES)


_ARVEN_PREFIXES = ["hey arven,", "hey arven", "arven,", "arven", "ok arven,", "ok arven"]


def strip_arven_prefix(text):
    lowered = str(text or "").strip()
    for prefix in sorted(_ARVEN_PREFIXES, key=len, reverse=True):
        if lowered.lower().startswith(prefix):
            return lowered[len(prefix):].strip()
    return lowered


def normalize_boss_variant(text):
    result = identity_guard.canonical_name(text)
    return result if result else text


def guard_memory_fact(content):
    """Write-time identity guard for memory storage."""
    if identity_guard.blank_fact_dropped(content):
        return None
    if identity_guard._conflicts(str(content).lower()):
        return None
    return identity_guard.normalize_fact(content)


__all__ = ["Calculator", "TTS_Sanitizer", "STT_MemoryCapper", "ActionResolver",
           "DocumentDetector", "normalize_boss_variant", "guard_memory_fact"]