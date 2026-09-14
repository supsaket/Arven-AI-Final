"""Cybersecurity Toolkit (feature 60, Day 2).

Authorization-bound, safe, read-only cyber operations:
- An explicit *authorized scope* list. Any target outside it is refused
  (AUTHORIZATION_REQUIRED). "LOCAL_MACHINE" is the only scope that permits
  local file audits.
- Network probes limited to non-intrusive DNS and TLS checks via the
  standard library, each with a short timeout.
- External tool *discovery* reports whether binaries are installed — and
  scanning through them reports NOT_INSTALLED honestly; nothing is faked.
- An append-only evidence ledger records what was checked, not secrets.

confirmed/request_id are handled by the caller (gate layer).
"""

import hashlib
import shutil
import socket
import ssl
from datetime import datetime
from pathlib import Path

from core.kv import KeyValueStore
from core.security_guardian import SecurityGuardian

LOCAL_MACHINE = "LOCAL_MACHINE"
_LOCAL_TARGETS = {"localhost", "127.0.0.1", "::1"}

# Read-only inspection tools worth discovering; never used to attack.
DISCOVERABLE = [
    "nmap", "nikto", "openssl", "trivy", "semgrep", "bandit", "clamscan",
    "dig", "nslookup",
]

_DNS_TIMEOUT = 5
_TLS_TIMEOUT = 5
_MAX_EVIDENCE = 200

KNOWLEDGE = {
    "xss": {
        "fact": "Cross-Site Scripting lets an attacker inject executable "
                "script into a page other clients render.",
        "risk": "High — session theft, credential capture, defacement.",
        "recommendation": "Validate input, encode output, apply CSP.",
    },
    "sql_injection": {
        "fact": "SQL injection occurs when untrusted input is concatenated "
                "into SQL statements.",
        "risk": "High — data exfiltration, deletion, or privilege escalation.",
        "recommendation": "Use parameterised queries and least-privilege DBA.",
    },
    "csrf": {
        "fact": "Cross-Site Request Forgery forces an authenticated session "
                "to perform actions the user never intended.",
        "risk": "Medium — state-changing requests fire without consent.",
        "recommendation": "Use CSRF tokens, SameSite cookies, origin checks.",
    },
    "tls": {
        "fact": "TLS encrypts transport and authenticates the peer via its "
                "certificate chain.",
        "risk": "Medium — expired, self-signed, or mismatched chains enable "
                "MITM.",
        "recommendation": "Validate certificate chains, hostnames, and expiry.",
    },
    "phishing": {
        "fact": "Phishing uses social engineering to trick users into "
                "disclosing credentials or executing attachments.",
        "risk": "High — account takeover and malware delivery.",
        "recommendation": "Train users, verify sender identity, use MFA.",
    },
    "port_scanning": {
        "fact": "Port scanning enumerates open services on a host.",
        "risk": "Medium — reconnaissance; unauthorised scanning is "
                "often illegal.",
        "recommendation": "Only scan targets you own or have written "
                "authorisation for; consider full-disk firewalls.",
    },
    "zero_day": {
        "fact": "A zero-day is an unknown, unpatched vulnerability actively "
                "exploited before a fix exists.",
        "risk": "Severe — no vendor mitigation available.",
        "recommendation": "Defence in depth, monitoring, and fast patch "
                "pipeline for the rest of the stack.",
    },
    "password_hashing": {
        "fact": "Passwords should be salted, keyed hashes (e.g. bcrypt, "
                "argon2), never plain or MD5.",
        "risk": "High — plain secrets cause account-takeover on leaks.",
        "recommendation": "Use strong adaptive hashing, enforce MFA.",
    },
    "firewall": {
        "fact": "A firewall filters traffic by rule, policy, and state.",
        "risk": "Medium — misconfiguration leaks services or blocks "
                "legitimate traffic.",
        "recommendation": "Default-deny rules, review logs, restrict egress.",
    },
    "indicator_of_compromise": {
        "fact": "An IoC is a forensic artefact (hash, domain, behaviour) "
                "that signals a compromise.",
        "risk": "Medium — stale IoCs give false confidence.",
        "recommendation": "Treat IoCs as leads, not proof; verify with telemetry.",
    },
}


