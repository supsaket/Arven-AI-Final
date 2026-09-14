"""Supply Chain & Inventory — Feature 96.

``InventoryManager`` is a plain class (not a Provider) persisted on a
KeyValueStore. Everything is user-entered: items, costs, minimums,
suppliers and BOMs. No external sync exists and none is faked.

Rules enforced here:
- ``receive``/``issue`` do real ledger math with audit entries.
- issuing below zero is refused (stock can never go negative).
- stock adjustments that are large or correcting (reducing) require an
  explicit confirmation flag.
- ``stock_value`` and ``bom_breakdown`` are real arithmetic over stored
  user data.
- every mutating call returns an honest ok/reject (from
  ``core.providers.base``); nothing is fabricated.
"""

from datetime import datetime

from core.kv import KeyValueStore
from core.providers.base import (
    STATUS_UNAVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_REQUIRES_PERMISSION,
    STATUS_FAILED,
    ok,
    reject,
)

from core.confirmation import CONFIRMATION


def _money(value):
    return round(float(value), 2)


def _confirm_gate(confirmed, trusted=False, request_id=None, destructive=False):
    """Honest explicit-confirmation gate (contract shared with the providers)."""
    if not confirmed:
        return False, "requires confirmation"
    if destructive:
        if not (trusted and request_id):
            return False, "destructive action requires a trusted, confirmed request id"
        if not CONFIRMATION.is_pending_ok(request_id):
            return False, "confirmation request is not pending (unknown or expired)"
        return True, "confirmed"
    if trusted:
        return True, "trusted and confirmed"
    if request_id:
        if not CONFIRMATION.is_pending_ok(request_id):
            return False, "confirmation request is not pending (unknown or expired)"
        return True, "confirmed"
    return True, "confirmed"


