"""ShoppingProvider — Feature 85 (Smart Shopping).

Capabilities:
- shopping_list
- shopping_price_memo
- shopping_compare
- shopping_purchase

Shopping lists, item categories, priorities and the price memo are REAL
user-entered data persisted in a KeyValueStore. Comparison tables build on
real arithmetic over user-entered prices. Purchases are confirm-gated and
NEVER executed without a configured commerce provider — with none configured
the capability reports NOT_CONFIGURED honestly.
"""

import time
from datetime import datetime

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_REQUIRES_PERMISSION,
    STATUS_FAILED,
    ok,
    reject,
)

# ----------------------------------------------------------------------
# Item name -> category heuristics (real, deterministic)
# ----------------------------------------------------------------------
_ITEM_KEYWORDS = {
    "produce": [
        "apple", "banana", "orange", "lettuce", "tomato", "onion", "potato",
        "avocado", "cucumber", "carrot", "broccoli", "pepper", "berry",
        "vegetable", "fruit",
    ],
    "dairy": ["milk", "cheese", "yogurt", "butter", "cream", "egg"],
    "meat": ["chicken", "beef", "pork", "fish", "salmon", "turkey", "meat",
             "steak", "bacon"],
    "bakery": ["bread", "bagel", "bun", "pastry", "cake", "croissant",
               "muffin"],
    "pantry": ["rice", "pasta", "flour", "sugar", "salt", "spice", "cereal",
               "oil", "sauce", "beans", "canned", "snack", "oats"],
    "beverages": ["water", "juice", "soda", "tea", "coffee", "beer", "wine"],
    "household": ["cleaner", "detergent", "soap", "towel", "paper", "duster",
                  "sponge", "trash", "bag"],
    "personal": ["shampoo", "toothpaste", "toothbrush", "deodorant", "lotion",
                 "razor"],
    "electronics": ["charger", "cable", "battery", "headphone", "phone case",
                    "keyboard", "mouse"],
}

_PRIORITIES = ("high", "normal", "low")


def _money(value):
    return round(float(value), 2)


def _confirm_gate(confirmed, trusted=False, request_id=None, destructive=False):
    """Honest explicit-confirmation gate (shared contract with finance)."""
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


def categorize_item(name=""):
    text = str(name or "").lower()
    for category, keywords in _ITEM_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return category
    return "other"


