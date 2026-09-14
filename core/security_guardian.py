"""Digital Verification & Security Guardian (feature 60, Day 2).

SecurityGuardian scans for exfiltration and credential patterns (masking real
secrets, never returning them), classifies URL safety, reviews permission
grants for least-privilege suggestions, and runs policy checks.

Content-security rule: credential_scan always returns a MASKED/redacted
placeholder — the raw secret never appears in output.
"""

import re
from urllib.parse import urlparse

# ----------------------------------------------------------------------
# Patterns
# ----------------------------------------------------------------------
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_API_KEY_PATTERNS = [
    re.compile(r"\b(?:api[_-]?key|apikey)\s*[=:]\s*([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|rk)_[A-Za-z0-9]{16,}"),          # openai-ish
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),                # google
    re.compile(r"\b[A-Za-z0-9]{32,}\b"),                     # long token-like
]

_PASSWORD_PATTERNS = [
    re.compile(r"\bpassword\s*[=:]\s*([^\s,;]+)", re.IGNORECASE),
    re.compile(r"\bpasswd\s*[=:]\s*([^\s,;]+)", re.IGNORECASE),
    re.compile(r"\bclient[_-]?secret\s*[=:]\s*([^\s,;]+)", re.IGNORECASE),
    re.compile(r"\bsecret\s*[=:]\s*([^\s,;]+)", re.IGNORECASE),
    re.compile(r"\btoken\s*[=:]\s*([^\s,;]+)", re.IGNORECASE),
]

_UPLOAD_PATTERNS = [
    re.compile(r"\b(?:upload|send|transmit|post|push|exfiltrat)\w*", re.IGNORECASE),
]
_LARGE_DATA_PATTERNS = [
    re.compile(r"\b(?:bulk|dump|all|entire|full|massive)(?:\s+data|\s+export|\s+database)", re.IGNORECASE),
    re.compile(r"\b\d{6,}\s*(?:rows|records|emails|contacts)\b", re.IGNORECASE),
]

_MASK_PLACEHOLDER = "[MASKED]"

_SUSPICIOUS_TLDS = {
    "tk", "ml", "ga", "cf", "gq", "xyz", "top", "club", "work", "click",
    "rest", "mom", "loan", "date", "racing", "stream", "gdn",
}


