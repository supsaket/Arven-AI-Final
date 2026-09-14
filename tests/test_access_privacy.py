"""Tests for Access Control (105) and Privacy/GDPR (106).
Each test uses isolated temp paths and temp output dirs."""

import json
import os

from core.access import PermissionManager
from core.privacy import PrivacyPortal, _anonymize_record
from core.kv import KeyValueStore
from core.confirmation import CONFIRMATION


# ------------------------------------------------------------------
# Access Control (105)
# ------------------------------------------------------------------


class TestGrantAndCheck:

    def test_grant_and_check(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("docs", "read", "alice", ttl_days=30)
        assert pm.check("docs", "read", "alice") is True
        assert pm.check("docs", "write", "alice") is False

    def test_scope_wildcard(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("*", "read", "bob")
        assert pm.check("any_name", "read", "bob") is True

    def test_action_wildcard(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("docs", "*", "carol")
        assert pm.check("docs", "delete", "carol") is True

    def test_expired_grant_denied(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("docs", "read", "alice", ttl_days=-1)
        assert pm.check("docs", "read", "alice") is False

    def test_no_grant_denied(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        assert pm.check("docs", "read", "ghost") is False


class TestRevoke:

    def test_revoke_removes(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("docs", "read", "alice")
        result = pm.revoke("docs", "read", "alice")
        assert result["removed"] == 1
        assert pm.check("docs", "read", "alice") is False


class TestRequest:

    def test_request_requires_confirmation(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        result = pm.request("docs", "write", "bob")
        assert result["status"] == "REQUIRES_AUTH"
        assert "request_id" in result
        assert CONFIRMATION.is_pending(result["request_id"])


class TestRoleDefaults:

    def test_role_default_map(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        # owner = *; admin = write; guest = read
        pm.set_role("admin_user", "admin")
        assert pm.check("docs", "write", "admin_user") is True
        assert pm.check("docs", "read", "admin_user") is True
        assert pm.check("docs", "delete", "admin_user") is False

    def test_guest_read_only(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.set_role("guest_user", "guest")
        assert pm.check("docs", "read", "guest_user") is True
        assert pm.check("docs", "write", "guest_user") is False


class TestLeastPrivilegeAndAudit:

    def test_least_privilege_report(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("docs", "read", "alice")
        pm.grant("docs", "write", "alice")
        pm.grant("mail", "read", "bob")
        report = pm.least_privilege_report()
        assert len(report) == 2
        alice = [r for r in report if r["principal"] == "alice"][0]
        assert alice["grant_count"] == 2
        assert alice["actions"] == ["read", "write"]

    def test_audit_log(self, tmp_path):
        pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
        pm.grant("docs", "read", "alice")
        pm.revoke("docs", "read", "alice")
        events = [e["event"] for e in pm.audit_log()]
        assert "grant" in events
        assert "revoke" in events


class TestAccessPersistence:

    def test_grants_persist(self, tmp_path):
        kv = str(tmp_path / "access.json")
        pm1 = PermissionManager(kv_path=kv)
        pm1.grant("docs", "read", "alice")
        pm2 = PermissionManager(kv_path=kv)
        assert pm2.check("docs", "read", "alice") is True


# ------------------------------------------------------------------
# Privacy / GDPR (106)
# ------------------------------------------------------------------


class TestInventory:

    def test_inventory_finds_stores(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "customers.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"name": "Jane", "email": "jane@example.com"}))
        portal = PrivacyPortal(
            kv_path=str(tmp_path / "privacy.json"), data_dir=data_dir
        )
        inv = portal.inventory()
        assert inv["status"] == "AVAILABLE"
        assert inv["total_files"] >= 1

    def test_inventory_missing_dir(self, tmp_path):
        portal = PrivacyPortal(
            kv_path=str(tmp_path / "privacy.json"),
            data_dir=str(tmp_path / "nope"),
        )
        inv = portal.inventory()
        assert inv["status"] == "UNAVAILABLE"
        assert inv["total_files"] == 0


class TestExport:

    def test_export_has_no_secret_markers(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "users.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "email": "jane@example.com",
                "password_hash": "abc123",
                "api_key": "sk-test-123",
            }))
        portal = PrivacyPortal(
            kv_path=str(tmp_path / "privacy.json"), data_dir=data_dir,
            output_root=str(tmp_path),
        )
        result = portal.request_export("jane")
        assert result["status"] == "AVAILABLE"
        content = open(result["md_path"], encoding="utf-8").read()
        assert "sk-test-123" not in content
        assert "abc123" not in content
        assert "jane@example.com" not in content

    def test_export_writes_files(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "a.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        portal = PrivacyPortal(
            kv_path=str(tmp_path / "privacy.json"), data_dir=data_dir,
            output_root=str(tmp_path),
        )
        result = portal.request_export("jane")
        assert os.path.exists(result["md_path"])
        assert os.path.exists(result["json_path"])


class TestErasure:

    def test_erasure_requires_confirmation(self, tmp_path):
        portal = PrivacyPortal(kv_path=str(tmp_path / "privacy.json"))
        result = portal.right_to_erasure("scope1", confirmed=False)
        assert result["status"] == "REQUIRES_AUTH"
        assert "request_id" in result

    def test_erasure_creates_anonymized_copy_without_deleting(self, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)
        orig = os.path.join(data_dir, "users.json")
        with open(orig, "w", encoding="utf-8") as f:
            json.dump({
                "name": "Jane Doe",
                "email": "jane@example.com",
                "password": "hunter2",
            }, f)

        portal = PrivacyPortal(
            kv_path=str(tmp_path / "privacy.json"), data_dir=data_dir,
            output_root=str(tmp_path),
        )
        req_id = CONFIRMATION.require("erasure:scope1", risk="destructive")
        result = portal.right_to_erasure(
            "scope1", confirmed=True, trusted=True, request_id=req_id
        )
        assert result["status"] == "AVAILABLE"
        assert result["originals_deleted"] is False
        # original still exists
        assert os.path.exists(orig)
        # anonymized copy created
        quarantine = os.listdir(
            os.path.join(str(tmp_path / "Output"), "Privacy", "quarantine")
        )
        assert len(quarantine) >= 1
        for fname in quarantine:
            with open(os.path.join(
                str(tmp_path / "Output"), "Privacy", "quarantine", fname
            ), encoding="utf-8") as f:
                data = json.load(f)
            text = json.dumps(data)
            assert "hunter2" not in text
            assert "jane@example.com" not in text

    def test_erasure_audited(self, tmp_path):
        portal = PrivacyPortal(kv_path=str(tmp_path / "privacy.json"))
        req_id = CONFIRMATION.require("erasure:scope2", risk="destructive")
        portal.right_to_erasure(
            "scope2", confirmed=True, trusted=True, request_id=req_id
        )
        log = portal._kv.get("_erasure_log", [])
        assert len(log) == 1
        assert log[0]["originals_deleted"] is False


class TestConsentAndReport:

    def test_consent_log(self, tmp_path):
        portal = PrivacyPortal(kv_path=str(tmp_path / "privacy.json"))
        portal.consent_log("jane", "data_processing", granted=True)
        portal.consent_log("jane", "marketing", granted=False)
        consents = portal.list_consents()
        assert len(consents) == 2
        assert consents[0]["purpose"] == "data_processing"
        assert consents[1]["granted"] is False

    def test_privacy_report(self, tmp_path):
        portal = PrivacyPortal(kv_path=str(tmp_path / "privacy.json"))
        report = portal.privacy_report()
        assert report["status"] == "AVAILABLE"
        assert "store_count" in report
        assert "consent_count" in report
        assert "disclaimer" in report


class TestAnonymize:

    def test_anonymize_record_masks_secrets(self):
        record = {
            "email": "jane@example.com",
            "password": "hunter2",
            "occupation": "engineer",
        }
        anon = _anonymize_record(record)
        assert anon["password"] == "[REDACTED]"
        assert anon["email"] == "[REDACTED]"
        assert anon["occupation"] == "engineer"


class TestPrivacyPersistence:

    def test_consent_persists_across_instances(self, tmp_path):
        kv = str(tmp_path / "privacy.json")
        p1 = PrivacyPortal(kv_path=kv)
        p1.consent_log("jane", "analytics")
        p2 = PrivacyPortal(kv_path=kv)
        assert len(p2.list_consents()) == 1