class InventoryManager:
    """KV-persisted inventory ledger with real receive/issue math."""

    name = "inventory"
    category = "supply-chain"

    def __init__(self, path=None, adjust_threshold=10):
        self._kv = KeyValueStore(path or "data/inventory.json")
        self.adjust_threshold = float(adjust_threshold)

    # ------------------------------------------------------------------
    # KV helpers
    # ------------------------------------------------------------------
    def _items(self):
        raw = self._kv.get("items", {})
        return raw if isinstance(raw, dict) else {}

    def _save_items(self, items):
        self._kv.set("items", items)

    def _save_log(self, entries):
        self._kv.set("log", entries)

    def audit_log(self):
        """Full adjustment ledger — every change is recorded."""
        return self._kv.get("log", [])

    def _append_log(self, entry):
        current = self.audit_log()
        if not isinstance(current, list):
            current = []
        current.append(entry)
        self._save_log(current)

    def _suppliers(self):
        raw = self._kv.get("suppliers", {})
        return raw if isinstance(raw, dict) else {}

    def _save_suppliers(self, suppliers):
        self._kv.set("suppliers", suppliers)

    def _bom(self):
        raw = self._kv.get("bom", {})
        return raw if isinstance(raw, dict) else {}

    def _save_bom(self, bom):
        self._kv.set("bom", bom)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def add_item(self, sku, name, qty=0, min_qty=0, cost=0.0, location=""):
        sku = str(sku).strip().upper()
        if not sku:
            return reject(STATUS_FAILED, "sku is required")
        items = self._items()
        if sku in items:
            return reject(STATUS_UNAVAILABLE, f"sku already registered: {sku}")
        item = {
            "sku": sku,
            "name": str(name or sku),
            "qty": round(float(qty or 0), 2),
            "min_qty": round(float(min_qty or 0), 2),
            "cost": _money(cost or 0),
            "location": str(location or ""),
        }
        items[sku] = item
        self._save_items(items)
        self._append_log({
            "ts": datetime.now().isoformat(),
            "sku": sku,
            "delta": item["qty"],
            "reason": "registration",
            "ref": "initial stock",
            "after": item["qty"],
        })
        return ok("item registered", data={"item": item})

    def list_items(self):
        items = self._items()
        return ok("inventory items",
                  data={"items": [items[s] for s in sorted(items)],
                        "item_count": len(items)})

    # ------------------------------------------------------------------
    # Ledger ops — real math, audited
    # ------------------------------------------------------------------
    def receive(self, sku, qty, ref=""):
        sku = str(sku or "").strip().upper()
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            return reject(STATUS_FAILED, "qty must be a number")
        if qty <= 0:
            return reject(STATUS_UNAVAILABLE, "receive quantity must be positive")
        items = self._items()
        if sku not in items:
            return reject(STATUS_NOT_CONFIGURED, f"item not registered: {sku}")
        items[sku]["qty"] = round(items[sku]["qty"] + qty, 2)
        self._save_items(items)
        after = items[sku]["qty"]
        self._append_log({
            "ts": datetime.now().isoformat(),
            "sku": sku,
            "delta": qty,
            "reason": "receive",
            "ref": str(ref or ""),
            "after": after,
        })
        return ok("stock received",
                  data={"sku": sku, "qty": qty, "on_hand": after, "ref": ref})

    def issue(self, sku, qty, ref=""):
        sku = str(sku or "").strip().upper()
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            return reject(STATUS_FAILED, "qty must be a number")
        if qty < 0:
            return reject(STATUS_UNAVAILABLE, "issue quantity cannot be negative")
        items = self._items()
        if sku not in items:
            return reject(STATUS_NOT_CONFIGURED, f"item not registered: {sku}")
        on_hand = items[sku]["qty"]
        if qty > on_hand:
            return reject(
                STATUS_UNAVAILABLE,
                f"insufficient stock: on_hand={on_hand} < requested={qty}",
                data={"sku": sku, "requested": qty, "on_hand": on_hand,
                      "issued": False})
        items[sku]["qty"] = round(on_hand - qty, 2)
        self._save_items(items)
        after = items[sku]["qty"]
        self._append_log({
            "ts": datetime.now().isoformat(),
            "sku": sku,
            "delta": -qty,
            "reason": "issue",
            "ref": str(ref or ""),
            "after": after,
        })
        return ok("stock issued",
                  data={"sku": sku, "qty": qty, "on_hand": after, "ref": ref})

    def adjust(self, sku, delta, reason, confirmed=False, trusted=False,
               request_id=None):
        """Adjust stock up/down. Large or correcting (negative) adjustments
        require an explicit confirmation flag."""
        sku = str(sku or "").strip().upper()
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            return reject(STATUS_FAILED, "delta must be a number")
        items = self._items()
        if sku not in items:
            return reject(STATUS_NOT_CONFIGURED, f"item not registered: {sku}")
        requires = (delta < 0) or (abs(delta) > self.adjust_threshold)
        if requires:
            allowed, why = _confirm_gate(confirmed, trusted, request_id,
                                         destructive=(delta < 0))
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"stock adjustment requires confirmation: {why}",
                    data={"sku": sku, "delta": delta, "reason": reason,
                          "threshold": self.adjust_threshold},
                    requires_confirmation=True,
                )
        new_qty = round(items[sku]["qty"] + delta, 2)
        if new_qty < 0:
            return reject(STATUS_UNAVAILABLE,
                          f"adjustment would drive stock below zero",
                          data={"sku": sku, "delta": delta, "projected": new_qty,
                                "on_hand": items[sku]["qty"]})
        items[sku]["qty"] = new_qty
        self._save_items(items)
        self._append_log({
            "ts": datetime.now().isoformat(),
            "sku": sku,
            "delta": delta,
            "reason": str(reason or "adjustment"),
            "ref": "adjustment",
            "after": new_qty,
            "confirmed": bool(requires),
        })
        return ok("stock adjusted",
                  data={"sku": sku, "delta": delta, "on_hand": new_qty,
                        "reason": reason})

    # ------------------------------------------------------------------
    # Reorder suggestions
    # ------------------------------------------------------------------
    def _min_order_for(self, sku):
        orders = []
        for supplier in self._suppliers().values():
            if sku in (s.upper() for s in supplier.get("items", [])):
                orders.append(float(supplier.get("min_order", 0) or 0))
        return max(orders) if orders else 0.0

    def reorder_suggestions(self):
        items = self._items()
        suggestions = []
        for sku in sorted(items):
            item = items[sku]
            if item["qty"] <= item["min_qty"] and item["min_qty"] > 0:
                min_order = self._min_order_for(sku)
                suggested = max(item["min_qty"] * 2 - item["qty"], min_order)
                suggestions.append({
                    "sku": sku,
                    "name": item["name"],
                    "on_hand": item["qty"],
                    "min_qty": item["min_qty"],
                    "min_order": min_order,
                    "suggested_qty": round(suggested, 2),
                })
        return ok("reorder suggestions",
                  data={"suggestions": suggestions,
                        "suggestion_count": len(suggestions)})

    # ------------------------------------------------------------------
    # Valuation / BOM — pure arithmetic over stored user data
    # ------------------------------------------------------------------
    def stock_value(self):
        items = self._items()
        total = 0.0
        rows = []
        for sku in sorted(items):
            item = items[sku]
            value = _money(item["qty"] * item["cost"])
            total += value
            rows.append({"sku": sku, "name": item["name"],
                         "qty": item["qty"], "cost": item["cost"],
                         "value": value})
        return ok("stock value",
                  data={"stock_value": _money(total), "items": rows,
                        "item_count": len(rows)})

    def set_bom(self, product, components):
        product = str(product or "").strip().upper()
        if not product:
            return reject(STATUS_FAILED, "product is required")
        if not isinstance(components, dict) or not components:
            return reject(STATUS_FAILED, "components must be a non-empty {sku: qty} dict")
        bom = self._bom()
        normalized = {str(sku).strip().upper(): _money(qty)
                      for sku, qty in components.items()}
        bom[product] = normalized
        self._save_bom(bom)
        return ok("BOM set", data={"product": product, "components": normalized})

    def bom_breakdown(self, product):
        product = str(product or "").strip().upper()
        bom = self._bom()
        if not product or product not in bom:
            return reject(STATUS_NOT_CONFIGURED, f"no BOM for product: {product}")
        items = self._items()
        components = []
        total_cost = 0.0
        for sku, qty in sorted(bom[product].items()):
            item = items.get(sku)
            cost = item["cost"] if item else 0.0
            total_cost += float(qty) * float(cost)
            components.append({
                "sku": sku,
                "qty": qty,
                "name": item["name"] if item else None,
                "on_hand": item["qty"] if item else 0.0,
                "unit_cost": cost if item else None,
                "line_cost": _money(float(qty) * float(cost)) if item else None,
            })
        return ok("BOM breakdown",
                  data={"product": product, "components": components,
                        "total_component_cost": _money(total_cost)})

    # ------------------------------------------------------------------
    # Suppliers registry (user-entered)
    # ------------------------------------------------------------------
    def add_supplier(self, supplier_id, name, items=None, lead_time_days=0,
                     min_order=0.0):
        supplier_id = str(supplier_id or "").strip().upper()
        if not supplier_id:
            return reject(STATUS_FAILED, "supplier_id is required")
        suppliers = self._suppliers()
        if supplier_id in suppliers:
            return reject(STATUS_UNAVAILABLE,
                          f"supplier already registered: {supplier_id}")
        suppliers[supplier_id] = {
            "id": supplier_id,
            "name": str(name or supplier_id),
            "items": sorted({str(i).strip().upper() for i in (items or [])}),
            "lead_time_days": int(lead_time_days or 0),
            "min_order": _money(min_order or 0),
        }
        self._save_suppliers(suppliers)
        return ok("supplier registered",
                  data={"supplier": suppliers[supplier_id]})

    def list_suppliers(self):
        suppliers = self._suppliers()
        return ok("suppliers",
                  data={"suppliers": [suppliers[s] for s in sorted(suppliers)],
                        "supplier_count": len(suppliers)})

    # ------------------------------------------------------------------
    # Status snapshot
    # ------------------------------------------------------------------
    def status(self):
        items = self._items()
        suggestion_result = self.reorder_suggestions()
        suggestions = suggestion_result["data"]["suggestions"]
        on_hand = sum(i["qty"] for i in items.values())
        return ok("inventory status",
                  data={
                      "item_count": len(items),
                      "skus": sorted(items),
                      "total_units_on_hand": _money(on_hand),
                      "stock_value": _money(sum(i["qty"] * i["cost"] for i in items.values())),
                      "low_stock_items": len(suggestions),
                      "supplier_count": len(self._suppliers()),
                      "bom_count": len(self._bom()),
                      "audit_entries": len(self.audit_log()),
                      "external_sync": False,
                  })


# Module-level singleton (lazy — never touches disk until written).
inventory_manager = InventoryManager()

__all__ = ["InventoryManager", "inventory_manager"]