class CyberToolkit:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/cyber_toolkit.json")

    # ------------------------------------------------------------------
    def _now(self):
        return datetime.now().isoformat()

    def _scopes(self):
        return self.kv.get("_scopes", [])

    def _save_scopes(self, scopes):
        self.kv.set("_scopes", scopes)

    def _audit(self):
        return self.kv.get("_audit", [])

    def _record_evidence(self, entry):
        audit = self._audit()
        audit.append(entry)
        self.kv.set("_audit", audit[-_MAX_EVIDENCE:])

    # ------------------------------------------------------------------
    def add_scope(self, scope):
        scope = str(scope).strip()
        if not scope:
            raise ValueError("scope is required")
        scopes = self._scopes()
        if scope not in scopes:
            scopes.append(scope)
            self._save_scopes(scopes)
        return {"scope": scope, "scopes": scopes}

    def remove_scope(self, scope):
        scopes = [s for s in self._scopes() if s != scope]
        self._save_scopes(scopes)
        return {"scope": scope, "removed": scope not in scopes,
                "scopes": scopes}

    def list_scopes(self):
        return self._scopes()

    def authorized(self, target):
        target = str(target).strip()
        scopes = self._scopes()
        if not scopes:
            return False
        if target in scopes:
            return True
        if target.lower() in _LOCAL_TARGETS and LOCAL_MACHINE in scopes:
            return True
        try:
            is_path = Path(target).resolve()
        except Exception:
            return False
        if is_path and LOCAL_MACHINE in scopes and is_path.exists():
            return True
        return False

    # ------------------------------------------------------------------
    def discover_tools(self):
        result = {}
        for name in DISCOVERABLE:
            path = shutil.which(name)
            result[name] = {"installed": bool(path), "path": path}
        return result

    def explain(self, topic):
        entry = KNOWLEDGE.get(str(topic).strip().lower())
        if entry is None:
            raise KeyError(topic)
        return {
            "topic": str(topic).strip().lower(),
            "fact": entry["fact"],
            "risk": entry["risk"],
            "recommendation": entry["recommendation"],
            "kind": "knowledge",
        }

    # ------------------------------------------------------------------
    def _dns_probe(self, host):
        try:
            infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP,
                                       timeout=_DNS_TIMEOUT)
            addresses = sorted({i[4][0] for i in infos})
            return {"resolved": True, "addresses": addresses}
        except Exception as exc:
            return {"resolved": False, "error": repr(exc)[:200]}

    def _tls_probe(self, host):
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        try:
            with socket.create_connection((host, 443), timeout=_TLS_TIMEOUT) as \
                    sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    cert = tls.getpeercert()
                    return {
                        "tls": True,
                        "subject": dict(x[0] for x in cert.get("subject", [])),
                        "issuer": dict(x[0] for x in cert.get("issuer", [])),
                        "not_after": cert.get("notAfter"),
                    }
        except Exception as exc:
            return {"tls": False, "error": repr(exc)[:200]}

    def _file_audit(self, target_path):
        path = Path(target_path)
        if not path.exists():
            return {"status": "FAILED", "error": "path does not exist"}
        checksums = []
        if path.is_dir():
            files = [p for p in path.rglob("*") if p.is_file()][:200]
        else:
            files = [path]
        for candidate in files:
            try:
                digest = hashlib.sha256(
                    candidate.read_bytes()[:65536]).hexdigest()
                checksums.append({
                    "path": str(candidate),
                    "size": candidate.stat().st_size,
                    "sha256_prefix": digest[:12],
                })
            except Exception as exc:
                checksums.append({"path": str(candidate),
                                  "status": "FAILED", "error": repr(exc)})
        secrets = []
        for candidate in files[:20]:
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                scan = SecurityGuardian(kv=self.kv).credential_scan(text)
                if scan.get("detected") or scan.get("count"):
                    secrets.append({
                        "path": str(candidate),
                        "types": scan.get("types") or [],
                        "count": int(scan.get("count") or 0),
                        "masked_note": scan.get("note"),
                    })
            except Exception:
                continue
        return {"type": "file", "paths_checked": len(files),
                "checksums": checksums, "possible_secrets": secrets}

    # ------------------------------------------------------------------
    def scan(self, target, tool="tls", confirmed=False, request_id=None,
             by="user"):
        if not self.authorized(target):
            return {
                "target": target, "status": "AUTHORIZATION_REQUIRED",
                "message": "target not in authorized scope (add it via "
                           "cyber_scope_add, or use LOCAL_MACHINE for files)",
            }
        if not confirmed:
            return {"target": target, "status": "confirm_required",
                    "message": "cyber scan requires explicit confirmation"}

        tool = str(tool or "tls").strip().lower()
        host = str(target)

        # Local file/dir audit: an authorized existing path is audited DIRECTLY
        # (never silently switched to Path.cwd()). "localhost" with a local
        # tool audits the current workspace by explicit contract.
        path_target = None
        try:
            candidate = Path(host)
            if candidate.exists():
                path_target = candidate
        except Exception:
            path_target = None

        if tool in ("local", "file") or path_target is not None:
            use = path_target if path_target is not None else Path.cwd()
            out = self._file_audit(str(use))
            return {"target": target, "tool": "local", "status": "EXECUTED",
                    "evidence": out, "at": self._now()}

        if host.lower() in _LOCAL_TARGETS:
            if tool == "dns":
                probe = self._dns_probe(host)
            else:
                probe = self._tls_probe(host)
        else:
            if tool in ("dns",):
                probe = self._dns_probe(host)
            else:
                probe = self._tls_probe(host)

        available = self.discover_tools()
        if tool in available and available[tool]["installed"]:
            probe["tool_note"] = (f"{tool} installed; results above from "
                                  f"non-intrusive stdlib probes")
        elif tool in available:
            probe["tool_note"] = (f"external tool '{tool}' is NOT_INSTALLED; "
                                  f"no invasive scan was attempted")

        result = {"target": target, "tool": tool, "status": "EXECUTED",
                  "evidence": probe, "at": self._now()}
        self._record_evidence({
            "kind": "scan",
            "target": target,
            "tool": tool,
            "status": result["status"],
            "summary": {k: v for k, v in probe.items()
                        if isinstance(v, (bool, str, int, float, list, type(None)))},
            "at": result["at"],
        })
        return result

    def audit(self, limit=50):
        return list(reversed(self._audit()[-int(limit):]))


__all__ = ["CyberToolkit", "LOCAL_MACHINE", "KNOWLEDGE"]