class ShoppingProvider(Provider):
    name = "shopping"
    capabilities = (
        "shopping_list",
        "shopping_price_memo",
        "shopping_compare",
        "shopping_purchase",
    )
    category = "shopping"
    requires_network = False
    confirm_capabilities = (
        "shopping_purchase",
        "shopping_list_item_remove",
        "shopping_price_memo_remove",
    )

    def __init__(self, settings=None, kv_path=None, commerce_provider=None):
        super().__init__(settings)
        self._kv = KeyValueStore(kv_path or "data/shopping.json")
        self.commerce_provider = commerce_provider

    # Pass-through execute: confirmation kwargs reach the gated methods,
    # which are the single authority for the confirmation gate.
    def execute(self, capability, **kwargs):
        try:
            target = self.describe_capability(capability)
            method = getattr(self, f"_cap_{target.replace('-', '_')}", None)
            if method is None:
                return self._honest(
                    STATUS_NOT_CONFIGURED,
                    f"{self.name} does not implement capability '{capability}'")
            return method(**kwargs)
        except Exception as exc:
            return self._honest(STATUS_FAILED, f"{self.name} error: {exc}")

    # ------------------------------------------------------------------
    def check(self):
        return self.set_status(
            STATUS_AVAILABLE,
            "local shopping store available (offline-capable)",
            {"store": self._kv.path})

    def _lists(self):
        raw = self._kv.get("lists", {})
        return raw if isinstance(raw, dict) else {}

    def _save_lists(self, lists):
        self._kv.set("lists", lists)

    def _memo(self):
        raw = self._kv.get("price_memo", {})
        return raw if isinstance(raw, dict) else {}

    def _save_memo(self, memo):
        self._kv.set("price_memo", memo)

    def _purchases(self):
        raw = self._kv.get("purchases", [])
        return raw if isinstance(raw, list) else []

    # ------------------------------------------------------------------
    # _cap_shopping_list
    # ------------------------------------------------------------------
    def _cap_shopping_list(self, action="create", list_name=None, name=None,
                           qty=1, priority="normal", confirmed=False,
                           trusted=False, request_id=None, **_kw):
        action = (action or "create").lower()
        if action in ("remove", "toggle", "add") and not list_name:
            return reject(STATUS_FAILED, "list_name is required")
        lists = self._lists()

        if action == "create":
            if not list_name:
                return reject(STATUS_FAILED, "list_name is required")
            if list_name in lists:
                return reject(STATUS_FAILED, f"list already exists: {list_name}")
            lists[list_name] = {
                "name": list_name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "items": [],
            }
            self._save_lists(lists)
            return ok("shopping list created", data={"list": lists[list_name]})

        if action == "add":
            if not name:
                return reject(STATUS_FAILED, "item name is required")
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                return reject(STATUS_FAILED, "qty must be a number")
            if qty <= 0:
                return reject(STATUS_FAILED, "qty must be positive")
            if priority not in _PRIORITIES:
                priority = "normal"
            target = lists.get(list_name)
            if target is None:
                return reject(STATUS_FAILED, f"no such list: {list_name}")
            entry = {
                "id": f"it-{time.time_ns()}",
                "name": str(name).strip(),
                "qty": qty,
                "checked": False,
                "category": categorize_item(name),
                "priority": priority,
            }
            target["items"].append(entry)
            target["updated_at"] = datetime.now().isoformat()
            self._save_lists(lists)
            return ok("item added to shopping list",
                      data={"list_name": list_name, "item": entry})

        if action == "toggle":
            target = lists.get(list_name)
            if target is None:
                return reject(STATUS_FAILED, f"no such list: {list_name}")
            for item in target["items"]:
                if item["name"] == name:
                    item["checked"] = not item["checked"]
                    target["updated_at"] = datetime.now().isoformat()
                    self._save_lists(lists)
                    return ok("item toggled",
                              data={"list_name": list_name, "item": item})
            return reject(STATUS_FAILED, f"no such item: {name}")

        if action == "remove":
            allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                            destructive=False)
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"removing an item requires confirmation: {reason}",
                    data={"list_name": list_name, "item": name},
                    requires_confirmation=True,
                )
            target = lists.get(list_name)
            if target is None:
                return reject(STATUS_FAILED, f"no such list: {list_name}")
            before = len(target["items"])
            target["items"] = [i for i in target["items"] if i["name"] != name]
            if len(target["items"]) == before:
                return reject(STATUS_FAILED, f"no such item: {name}")
            target["updated_at"] = datetime.now().isoformat()
            self._save_lists(lists)
            return ok("item removed from shopping list",
                      data={"list_name": list_name, "item": name})

        if action in ("list", "items"):
            if list_name:
                target = lists.get(list_name)
                if target is None:
                    return reject(STATUS_FAILED, f"no such list: {list_name}")
                return ok("shopping list",
                          data={"list_name": list_name, "items": target["items"],
                                "item_count": len(target["items"])})
            summary = {}
            for lname, entry in lists.items():
                summary[lname] = {
                    "item_count": len(entry["items"]),
                    "checked_count": sum(1 for i in entry["items"] if i["checked"]),
                    "items": entry["items"],
                }
            return ok("shopping lists",
                      data={"lists": summary, "list_count": len(lists)})

        return reject(STATUS_FAILED, f"unknown shopping_list action: {action}")

    # ------------------------------------------------------------------
    # _cap_shopping_price_memo (user-entered prices)
    # ------------------------------------------------------------------
    def _cap_shopping_price_memo(self, action="set", item=None, store=None,
                                 price=None, confirmed=False, trusted=False,
                                 request_id=None, **_kw):
        action = (action or "set").lower()
        memo = self._memo()

        if action in ("set", "add"):
            if not item or not store:
                return reject(STATUS_FAILED, "item and store are required")
            try:
                price = float(price)
            except (TypeError, ValueError):
                return reject(STATUS_FAILED, "price must be a number")
            if price < 0:
                return reject(STATUS_FAILED, "price cannot be negative")
            item = str(item).strip().lower()
            store = str(store).strip()
            memo.setdefault(item, {})[store] = _money(price)
            self._save_memo(memo)
            return ok("price recorded",
                      data={"item": item, "store": store, "price": _money(price)})

        if action == "get":
            if not item:
                return reject(STATUS_FAILED, "item is required")
            item = str(item).strip().lower()
            if item not in memo:
                return ok("no prices recorded",
                          data={"item": item, "prices": {}})
            return ok("prices",
                      data={"item": item, "prices": memo[item]})

        if action == "list":
            if store:
                filtered = {
                    item: {s: p for s, p in prices.items() if s == store}
                    for item, prices in memo.items()
                }
                return ok("price memo",
                          data={"store": store, "memo": filtered,
                                "item_count": len(filtered)})
            return ok("price memo",
                      data={"memo": memo, "item_count": len(memo)})

        if action == "remove":
            allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                            destructive=False)
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"removing a memo price requires confirmation: {reason}",
                    data={"item": item, "store": store},
                    requires_confirmation=True,
                )
            if not item:
                return reject(STATUS_FAILED, "item is required")
            item = str(item).strip().lower()
            if item not in memo:
                return reject(STATUS_FAILED, f"no memo entry for item: {item}")
            if store:
                store = str(store).strip()
                if store not in memo[item]:
                    return reject(STATUS_FAILED,
                                  f"no memo entry for {item} @ {store}")
                del memo[item][store]
                if not memo[item]:
                    del memo[item]
            else:
                del memo[item]
            self._save_memo(memo)
            return ok("price memo entry removed", data={"item": item, "store": store})

        return reject(STATUS_FAILED, f"unknown price_memo action: {action}")

    # ------------------------------------------------------------------
    # _cap_shopping_compare — real arithmetic, cheapest per item
    # ------------------------------------------------------------------
    def _cap_shopping_compare(self, store=None, **_kw):
        memo = self._memo()
        rows = []
        cheapest_by_item = {}
        for item in sorted(memo):
            prices = memo[item]
            if store:
                prices = {s: p for s, p in prices.items() if s == store}
            if not prices:
                continue
            price, best_store = min((p, s) for s, p in prices.items())
            rows.append({
                "item": item,
                "stores": prices,
                "cheapest_store": best_store,
                "price": _money(price),
            })
            cheapest_by_item[item] = {"store": best_store, "price": _money(price)}
        return ok(
            "comparison built from user-entered prices",
            data={
                "item_count": len(rows),
                "rows": rows,
                "cheapest_by_item": cheapest_by_item,
                "market_data": False,
                "source": "user price memo",
            },
        )

    # ------------------------------------------------------------------
    # _cap_shopping_purchase — confirm-gated; never without a commerce
    # provider; never without explicit confirmation.
    # ------------------------------------------------------------------
    def _order_value(self, items):
        memo = self._memo()
        total = 0.0
        for entry in items or []:
            item = str(entry.get("name", "")).strip().lower()
            stores = memo.get(item, {})
            if not stores:
                continue
            price = min(stores.values())
            total += float(entry.get("qty", 1)) * price
        return _money(total)

    def purchase_log(self):
        return list(self._purchases())

    def purchase(self, items=None, store=None, confirmed=False, trusted=False,
                 request_id=None):
        allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                        destructive=False)
        if not allowed:
            return reject(
                STATUS_REQUIRES_PERMISSION,
                f"shopping purchase requires explicit confirmation: {reason}",
                data={"items": items, "purchased": False},
                requires_confirmation=True,
            )
        if self.commerce_provider is None:
            return reject(
                STATUS_NOT_CONFIGURED,
                "no commerce provider configured — a purchase is never executed "
                "without one",
                data={"items": items, "purchased": False, "commerce_provider": None},
                requires_confirmation=True,
            )
        try:
            commerce_result = self.commerce_provider.purchase(items=items, store=store)
        except Exception as exc:
            return reject(STATUS_FAILED,
                          f"commerce provider declined purchase: {exc}",
                          data={"items": items, "purchased": False})
        record = {
            "at": datetime.now().isoformat(),
            "items": items,
            "store": store,
            "order_value": self._order_value(items),
            "commerce_provider": getattr(self.commerce_provider, "name", "commerce"),
            "result": commerce_result,
        }
        self._kv.update("purchases",
                        lambda prev: (prev if isinstance(prev, list) else []) + [record])
        return ok("purchase completed", data={"record": record,
                                              "purchased": True})

    def _cap_shopping_purchase(self, items=None, store=None, confirmed=False,
                               trusted=False, request_id=None, **_kw):
        return self.purchase(items, store, confirmed, trusted, request_id)


# ---- Registration at import time ----
from core.providers.registry import providers_registry  # noqa: E402

if not providers_registry.has("shopping"):
    providers_registry.register(ShoppingProvider())

__all__ = ["ShoppingProvider", "categorize_item", "_PRIORITIES"]