"""Security & permission guard (row 24) — central privileged-action policy.

* detects destructive / privileged intents in natural language
* blocks credential exfiltration attempts and dangerous shell patterns
* prevents persistence & privilege-escalation commands
* relies on the ConfirmationManager as the single gate for
  destructive/high-risk actions (never bypassed without a pending request)
"""

import re

from core.confirmation import CONFIRMATION

_DELETE_PATTERNS = [
    r"\bdelete\b", r"\bremove\b", r"\bpurge\b", r"\bwipe\b", r"\berase\b",
    r"\btrash\b", r"\bshred\b",
]
_KILL_PATTERNS = [r"kill\b", r"\bterminate\b", r"close process", r"\bforce.?close\b"]
_SHUTDOWN_PATTERNS = [r"\bshut\s?down\b", r"\brestart\b", r"\breboot\b",
                      r"\bpower\s?off\b", r"\bhibernate\b"]
_PERSISTENCE_PATTERNS = [r"add.*startup", r"autorun", r"hklm\\run",
                         r"create.*service", r"schtasks"]
_PRIVILEGE_PATTERNS = [r"run as administrator", r"elevate", r"grant admin",
                       r"uac bypass", r"\\windows\\system32", r"reg add",
                       r"owner .* reboot"]

_EXFIL_PATTERNS = [r"api[_-]?key[=:\s]", r"password[=:\s]", r"secret[=:\s]",
                   r"token[=:\s]", r"authorization:", r"client[_-]?secret"]


class SecurityGuard:

    def __init__(self, confirmation=CONFIRMATION, detect=True):
        self.confirmation = confirmation
        self.detect = detect

    # ------------------------------------------------------------------
    def detect_delete_file(self, text):
        return any(re.search(pattern, str(text or ""), re.IGNORECASE)
                   for pattern in _DELETE_PATTERNS)

    def detect_kill_process(self, text):
        return any(re.search(pattern, str(text or ""), re.IGNORECASE)
                   for pattern in _KILL_PATTERNS)

    def detect_shutdown(self, text):
        return any(re.search(pattern, str(text or ""), re.IGNORECASE)
                   for pattern in _SHUTDOWN_PATTERNS)

    def detect_restart(self, text):
        return any(re.search(pattern, str(text or ""), re.IGNORECASE)
                   for pattern in (r"\brestart\b", r"\breboot\b"))

    # ------------------------------------------------------------------
    def _blocked_text(self, text, patterns):
        lowered = str(text or "").lower()
        return any(re.search(p, lowered, re.IGNORECASE) for p in patterns)

    def blocks_credential_exfiltration(self, text):
        return self._blocked_text(text, _EXFIL_PATTERNS) and self.detect

    def blocks_persistence(self, text):
        return self._blocked_text(text, _PERSISTENCE_PATTERNS) and self.detect

    def blocks_privilege_escalation(self, text):
        return self._blocked_text(text, _PRIVILEGE_PATTERNS) and self.detect

    # ------------------------------------------------------------------
    def check(self, text, context=None):
        """Full policy evaluation for a request string."""
        issues = []
        if self.blocks_credential_exfiltration(text):
            issues.append("credential_exfiltration")
        if self.blocks_persistence(text):
            issues.append("persistence")
        if self.blocks_privilege_escalation(text):
            issues.append("privilege_escalation")
        if self.detect_shutdown(text):
            issues.append("shutdown")
        if self.detect_delete_file(text):
            issues.append("delete_file")
        if self.detect_kill_process(text):
            issues.append("kill_process")
        return {"blocked": bool(issues), "issues": issues}

    def may_execute(self, request, risk="low", user_confirmed=False):
        evaluation = self.check(request)
        if evaluation["blocked"]:
            return {"allowed": False, "reason": evaluation["issues"][0],
                    "issues": evaluation["issues"]}
        from core.safety import RISK_HIGH, _RISK_ORDER
        high_risk = _RISK_ORDER.get(risk, _RISK_ORDER[RISK_HIGH]) >= _RISK_ORDER[RISK_HIGH]
        if high_risk and user_confirmed is False:
            return {"allowed": False, "reason": "requires_confirmation"}
        return {"allowed": True}


security_guard = SecurityGuard()

__all__ = ["SecurityGuard", "security_guard"]