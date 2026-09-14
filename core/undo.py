"""Universal Undo & Transaction Recovery (feature 102, Day 2).

A transaction journal over the KeyValueStore: BEGIN captures a transaction,
each recorded operation writes a new value while preserving the pre-image of
every touched key exactly once, COMMIT closes the transaction and ROLLBACK
restores every pre-image. Rollback only reports success when every key was
restored — partial failures are surfaced honestly.
"""

import uuid
from datetime import datetime

from core.kv import KeyValueStore


class TransactionManager:

    def __init__(self, kv=None):
        self.kv = kv or KeyValueStore("data/undo.json")

    # ------------------------------------------------------------------
    def _now(self):
        return datetime.now().isoformat()

    def _txns(self):
        return self.kv.get("transactions", {})

    def _save(self, txns):
        self.kv.set("transactions", txns)

    def _get_txn(self, txn_id):
        txn = self._txns().get(txn_id)
        if txn is None:
            raise KeyError(txn_id)
        return txn

    # ------------------------------------------------------------------
    def begin(self, label="transaction"):
        txn = {
            "id": uuid.uuid4().hex[:16],
            "label": str(label or "transaction"),
            "status": "active",
            "ops": [],
            "preimages": {},
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        txns = self._txns()
        txns[txn["id"]] = txn
        self._save(txns)
        return {"id": txn["id"], "label": txn["label"], "status": "active"}

    def active_transactions(self):
        return [
            {"id": t["id"], "label": t["label"], "ops": len(t["ops"])}
            for t in self._txns().values()
            if t["status"] == "active"
        ]

    # ------------------------------------------------------------------
    def op(self, txn_id, key, value):
        txn = self._get_txn(txn_id)
        if txn["status"] != "active":
            raise ValueError(f"transaction {txn_id} is {txn['status']}")
        if key not in txn["preimages"]:
            txn["preimages"][key] = self.kv.get(key)
        self.kv.set(key, value)
        txn["ops"].append({"key": key, "at": self._now()})
        txn["updated_at"] = self._now()
        self._save(self._txns())
        return {"txn_id": txn_id, "key": key, "ops": len(txn["ops"])}

    def _restore(self, txn):
        restored = []
        failed = []
        for key, before in txn["preimages"].items():
            try:
                self.kv.set(key, before)
                restored.append(key)
            except Exception as exc:
                failed.append({"key": key, "error": repr(exc)})
        return restored, failed

    def rollback(self, txn_id):
        txn = self._get_txn(txn_id)
        if txn["status"] != "active":
            raise ValueError(f"transaction {txn_id} is {txn['status']}")
        restored, failed = self._restore(txn)
        txn["status"] = "rolled_back"
        txn["restored"] = restored
        txn["failed"] = failed
        txn["updated_at"] = self._now()
        self._save(self._txns())
        result = {
            "txn_id": txn_id,
            "status": "rolled_back",
            "keys_restored": len(restored),
            "keys_failed": len(failed),
        }
        if failed:
            result["message"] = "some keys could not be restored"
            result["failed_keys"] = failed
        return result

    def commit(self, txn_id):
        txn = self._get_txn(txn_id)
        if txn["status"] != "active":
            raise ValueError(f"transaction {txn_id} is {txn['status']}")
        txn["status"] = "committed"
        txn["updated_at"] = self._now()
        self._save(self._txns())
        return {
            "txn_id": txn_id,
            "status": "committed",
            "ops_committed": len(txn["ops"]),
            "keys_touched": len(txn["preimages"]),
        }

    def status(self, txn_id):
        txn = self._get_txn(txn_id)
        return {
            "txn_id": txn_id,
            "label": txn["label"],
            "status": txn["status"],
            "ops": len(txn["ops"]),
            "keys_touched": len(txn["preimages"]),
        }


__all__ = ["TransactionManager"]