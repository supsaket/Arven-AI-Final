"""Privacy & Data Protection / GDPR (106).

Provides ``PrivacyPortal`` with data inventory, export with redaction,
right-to-anonymize (never silent delete), consent logging, and privacy
reporting.  All erasure operations create anonymized quarantine copies
and require explicit user confirmation via ``CONFIRMATION``.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.kv import KeyValueStore
from core.output import OutputManager
from core.confirmation import CONFIRMATION

_SECRET_MARKERS = {"password", "secret", "api_key", "token", "private_key", "credential"}

_ANONYMIZED_PLACEHOLDER = "[REDACTED]"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _uid():
    return uuid.uuid4().hex[:8]


def _is_secret_key(key):
    k = key.lower()
    return any(marker in k for marker in _SECRET_MARKERS)


def _anonymize_record(record):
    """Replace identifying fields in a dict with placeholders (list-safe)."""
    if isinstance(record, list):
        return [
            _anonymize_record(item) if isinstance(item, (dict, list)) else item
            for item in record
        ]
    if not isinstance(record, dict):
        return record
    anonymized = {}
    for k, v in record.items():
        if _is_secret_key(k):
            anonymized[k] = _ANONYMIZED_PLACEHOLDER
        elif isinstance(v, str) and ("@" in v or len(v) > 30):
            anonymized[k] = _ANONYMIZED_PLACEHOLDER
        elif isinstance(v, dict):
            anonymized[k] = _anonymize_record(v)
        elif isinstance(v, list):
            anonymized[k] = _anonymize_record(v)
        else:
            anonymized[k] = v
    return anonymized


class PrivacyPortal:
    """Privacy operations: inventory, export, erasure, consent, reporting."""

    def __init__(self, kv_path="data/privacy.json", data_dir=None, output_root=None):
        self._kv = KeyValueStore(kv_path)
        self._om = OutputManager(root=output_root) if output_root else OutputManager()
        self._data_dir = data_dir or str(
            Path(kv_path).parent if kv_path else "data"
        )
        if self._kv.get("_consent_log") is None:
            self._kv.set("_consent_log", [])
        if self._kv.get("_erasure_log") is None:
            self._kv.set("_erasure_log", [])

    # ------------------------------------------------------------------
    # Inventory (106)
    # ------------------------------------------------------------------

    def inventory(self):
        """Walk data_dir and report counts by file/store."""
        stores = {}
        data_path = Path(self._data_dir)
        if not data_path.exists():
            return {"stores": {}, "total_files": 0, "status": "UNAVAILABLE"}
        for p in data_path.rglob("*.json"):
            rel = str(p.relative_to(data_path))
            category = p.stem
            stores[rel] = {
                "category": category,
                "size_bytes": p.stat().st_size,
            }
        return {
            "stores": stores,
            "total_files": len(stores),
            "status": "AVAILABLE",
        }

    # ------------------------------------------------------------------
    # Export (106)
    # ------------------------------------------------------------------

    def request_export(self, user):
        """Build a redacted export bundle to Output/Privacy."""
        inv = self.inventory()
        bundle = {
            "user": user,
            "exported_at": _now_iso(),
            "stores": inv.get("stores", {}),
        }
        # redact any secret-like keys from the bundle
        bundle = _anonymize_record(bundle)

        output_dir = os.path.join(str(self._om.root), "Output", "Privacy")
        os.makedirs(output_dir, exist_ok=True)
        md_path = self._om.next_rw_path(
            output_dir, f"export_{user}", suffix=".md"
        )
        md_content = [
            f"# Privacy Export — {user}",
            f"Generated: {bundle['exported_at']}",
            "",
            "## Store summary",
        ]
        for name, info in bundle["stores"].items():
            md_content.append(f"- {name}: {info['category']} ({info['size_bytes']} bytes)")
        md_content.append(f"\nStores found: {len(bundle['stores'])}")
        md_path.write_text("\n".join(md_content), encoding="utf-8")
        self._om.metadata_sidecar(md_path, {"user": user, "type": "privacy_export"})

        json_path = md_path.with_suffix(".json")
        json_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

        return {
            "status": "AVAILABLE",
            "md_path": str(md_path),
            "json_path": str(json_path),
            "store_count": len(bundle["stores"]),
        }

    # ------------------------------------------------------------------
    # Right to Erasure / Anonymize (106)
    # ------------------------------------------------------------------

    def right_to_erasure(self, scope, confirmed=False, trusted=False,
                         request_id=None):
        """Create anonymized quarantine copy.  Never physically deletes.

        Requires confirmation via CONFIRMATION system.
        """
        if not confirmed or not request_id:
            req_id = CONFIRMATION.require(
                f"erasure:{scope}", risk="destructive"
            )
            return {
                "status": "REQUIRES_AUTH",
                "request_id": req_id,
                "message": (
                    "Erasure requires explicit confirmation. "
                    "An anonymized copy will be created; originals are "
                    "NOT deleted."
                ),
            }

        gate_ok, reason = CONFIRMATION.gate(
            "right_to_erasure", scope,
            confirmed=confirmed, trusted=trusted, request_id=request_id,
        )
        if not gate_ok:
            return {"status": "FAILED", "reason": reason}

        # Create quarantine directory
        quarantine_dir = os.path.join(
            str(self._om.root), "Output", "Privacy", "quarantine"
        )
        os.makedirs(quarantine_dir, exist_ok=True)

        # Walk data, create anonymized copies
        data_path = Path(self._data_dir)
        anonymized_files = []
        if data_path.exists():
            for p in data_path.rglob("*.json"):
                if p.parent.name == "quarantine":
                    continue
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    anon = _anonymize_record(raw)
                    out_path = Path(quarantine_dir) / p.name
                    out_path.write_text(
                        json.dumps(anon, indent=2), encoding="utf-8"
                    )
                    anonymized_files.append(str(out_path))
                except (json.JSONDecodeError, OSError):
                    continue

        # Mark erasure event
        erasure_log = self._kv.get("_erasure_log", [])
        erasure_entry = {
            "id": _uid(),
            "scope": scope,
            "anonymized_files": anonymized_files,
            "originals_deleted": False,
            "at": _now_iso(),
            "status": "erased_review",
        }
        erasure_log.append(erasure_entry)
        self._kv.set("_erasure_log", erasure_log)

        return {
            "status": "AVAILABLE",
            "anonymized_count": len(anonymized_files),
            "quarantine_dir": quarantine_dir,
            "originals_deleted": False,
            "message": (
                f"Anonymized copy of {len(anonymized_files)} store(s) "
                f"created in quarantine. Originals are marked "
                f"'erased_review' but NOT physically deleted."
            ),
        }

    # ------------------------------------------------------------------
    # Consent Log
    # ------------------------------------------------------------------

    def consent_log(self, user, purpose, granted=True):
        log = self._kv.get("_consent_log", [])
        entry = {
            "user": user,
            "purpose": purpose,
            "granted": granted,
            "at": _now_iso(),
        }
        log.append(entry)
        self._kv.set("_consent_log", log)
        return entry

    def list_consents(self):
        return list(self._kv.get("_consent_log", []))

    # ------------------------------------------------------------------
    # Privacy Report
    # ------------------------------------------------------------------

    def privacy_report(self):
        inv = self.inventory()
        return {
            "store_count": inv.get("total_files", 0),
            "consent_count": len(self._kv.get("_consent_log", [])),
            "erasure_count": len(self._kv.get("_erasure_log", [])),
            "status": "AVAILABLE",
            "disclaimer": (
                "This report is informational guidance only and does not "
                "constitute legal advice."
            ),
        }


__all__ = ["PrivacyPortal", "_anonymize_record", "_SECRET_MARKERS"]
