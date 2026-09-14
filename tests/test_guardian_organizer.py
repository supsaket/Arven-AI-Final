"""Tests: Security Guardian (60) + Organizer (59)."""

import os
from pathlib import Path

import pytest

from core.organizer import Organizer
from core.security_guardian import SecurityGuardian


# ----------------------------------------------------------------------
# Feature 60 — Security Guardian
# ----------------------------------------------------------------------
class TestSecurityGuardian:

    def _kv(self, tmp_path):
        from core.kv import KeyValueStore
        return KeyValueStore(tmp_path / "sec.json")

    def test_exfil_scan_flags_uploads(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        result = guardian.exfil_scan("please upload the entire database dump")
        assert "upload_or_transfer" in result["flags"]
        assert result["risk"] == "high"
        assert isinstance(result["email_count"], int)

    def test_credential_scan_masks_secret(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        secret = "sk-4f9K2xQ1zA7bC8dE9fG1hJ2kL3mN4oP5"
        text = f"api_key = {secret}"
        result = guardian.credential_scan(text)
        assert result["detected"] is True
        assert secret not in result["redacted"]
        assert "[MASKED]" in result["redacted"]

    def test_credential_scan_password(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        text = "password = hunter2secret"
        result = guardian.credential_scan(text)
        assert "hunter2secret" not in result["redacted"]

    def test_url_safety_https_required(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        verdict = guardian.url_safety("http://example.com", ["example.com"])
        assert verdict["verdict"] == "UNSAFE"
        assert verdict["https"] is False

    def test_url_safety_localhost_and_known(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        local = guardian.url_safety("http://localhost:8080", ["localhost"])
        assert local["https"] is True  # localhost exempt from https requirement
        safe = guardian.url_safety("https://trusted.dev", ["trusted.dev"])
        assert safe["verdict"] == "SAFE"

    def test_url_safety_suspicious_tld(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        verdict = guardian.url_safety("https://free.stuff.xyz", [])
        assert verdict["suspicious_tld"] is True
        assert verdict["verdict"] == "SUSPICIOUS"

    def test_permission_review_zero_privilege(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        grants = {
            "permissions.files.read": False,
            "permissions.network.send": None,
            "permissions.shell.exec": "",
        }
        result = guardian.permission_review(grants)
        assert result["permission_count"] == 3
        # zero-privilege grants yield low-severity least-privilege suggestions
        for suggestion in result["suggestions"]:
            assert suggestion["severity"] == "low"

    def test_permission_review_never_leaks_values(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        grants = {"permissions.api.token": "verysecretvalue123"}
        result = guardian.permission_review(grants)
        text = str(result)
        assert "verysecretvalue123" not in text

    def test_permission_review_from_kv_prefix(self, tmp_path):
        kv = self._kv(tmp_path)
        kv.set("permissions.admin", True)
        guardian = SecurityGuardian(kv)
        result = guardian.permission_review()
        assert result["permission_count"] == 1

    def test_policy_check_requires_confirmation(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        result = guardian.policy_check("delete_file", "data/kv.json")
        assert result["recommendation"] in ("BLOCK", "BLOCK_AND_AUDIT", "REQUIRE_CONFIRMATION")
        assert "require_confirmation" in result
        assert isinstance(result["allowedish"], bool)

    def test_policy_check_low_risk(self, tmp_path):
        guardian = SecurityGuardian(self._kv(tmp_path))
        result = guardian.policy_check("status", "")
        assert result["recommendation"] == "ALLOW"
        assert result["require_confirmation"] is False


# ----------------------------------------------------------------------
# Feature 59 — Organizer
# ----------------------------------------------------------------------
class TestOrganizer:

    def _kv(self, tmp_path):
        from core.kv import KeyValueStore
        return KeyValueStore(tmp_path / "org.json")

    def test_build_daily_plan_deterministic(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        tasks = [
            {"title": "meeting", "est_minutes": 30, "priority": "high"},
            {"title": "write", "est_minutes": 90, "priority": "medium"},
            {"title": "read", "est_minutes": 20, "priority": "low"},
        ]
        plan_a = org.build_daily_plan(tasks)
        plan_b = org.build_daily_plan(tasks)
        assert plan_a["slots"] == plan_b["slots"]  # deterministic
        starts = [s["start"] for s in plan_a["slots"]]
        # earliest available slot allocation: starts non-decreasing
        assert starts == sorted(starts)

    def test_build_daily_plan_honors_start_hour(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        plan = org.build_daily_plan(
            [{"title": "x", "est_minutes": 30}], start_hour=9)
        assert plan["slots"][0]["start"].startswith("2026")
        assert "T09:00" in plan["slots"][0]["start"]

    def test_event_validation(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        bad = org.validate_datetime("not a date")
        assert bad["ok"] is False
        good = org.validate_datetime("2026-01-01 09:00")
        assert good["ok"] is True

    def test_create_event_end_after_start(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        ok = org.create_event("e1", "standup", "2026-01-01 09:00", "2026-01-01 09:30")
        assert ok["ok"] is True
        bad = org.create_event("e2", "bad", "2026-01-01 10:00", "2026-01-01 09:00")
        assert bad["ok"] is False

    def test_conflicts_detection(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        org.create_event("a", "a", "2026-01-01 09:00", "2026-01-01 10:00")
        org.create_event("b", "b", "2026-01-01 09:30", "2026-01-01 10:30")
        org.create_event("c", "c", "2026-01-01 11:00", "2026-01-01 12:00")
        conflicts = org.conflicts()
        assert any({"a", "b"} <= {c["a"], c["b"]} for c in conflicts)

    def test_upcoming(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        from datetime import datetime, timedelta
        now = datetime.now()
        org.create_event("soon", "soon", now.isoformat()[:16],
                         (now + timedelta(hours=1)).isoformat()[:16])
        org.create_event("past", "past",
                         (now - timedelta(days=2)).isoformat()[:16],
                         (now - timedelta(days=1)).isoformat()[:16])
        upcoming = org.upcoming(days=7, now=now)
        ids = {e["id"] for e in upcoming}
        assert "soon" in ids
        assert "past" not in ids

    def test_external_calendar_sync_honest(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        assert org.external_calendar_sync()["status"] == "NOT_CONFIGURED"

    def test_reminder_due_and_fire(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        from datetime import datetime, timedelta
        past = (datetime.now() - timedelta(hours=1)).isoformat()[:16]
        future = (datetime.now() + timedelta(hours=1)).isoformat()[:16]
        org.create_reminder("r1", "do the thing", past)
        org.create_reminder("r2", "future thing", future)
        due = org.due()
        assert any(r["id"] == "r1" for r in due)
        fired = org.fired("r1")
        assert fired["ok"] is True
        assert fired["reminder"]["fired"] is True
        # once fired, no longer due
        assert not any(r["id"] == "r1" for r in org.due())

    def test_email_digest_composition(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        from datetime import datetime, timedelta
        org.create_reminder("d1", "call bob", datetime.now().isoformat()[:16])
        org.create_event("a", "review", "2026-01-01 09:00", "2026-01-01 09:30")
        digest = org.email_digest()
        assert digest["subject"] == "ARVEN Daily Digest"
        assert "Daily Digest" in digest["body"]
        assert digest["reminder_count"] == 1
        assert digest["event_count"] == 1
        assert "call bob" in digest["body"]

    def test_weekly_review_template(self, tmp_path):
        org = Organizer(self._kv(tmp_path))
        template = org.weekly_review_template()
        assert template["sections"] == 6
        assert len(template["template"]) == 6
