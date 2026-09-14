"""Day 3 security hardening (T6 cyber / T7 backup / authorization)."""

import pytest

from core.access import PermissionManager
from core.confirmation import CONFIRMATION
from core.cyber_toolkit import CyberToolkit, LOCAL_MACHINE
from core.kv import KeyValueStore


@pytest.fixture()
def toolkit(tmp_path):
    return CyberToolkit(kv=KeyValueStore(str(tmp_path / "cyber.json")))


def test_unauthorized_target_refused_before_probe(toolkit):
    out = toolkit.scan("https://example.com", tool="dns", confirmed=True)
    assert out["status"] == "AUTHORIZATION_REQUIRED"
    assert "not in authorized scope" in out["message"]


def test_ghost_local_path_refused(toolkit):
    out = toolkit.scan(str(tmp_path_for_ghost()), tool="local",
                       confirmed=True)
    assert out["status"] == "AUTHORIZATION_REQUIRED"


def tmp_path_for_ghost():
    import os
    import tempfile
    return os.path.join(tempfile.gettempdir(), "definitely_missing_dir_arven")


def test_local_file_audit_targets_the_path_fix(tmp_path, toolkit):
    toolkit.add_scope(LOCAL_MACHINE)
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    target_file = probe_dir / "secret.env"
    target_file.write_text('api_key="sk-abcdefghijklmnopqrstuvwx"\n',
                           encoding="utf-8")
    out = toolkit.scan(str(probe_dir), tool="local", confirmed=True)
    assert out["status"] == "EXECUTED"
    evidence = out["evidence"]
    assert evidence["type"] == "file"
    checked = {c["path"] for c in evidence["checksums"]}
    assert str(target_file) in checked          # T6 fix: target, not cwd()
    assert evidence["paths_checked"] >= 1


def test_old_behavior_would_not_see_target_file(tmp_path, toolkit):
    """Regression guard: Path.cwd() audit would not include the tmp target."""
    toolkit.add_scope(LOCAL_MACHINE)
    probe_dir = tmp_path / "only_here"
    probe_dir.mkdir()
    only = probe_dir / "x.txt"
    only.write_text("content", encoding="utf-8")
    out = toolkit.scan(str(probe_dir), tool="file", confirmed=True)
    paths = {c["path"] for c in out["evidence"]["checksums"]}
    assert str(only) in paths


def test_secrets_masked_never_leaked(tmp_path, toolkit):
    toolkit.add_scope(LOCAL_MACHINE)
    probe_dir = tmp_path / "secrets_dir"
    probe_dir.mkdir()
    secret_file = probe_dir / "creds.txt"
    raw_secret = "sk-abcdefghijklmnopqrstuvwx"
    secret_file.write_text(f"KEY={raw_secret}\n", encoding="utf-8")
    out = toolkit.scan(str(probe_dir), tool="local", confirmed=True)
    secrets = out["evidence"]["possible_secrets"]
    blob = str(secrets)
    assert len(secrets) == 1
    assert secrets[0]["count"] >= 1
    assert raw_secret not in blob
    assert out["status"] == "EXECUTED"


def test_external_tool_not_installed_honest(toolkit, tmp_path, monkeypatch):
    toolkit.add_scope("offline-host.invalid")
    toolkit._tls_probe = lambda host: {"tls": False, "error": "offline"}
    discovered = toolkit.discover_tools()
    assert "nmap" in discovered
    assert isinstance(discovered["nmap"]["installed"], bool)
    out = toolkit.scan("offline-host.invalid", tool="nmap", confirmed=True)
    assert out["status"] == "EXECUTED"
    note = out["evidence"].get("tool_note", "")
    assert "NOT_INSTALLED" in note


def test_backup_restore_refusals(tmp_path):
    from core.backup import BackupManager
    ws = tmp_path / "ws"
    out_root = tmp_path / "out"
    (ws / "data").mkdir(parents=True)
    (ws / "data" / "a.txt").write_text("alpha", encoding="utf-8")
    mgr = BackupManager(workspace_root=str(ws), output_root=str(out_root))

    snap = mgr.snapshot("check")
    snap_id = snap["id"]

    refused = mgr.restore(snap_id, str(tmp_path / "target"))
    assert refused["status"] == "FAILED"
    assert "confirmation required" in refused["message"]  # no silent restore

    unknown = mgr.restore("does_not_exist", str(tmp_path / "t2"),
                          confirmed=True)
    assert unknown["status"] == "FAILED"
    assert "not found" in unknown["message"]

    snap_dir = mgr.backup_root / snap_id
    (snap_dir / "data" / "a.txt").write_text("TAMPERED!", encoding="utf-8")
    tampered_verify = mgr.verify(snap_id)
    assert tampered_verify["status"] == "FAILED"
    assert tampered_verify["mismatches"]

    target = tmp_path / "target3"
    refused2 = mgr.restore(snap_id, str(target), confirmed=True)
    assert refused2["status"] == "FAILED"
    assert "integrity" in refused2["message"]
    assert not (target / "data" / "a.txt").exists()


def test_restore_writes_only_into_explicit_target(tmp_path):
    from core.backup import BackupManager
    ws = tmp_path / "ws"
    out_root = tmp_path / "out"
    (ws / "data").mkdir(parents=True)
    source = ws / "data" / "a.txt"
    source.write_text("original", encoding="utf-8")
    mgr = BackupManager(workspace_root=str(ws), output_root=str(out_root))
    snap = mgr.snapshot("intact")

    target = tmp_path / "restored"
    out = mgr.restore(snap["id"], str(target), confirmed=True)
    assert out["status"] == "AVAILABLE"
    assert out["restored"] is True
    assert (target / "data" / "a.txt").read_text() == "original"
    assert source.read_text() == "original"      # live store untouched
    siblings = {p.name for p in tmp_path.iterdir()}
    assert "restored" in siblings
    assert "restored2" not in siblings


def test_permission_manager_grant_check_revoke_expiry(tmp_path):
    pm = PermissionManager(kv_path=str(tmp_path / "access.json"))
    pm.grant("cyber", "invoke", "boss")
    assert pm.check("cyber", "invoke", "boss") is True
    assert pm.check("cyber", "invoke", "nosy") is False
    revoked = pm.revoke("cyber", "invoke", "boss")
    assert revoked["removed"] == 1
    assert pm.check("cyber", "invoke", "boss") is False


def test_permission_expired_grant_not_honored(tmp_path):
    pm = PermissionManager(kv_path=str(tmp_path / "access2.json"))
    pm.grant("cyber", "invoke", "boss", ttl_days=-1)
    assert pm.check("cyber", "invoke", "boss") is False


def test_permission_request_requires_auth(tmp_path):
    pm = PermissionManager(kv_path=str(tmp_path / "access3.json"))
    out = pm.request("cyber", "invoke", "boss")
    assert out["status"] == "REQUIRES_AUTH"
    assert out["request_id"]
    assert CONFIRMATION.is_pending(out["request_id"]) is True


def test_guest_role_is_read_only(tmp_path):
    pm = PermissionManager(kv_path=str(tmp_path / "access4.json"))
    pm.set_role("guest_user", "guest")
    assert pm.check("*", "read", "guest_user") is True
    assert pm.check("*", "write", "guest_user") is False