class SecurityGuardian:

    def __init__(self, kv=None):
        from core.kv import KeyValueStore
        self.kv = kv if kv is not None else KeyValueStore("data/security_guardian.json")

    # ------------------------------------------------------------------
    # Exfiltration scan
    # ------------------------------------------------------------------
    def exfil_scan(self, text):
        text = str(text or "")
        flags = []
        risk = "low"

        emails = _EMAIL_RE.findall(text)

        if _UPLOAD_PATTERNS and any(p.search(text) for p in _UPLOAD_PATTERNS):
            flags.append("upload_or_transfer")
        if _LARGE_DATA_PATTERNS and any(p.search(text) for p in _LARGE_DATA_PATTERNS):
            flags.append("large_data_marker")
        if len(emails) > 0 and any(p.search(text) for p in _UPLOAD_PATTERNS):
            flags.append("emails_accompany_transfer")
        if emails:
            flags.append("emails_present")

        if any(f in flags for f in ("upload_or_transfer", "large_data_marker")):
            risk = "high"
        elif flags:
            risk = "medium"

        return {
            "risk": risk,
            "flags": flags,
            "email_count": len(emails),
        }

    # ------------------------------------------------------------------
    # Credential scan + masking
    # ------------------------------------------------------------------
    def credential_scan(self, text):
        """Detect credentials and return a redacted text (secret never leaks)."""
        text = str(text or "")
        redacted = text
        found = []

        for pattern in _API_KEY_PATTERNS:
            for match in pattern.finditer(text):
                found.append({"type": "api_key"})
                redacted = redacted.replace(match.group(0), _MASK_PLACEHOLDER)

        for pattern in _PASSWORD_PATTERNS:
            for match in pattern.finditer(text):
                found.append({"type": "password"})
                redacted = redacted.replace(match.group(0), _MASK_PLACEHOLDER)

        # Mask anything that looked like a raw secret value but never output it.
        for chunk in re.findall(r"\b([A-Za-z0-9_\-\.]{20,})\b", text):
            lowered = chunk.lower()
            if any(tok in lowered for tok in ("sk-", "ai", "token", "secret", "key")):
                found.append({"type": "secret_like"})
                redacted = redacted.replace(chunk, _MASK_PLACEHOLDER)

        return {
            "detected": bool(found),
            "count": len(found),
            "types": sorted({f["type"] for f in found}),
            "redacted": redacted,
            "note": "secrets masked; values never returned",
        }

    # ------------------------------------------------------------------
    # URL safety
    # ------------------------------------------------------------------
    def url_safety(self, url, known_ok_domains=()):
        known = {str(d).lower().lstrip(".").rstrip(".") for d in (known_ok_domains or ())}
        parsed = urlparse(str(url or ""))
        host = (parsed.hostname or "").lower()
        tld = host.split(".")[-1] if "." in host else ""

        if not host:
            return {"verdict": "UNSAFE", "reason": "no valid host", "https": False,
                    "domain_known": False, "suspicious_tld": False}

        is_localhost = host in ("localhost", "127.0.0.1", "::1")
        https_ok = parsed.scheme == "https" or (is_localhost and parsed.scheme == "http")

        if not https_ok:
            return {"verdict": "UNSAFE", "reason": "https required (non-localhost)",
                    "https": False, "domain_known": host in known,
                    "suspicious_tld": tld in _SUSPICIOUS_TLDS}

        domain_known = host in known
        suspicious_tld = tld in _SUSPICIOUS_TLDS

        if suspicious_tld:
            verdict = "SUSPICIOUS"
            reason = "domain uses a suspicious TLD"
        elif domain_known:
            verdict = "SAFE"
            reason = "recognised safe domain"
        else:
            verdict = "UNKNOWN"
            reason = "domain not in known_ok list (https ok)"

        return {
            "verdict": verdict, "reason": reason, "https": True,
            "domain_known": domain_known, "suspicious_tld": suspicious_tld,
            "host": host,
        }

    # ------------------------------------------------------------------
    # Permission review
    # ------------------------------------------------------------------
    def permission_review(self, grants=None):
        """Inspect permission grants and suggest least-privilege reductions.

        ``grants`` may be a dict, or the method reads kv keys under
        ``permissions.*``. Values are only used for shape, never surfaced raw.
        """
        perms = {}
        if grants is not None:
            perms = dict(grants)
        else:
            for key in self.kv.keys(prefix="permissions."):
                perms[key] = self.kv.get(key, "")

        suggestions = []
        for key, value in perms.items():
            # Only read shape (bool/None/empty strings) — never leak values.
            truthy = bool(value) if isinstance(value, bool) else value not in (None, "", "0")
            if truthy:
                suggestions.append({
                    "key": key,
                    "suggestion": "consider revoking or narrowing this grant",
                    "severity": "high" if "all" in str(key).lower() or "*" in str(key) else "medium",
                })
            else:
                suggestions.append({
                    "key": key,
                    "suggestion": "already least-privilege (grant absent/off)",
                    "severity": "low",
                })
        return {"permission_count": len(perms), "suggestions": suggestions}

    # ------------------------------------------------------------------
    # Policy check
    # ------------------------------------------------------------------
    def policy_check(self, action, target, context=None):
        """Return {allowedish, recommendation, reasons, require_confirmation}."""
        from core.safety import SAFETY, RISK_DESTRUCTIVE, RISK_HIGH

        reasons = []
        risk = SAFETY.risk_label(action, target)
        require_confirmation = risk in (RISK_DESTRUCTIVE, RISK_HIGH)

        exfil = self.exfil_scan(f"{action} {target} {context or ''}")
        if exfil["risk"] == "high" or exfil["flags"]:
            reasons.append(f"exfil markers: {exfil['flags']}")
            require_confirmation = True

        if risk == RISK_DESTRUCTIVE:
            recommendation = "BLOCK" if not exfil["risk"] == "high" else "BLOCK_AND_AUDIT"
        elif require_confirmation:
            recommendation = "REQUIRE_CONFIRMATION"
        else:
            recommendation = "ALLOW"

        allowedish = risk != RISK_DESTRUCTIVE and not exfil["risk"] == "high"
        return {
            "allowedish": bool(allowedish),
            "recommendation": recommendation,
            "reasons": reasons,
            "require_confirmation": bool(require_confirmation),
            "risk": risk,
        }


__all__ = ["SecurityGuardian"]
