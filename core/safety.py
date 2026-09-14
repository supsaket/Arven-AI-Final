"""Safety engine — risk classification and destructive-action gate.

The SafetyEngine is the single authority that decides how risky an action is.
Any tool that mutates the system (shell, files, communications) must pass
through it. Confirmation-gating is enforced by the ToolRegistry (see
``tools/registry.py``) backed by this classification.

Security rule: privileged/destructive actions never bypass this check.
"""

import re

# Risk tiers (low -> high). STRING values are what tools report.
RISK_SAFE = "safe"
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_DESTRUCTIVE = "destructive"

_RISK_ORDER = {
    RISK_SAFE: 0,
    RISK_LOW: 1,
    RISK_MEDIUM: 2,
    RISK_HIGH: 3,
    RISK_DESTRUCTIVE: 4,
}

_CONFIRM_THRESHOLD = RISK_HIGH  # high + requires confirmation

# Explicitly destructive verbs.
_DESTRUCTIVE_VERBS = (
    "delete", "remove", "wipe", "erase", "rm ", "del ", "unlink",
    "kill", "stop -f", "shutdown /s", "format", "mkfs", "rd /s",
    "takeown", "icacls /grant", "reg delete",
)

# High-risk action classes.
_HIGH_RISK_PATTERNS = (
    re.compile(r"\bsend\b.*\b\w+@", re.I),          # send an email
    re.compile(r"\bshell\b", re.I),                  # arbitrary shell
    re.compile(r"\bpowershell\b", re.I),
    re.compile(r"\bcmd\b", re.I),
    re.compile(r"\bwi-?fi\b|\bnetwork\b", re.I),     # network state mutation
    re.compile(r"\bmessag", re.I),                   # messaging
    re.compile(r"\bcalendar", re.I),                 # calendar create
)


class SafetyEngine:

    def __init__(self):
        self._denials = []
        self._confirmations = []

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def classify_name(self, name):
        """Classify risk by tool name/keyword."""
        lowered = (name or "").lower()

        if lowered.startswith(("run_shell", "shell_run", "exec")):
            return RISK_HIGH
        if lowered.startswith(("delete_", "remove_", "wipe", "format")):
            return RISK_DESTRUCTIVE
        if lowered.startswith(("write_", "move_", "rename_", "copy_", "create_")):
            return RISK_MEDIUM
        if lowered.startswith(("send_", "email_send", "calendar_create", "messaging_send")):
            return RISK_HIGH
        if lowered in (
            "open_app", "date_time", "system_info", "running_processes",
            "memory_search", "list_memories", "web_search", "fetch_page",
            "browser_navigate", "browser_status", "browser_search",
            "tts_status", "tts_speak", "media_command", "read_document",
            "read_file", "search_files", "capture_screen", "proactive_status",
        ):
            return RISK_LOW
        return RISK_MEDIUM

    def classify_action(self, action, target=""):
        """Classify a natural-language action phrase."""
        text = f"{action} {target}".lower().strip()

        for verb in _DESTRUCTIVE_VERBS:
            if verb.strip() in re.split(r"\s+", text) or verb in text:
                return RISK_DESTRUCTIVE

        for pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(text):
                return RISK_HIGH

        if any(word in text for word in ("open", "search", "date", "time", "status")):
            return RISK_LOW

        if any(word in text for word in ("create", "write", "copy", "move", "rename")):
            return RISK_MEDIUM

        return RISK_MEDIUM

    def risk_label(self, action, target=""):
        if action is None:
            return RISK_LOW
        if hasattr(action, "risk"):
            return action.risk
        return self.classify_action(str(action), str(target or ""))

    def requires_confirmation(self, risk):
        return _RISK_ORDER.get(str(risk), 4) >= _RISK_ORDER[_CONFIRM_THRESHOLD]

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------
    def check(self, action, target="", confirmed=False, trusted=False):
        """Authoritative gate. Returns a (allowed, reason) tuple.

        privileged = True only when the caller is a trusted internal caller
        that already consulted this engine. Direct callers without
        confirmation are REFUSED for destructive actions.
        """
        risk = self.risk_label(action, target)

        if risk == RISK_DESTRUCTIVE:
            # Never auto-trust destructive actions.
            if not (confirmed and trusted):
                self._denials.append((str(action), "confirm required"))
                return False, "destructive action requires confirmation"

        if self.requires_confirmation(risk) and not confirmed:
            self._denials.append((str(action), "confirm required"))
            return False, "action requires confirmation"

        self._confirmations.append((str(action), risk))
        return True, risk

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def audit(self):
        return {
            "denied": list(self._denials),
            "allowed": list(self._confirmations),
        }


try:
    SAFETY = SafetyEngine()
except Exception:  # never crash on import
    SAFETY = SafetyEngine()

__all__ = [
    "SafetyEngine",
    "SAFETY",
    "RISK_SAFE",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_HIGH",
    "RISK_DESTRUCTIVE",
]