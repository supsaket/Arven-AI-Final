"""Intent detection — classify a command into a first-class intent.

Implements the routing used by the agent layer:
* open_app   — open <app> / launch <app>
* close_app  — close <app> / quit <app>
* identity   — who are you / what is your name / am I <boss>
* memory     — remember X / what do you remember
* other intent helpers (calendar, research, coding, document, calculator)
"""

import re

from core.upgrade import DocumentDetector, strip_arven_prefix

_OPEN_WORDS = ("open", "open up", "launch", "start", "run", "chalao", "chala",
               "khol", "kholo", "open kar", "open karo")
_CLOSE_WORDS = ("close", "quit", "exit", "band kar", "band karo", "close kar",
                "close karo", "shut")
# Targets that are filler rather than an actual app to close.
_CLOSE_NOISE = {"enough", "it", "that", "this", "all", "down", "off", "the door",
                "the tab", "my eyes"}
_MEMORY_WORDS = ("remember", "remember that", "do you remember",
                 "what do you remember", "my memories")
_IDENTITY_WORDS = ("who are you", "what is your name", "what's your name",
                   "who am i", "what is my name", "what's my name",
                   "am i ", "my name is", "are you")


def detect_open_app(text):
    lowered = str(text).lower().strip()
    for word in _OPEN_WORDS:
        if lowered.startswith(word + " ") or lowered == word:
            target = lowered[len(word):].strip()
            if target and not target.startswith((" a ", " the ", " an ")):
                return True
    return False


def detect_close_app(text):
    lowered = str(text).lower().strip()
    for word in _CLOSE_WORDS:
        if lowered.startswith(word + " ") or lowered == word:
            target = lowered[len(word):].strip()
            if target and target not in _CLOSE_NOISE:
                return True
    return False


def detect_identity(text):
    lowered = str(text).lower().strip()
    return any(phrase in lowered for phrase in _IDENTITY_WORDS)


def detect_memory(text):
    lowered = str(text).lower().strip()
    return any(phrase in lowered for phrase in _MEMORY_WORDS)


def detect(text):
    """Return the winning intent as a string (default 'chat')."""
    text = strip_arven_prefix(text)

    if detect_memory(text):
        return "memory"
    if detect_identity(text):
        return "identity"
    if detect_open_app(text):
        return "open_app"
    if detect_close_app(text):
        return "close_app"
    if re.search(r"\bcalculat|\bsolve|\beq[u]?al|\bwhat is \d", str(text).lower()):
        return "calculate"
    if DocumentDetector.is_document(text):
        return "document"
    return "chat"


__all__ = ["detect", "detect_open_app", "detect_close_app", "detect_identity",
           "detect_memory"]