"""Access Control — Permission Management (105).

Provides ``PermissionManager`` with grant/check/revoke, expiry-aware
datetime resolution, role-based defaults, least-privilege report, and
an audited confirmation-gated request flow.
"""

import time
from datetime import datetime, timezone, timedelta

from core.kv import KeyValueStore
from core.confirmation import CONFIRMATION

_DEFAULT_ROLES = {
    "owner": {"scope": "*", "actions": ["read", "write", "delete", "admin"]},
    "admin": {"scope": "*", "actions": ["read", "write"]},
    "guest": {"scope": "*", "actions": ["read"]},
}


class PermissionManager:
    """Grant, check, revoke, and audit access permissions (kv-persisted)."""

    def __init__(self, kv_path="data/access.json"):
        self._kv = KeyValueStore(kv_path)
        if self._kv.get("_grants") is None:
            self._kv.set("_grants", [])
        if self._kv.get("_audit") is None:
            self._kv.set("_audit", [])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _grants(self):
        return self._kv.get("_grants", [])

    def _save_grants(self, grants):
        self._kv.set("_grants", grants)

    def _audit(self, event, **extra):
        log = self._kv.get("_audit", [])
        log.append({"event": event, "at": time.time(), **extra})
        self._kv.set("_audit", log)

    # ------------------------------------------------------------------
    # Grant
    # ------------------------------------------------------------------

    def grant(self, scope, action, principal, ttl_days=None):
        expires_at = None
        if ttl_days is not None:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(days=ttl_days)
            ).isoformat()
        entry = {
            "scope": scope,
            "action": action,
            "principal": principal,
            "expires_at": expires_at,
            "source": "explicit",
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }
        grants = self._grants()
        grants.append(entry)
        self._save_grants(grants)
        self._audit("grant", scope=scope, action=action, principal=principal)
        return entry

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def check(self, scope, action, principal):
        """Return True if principal has (scope, action) and grant is not expired."""
        now = datetime.now(timezone.utc)
        grants = self._grants()
        for g in grants:
            if g["principal"] != principal:
                continue
            if g["scope"] != "*" and g["scope"] != scope:
                continue
            if g["action"] != "*" and g["action"] != action:
                continue
            if g.get("expires_at"):
                exp = datetime.fromisoformat(g["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now > exp:
                    continue
            return True
        # fall back to role defaults
        role = self._kv.get(f"_role_{principal}")
        if role and role in _DEFAULT_ROLES:
            allowed = _DEFAULT_ROLES[role]["actions"]
            if action in allowed or "*" in allowed:
                return True
        return False

    # ------------------------------------------------------------------
    # Revoke
    # ------------------------------------------------------------------

    def revoke(self, scope, action, principal):
        grants = self._grants()
        new_grants = [
            g for g in grants
            if not (g["scope"] == scope and g["action"] == action
                    and g["principal"] == principal)
        ]
        removed = len(grants) - len(new_grants)
        self._save_grants(new_grants)
        self._audit("revoke", scope=scope, action=action,
                     principal=principal, removed=removed)
        return {"removed": removed, "status": "AVAILABLE"}

    # ------------------------------------------------------------------
    # Request (confirmation-gated)
    # ------------------------------------------------------------------

    def request(self, scope, action, principal):
        request_id = CONFIRMATION.require(
            f"access_request:{principal}:{scope}:{action}",
            risk="high",
        )
        self._audit("request", scope=scope, action=action,
                     principal=principal, request_id=request_id)
        return {"request_id": request_id, "status": "REQUIRES_AUTH"}

    # ------------------------------------------------------------------
    # Role helpers
    # ------------------------------------------------------------------

    def set_role(self, principal, role):
        self._kv.set(f"_role_{principal}", role)
        return {"principal": principal, "role": role}

    # ------------------------------------------------------------------
    # Least-privilege report
    # ------------------------------------------------------------------

    def least_privilege_report(self):
        grants = self._grants()
        by_principal = {}
        for g in grants:
            p = g["principal"]
            by_principal.setdefault(p, []).append(g)
        report = []
        for principal, entries in sorted(by_principal.items()):
            scopes = {e["scope"] for e in entries}
            actions = {e["action"] for e in entries}
            report.append({
                "principal": principal,
                "grant_count": len(entries),
                "scopes": sorted(scopes),
                "actions": sorted(actions),
            })
        return report

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def audit_log(self):
        return list(self._kv.get("_audit", []))


__all__ = ["PermissionManager", "_DEFAULT_ROLES"]
