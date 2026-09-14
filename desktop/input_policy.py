"""Natural-language policies for the desktop application shell.

These decide, for a piece of user input, whether it concerns the *application*
(switch to Chat/Talk, or close ARVEN) rather than a request for the ARVEN Brain.
Pure functions so they are trivial to test and share no state.

Rules (case-insensitive):
  - App-exit phrases ("Bye Arven", "goodbye arven", "close yourself", ...) are
    owned by the app and NEVER reach Brain. Crucially "shutdown arven" means
    close the ARVEN app, NOT Windows. Real Windows-shutdown phrases (e.g.
    "shutdown the computer") are NOT in this list and still go to the Brain's
    gated destructive flow.
  - Chat/Talk selector phrases switch the mode without asking the Brain.
"""

from config import get_settings

__all__ = [
    "is_app_exit",
    "resolve_mode",
    "resolve_mode_selection",
    "resolve_switch",
    "normalise_exit_phrase",
]


def _norm(text):
    return " ".join((text or "").lower().strip().split())


def normalise_exit_phrase(phrase):
    """Return a canonical, normalised (lowercase, whitespace-collapsed) version
    of an app-exit phrase. Used to deduplicate/compare exit phrases."""
    return _norm(phrase) or None


def is_app_exit(text, phrases=None):
    """True when *text* asks ARVEN (the app) to close itself.

    ONLY matches phrases that unambiguously target the ARVEN application, so a
    generic "bye" or a "shutdown the computer" style command is never confused
    with closing ARVEN.
    """
    t = _norm(text)
    if not t:
        return False
    if phrases is None:
        phrases = get_settings().APP_EXIT_PHRASES
    for phrase in phrases:
        if _norm(phrase) in t:
            return True
    return False


def _selector(selector_map, value):
    t = _norm(value)
    if not t:
        return False
    for word in selector_map:
        if word in t:
            return True
    return False


def resolve_mode(text, selectors=None):
    """Return 'chat', 'talk', or 'both'/'conflict' when the text clearly selects
    a single preferred mode, else None.

    'both' indicates the text matched both chat and talk cues simultaneously
    (caller should ask for clarification).
    """
    if selectors is None:
        selectors = get_settings().APP_MODE_SELECTORS
    prefers_chat = _selector(selectors["chat"], text)
    prefers_talk = _selector(selectors["talk"], text)
    if prefers_chat and prefers_talk:
        return "both"
    if prefers_chat:
        return "chat"
    if prefers_talk:
        return "talk"
    return None


def resolve_switch(text):
    """Return 'chat' | 'talk' | None for an explicit mode-switch request.

    Handles "switch to talk", "switch to chat", "switch to voice (talk)",
    "switch to chat mode", etc. Requires an explicit "switch" cue so ordinary
    sentences mentioning "chat"/"talk" aren't misread as a switch.
    """
    t = _norm(text)
    if not t:
        return None
    if "switch" not in t and "change to" not in t and "go to" not in t:
        return None
    if "talk" in t or "voice" in t or "speak" in t:
        return "talk"
    if "chat" in t or "text" in t or "type" in t:
        return "chat"
    return None


# ---------------------------------------------------------------------------
# Startup mode-selection parser (robust to STT errors)
# ---------------------------------------------------------------------------
#
# Used ONLY when ARVEN is listening for the initial "Chat or Talk?" answer.
# It is tolerant of common STT mistakes on the short, acoustically-confusable
# words "chat" (-> "check", "chatt", "chad") and "talk" (-> "tok", "tawk").
#
# Two layers, evaluated in order:
#   1. EXPLICIT INTENT PHRASES  — full phrases are the strongest signal.
#   2. BOUNDED FUZZY MATCH      — a close lexical single-word match, with a
#      conservative distance so unrelated words are never accepted.
#
# "check" is treated as CHAT ONLY here (startup context); it is never globally
# interpreted as "chat" by the general conversation rules.
# ---------------------------------------------------------------------------

# Explicit, high-confidence intent phrases (substring match, case-insensitive).
_MODE_EXPLICIT_PHRASES = {
    "chat": [
        "i want chat", "i want to chat", "lets chat", "let's chat",
        "i prefer chat", "open chat", "use chat", "chat mode",
        "chat please", "go to chat",
    ],
    "talk": [
        "i want talk", "i want to talk", "lets talk", "let's talk",
        "i prefer talk", "open talk", "use talk", "talk mode",
        "talk please", "voice mode", "go to talk", "use voice",
    ],
}

# Words that, when spoken alone (or found as a clean token), select a mode.
_EXACT_MODE_WORDS = {
    "chat": {"chat", "text", "texts", "chats", "chatt", "chad", "check"},
    "talk": {"talk", "talkk", "tok", "tawk", "voice", "speak"},
}


def _edit_distance(a, b):
    """Levenshtein distance (bounded, small strings only)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i]
        for j in range(1, lb + 1):
            cur.append(min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (a[i - 1] != b[j - 1]),
            ))
        prev = cur
    return prev[lb]


def _sounds_like_inclusive(word, targets):
    """Conservative tolerance: accept an exact word, or a close lexical variant.

    Distance is bounded by word length (<=1 for 3-4 letter words, <=2 for
    longer), so "chatt"/"chad"/"check" and "tawk"/"tok"/"talkk" match, but an
    unrelated word like "dog" or "music" does not.
    """
    n = len(word)
    for target in targets:
        if word == target:
            return True
        limit = 2 if n >= 5 else 1
        if _edit_distance(word, target) <= limit:
            return True
    return False


def resolve_mode_selection(text):
    """Return 'chat' | 'talk' | 'both' | None for a startup mode-selection input.

    Robust to STT errors on the short mode words. 'both' means the input matched
    both Chat and Talk signals (caller asks for clarification); None means no
    confident mode was detected.
    """
    t = _norm(text)
    if not t:
        return None

    # Layer 1: explicit intent phrases (strongest).
    chat_explicit = any(_norm(p) in t for p in _MODE_EXPLICIT_PHRASES["chat"])
    talk_explicit = any(_norm(p) in t for p in _MODE_EXPLICIT_PHRASES["talk"])
    if chat_explicit and talk_explicit:
        return "both"
    if chat_explicit:
        return "chat"
    if talk_explicit:
        return "talk"

    # Layer 2: bounded fuzzy match on the short mode words.
    words = t.split()
    tokens = [w for w in words if w]
    chat_hit = False
    talk_hit = False
    for w in tokens:
        # Strip trailing punctuation that STT sometimes emits.
        w = w.rstrip(".,!?;:").lower()
        if not w:
            continue
        if any(_sounds_like_inclusive(w, (tx,)) for tx in _EXACT_MODE_WORDS["chat"]):
            chat_hit = True
        if any(_sounds_like_inclusive(w, (tx,)) for tx in _EXACT_MODE_WORDS["talk"]):
            talk_hit = True

    # Only count the raw "text"/"type" style aliases when they look like a
    # single-word answer, not when embedded in a sentence.
    if not chat_hit:
        for a in ("text", "texts", "type"):
            if t.strip().rstrip(".,!?;:") == a:
                chat_hit = True

    if chat_hit and talk_hit:
        return "both"
    if chat_hit:
        return "chat"
    if talk_hit:
        return "talk"
    return None
