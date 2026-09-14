"""Day 2 — Features 81, 102 (Finance), 85 (Shopping), 96 (Supply Chain),
97 (Service Orchestration).

Every factory takes an explicit path (tempfile). Nothing touches the real
data directory; the only outputs written are under the pytest ``tmp_path``.
Honest statuses are asserted: purchases / deletes / large adjustments /
side-effect service starts are refused without confirmation.
"""

from pathlib import Path

from core.confirmation import CONFIRMATION
from core.providers.finance_provider import FinanceProvider, normalize_category
from core.providers.shopping_provider import ShoppingProvider
from core.services import ServiceOrchestrator
from core.supply_chain import InventoryManager


def pending(action="confirm"):
    """Create a pending confirmation request and return its id."""
    return CONFIRMATION.require(action)


# ----------------------------------------------------------------------
# Finance — transactions, period math, budgets
# ----------------------------------------------------------------------
class TestFinanceTransactions:

    def test_add_transaction_with_category_normalisation(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        result, tx = provider.add_transaction(
            "2026-09-01", 42.5, "expense", note="groceries at supermarket")
        assert result["success"] is True
        assert tx["category"] == "food"
        assert tx["amount"] == 42.5
        assert tx["type"] == "expense"

    def test_normalize_category_heuristics(self):
        assert normalize_category("uber to the airport") == "transport"
        assert normalize_category("monthly rent") == "housing"
        assert normalize_category("salary") == "salary"
        assert normalize_category("random note") == "other"
        assert normalize_category("", "housing") == "housing"

    def test_validation_rejects_bad_inputs(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        result, errors = provider.add_transaction("nonsense", -5, "transfer",
                                                  note="x")
        assert result["success"] is False
        assert any("date" in e for e in errors)
        assert any("amount" in e for e in errors)
        assert any("type" in e for e in errors)

    def test_period_math_and_running_totals(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        provider.add_transaction("2026-09-01", 100, "income", note="salary")
        provider.add_transaction("2026-09-02", 30, "expense", note="groceries")
        provider.add_transaction("2026-09-03", 20, "expense", note="uber")
        result = provider.execute("finance_transaction_list", month="2026-09")
        summary = result["data"]["summary"]
        assert result["success"] is True
        assert summary["income"] == 100
        assert summary["expense"] == 50
        assert summary["net"] == 50
        assert summary["category_breakdown"]["food"]["expense"] == 30
        assert summary["category_breakdown"]["transport"]["expense"] == 20
        assert len(summary["running_totals"]) == 3
        assert summary["running_totals"][-1]["running_net"] == 50

    def test_list_filters_by_category_and_range(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        provider.add_transaction("2026-09-01", 10, "expense", note="coffee")
        provider.add_transaction("2026-09-15", 99, "expense", note="gym")
        result = provider.execute(
            "finance_transaction_list", category="health",
            start_date="2026-09-01", end_date="2026-09-30")
        txs = result["data"]["transactions"]
        assert len(txs) == 1
        assert txs[0]["category"] == "health"

    def test_delete_and_void_require_confirmation(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        _, tx = provider.add_transaction("2026-09-01", 10, "expense",
                                         note="coffee")
        tx_id = tx["id"]

        denied = provider.execute("finance_transaction_delete",
                                  transaction_id=tx_id)
        assert denied["success"] is False
        assert denied["requires_confirmation"] is True

        rid = pending("delete transaction")
        allowed = provider.execute(
            "finance_transaction_delete", transaction_id=tx_id,
            confirmed=True, trusted=True, request_id=rid)
        assert allowed["success"] is True
        listed = provider.execute("finance_transaction_list")
        assert all(t["id"] != tx_id for t in listed["data"]["transactions"])

        _, tx2 = provider.add_transaction("2026-09-02", 5, "expense",
                                          note="water")
        rid2 = pending("void transaction")
        voided = provider.execute(
            "finance_transaction_void", transaction_id=tx2["id"],
            confirmed=True, trusted=True, request_id=rid2)
        assert voided["success"] is True
        listed = provider.execute("finance_transaction_list")
        assert listed["data"]["summary"]["expense"] == 0


class TestFinanceBudgets:

    def test_budget_compliance_overspend_flag(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        provider.execute("finance_budget_set", category="food", limit=100,
                         month="2026-09")
        provider.add_transaction("2026-09-01", 40, "expense",
                                 note="groceries")
        provider.add_transaction("2026-09-10", 80, "expense",
                                 note="restaurant dinner")
        result = provider.execute("finance_budget_status", month="2026-09")
        assert result["success"] is True
        budgets = result["data"]["budgets"]
        assert len(budgets) == 1
        row = budgets[0]
        assert row["category"] == "food"
        assert row["limit"] == 100
        assert row["spend"] == 120
        assert row["variance"] == -20
        assert row["remaining"] == 0
        assert row["overspend"] is True
        assert row["alert"] == "OVER_BUDGET"
        assert result["data"]["overspend_count"] == 1

    def test_budget_ok_when_under_limit(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        provider.execute("finance_budget_set", category="transport", limit=50,
                         month="2026-09")
        provider.add_transaction("2026-09-05", 10, "expense", note="uber")
        result = provider.execute("finance_budget_status", month="2026-09")
        row = result["data"]["budgets"][0]
        assert row["overspend"] is False
        assert row["alert"] == "OK"
        assert row["remaining"] == 40


class TestFinanceReport:

    def test_report_written_to_output_dir(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"),
                                   output_dir=str(tmp_path))
        provider.execute("finance_budget_set", category="food", limit=100,
                         month="2026-09")
        provider.add_transaction("2026-09-01", 200, "income", note="salary")
        provider.add_transaction("2026-09-02", 30, "expense", note="groceries")
        result = provider.execute("finance_report", month="2026-09")
        assert result["success"] is True
        path = Path(result["data"]["path"])
        assert path.exists()
        assert path.parent == Path(tmp_path) / "Output" / "Finance"
        assert Path(result["data"]["sidecar"]).exists()
        content = path.read_text(encoding="utf-8")
        assert "Period totals" in content
        assert "Budget compliance" in content
        assert result["data"]["period_totals"]["net"] == 170


class TestFinanceInvestment:

    def test_watchlist_add_list_remove_gated(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        added = provider.execute("finance_investment_watchlist",
                                 action="add", symbol="AAPL")
        assert added["success"] is True
        listed = provider.execute("finance_investment_watchlist",
                                  action="list")
        assert listed["data"]["watchlist"] == ["AAPL"]

        denied = provider.execute("finance_investment_watchlist",
                                  action="remove", symbol="AAPL")
        assert denied["success"] is False
        assert denied["requires_confirmation"] is True

        removed = provider.execute("finance_investment_watchlist",
                                   action="remove", symbol="AAPL",
                                   confirmed=True)
        assert removed["success"] is True
        assert removed["data"]["watchlist"] == []

    def test_portfolio_user_entered_values_no_market_data(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        added = provider.execute(
            "finance_portfolio", action="add", symbol="AAPL", shares=10,
            cost_per_share=150, price=160)
        assert added["success"] is True
        holding = added["data"]["holding"]
        assert holding["cost_per_share"] == 150
        assert holding["price"] == 160

        listed = provider.execute("finance_portfolio", action="list")
        rows = listed["data"]["portfolio"]
        assert listed["data"]["market_data"] is False
        assert listed["data"]["estimate"] is True
        assert rows[0]["cost_basis"] == 1500
        assert rows[0]["current_value"] == 1600
        assert rows[0]["pnl"] == 100
        assert rows[0]["market_data"] is False
        assert rows[0]["estimate"] is True
        assert listed["data"]["aggregate"]["total_cost_basis"] == 1500
        assert listed["data"]["aggregate"]["total_current_value"] == 1600

    def test_live_market_data_is_not_configured(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        result = provider.execute("finance_portfolio", action="list", live=True)
        assert result["success"] is False
        assert result["status"] == "NOT_CONFIGURED"
        assert result["data"]["market_data"] is False

    def test_portfolio_holding_without_price_has_no_fake_value(self, tmp_path):
        provider = FinanceProvider(kv_path=str(tmp_path / "finance.json"))
        provider.execute("finance_portfolio", action="add", symbol="MSFT",
                         shares=5, cost_per_share=300)
        rows = provider.execute("finance_portfolio", action="list")["data"]["portfolio"]
        assert rows[0]["current_value"] is None
        assert rows[0]["pnl"] is None
        assert rows[0]["estimate"] is False


# ----------------------------------------------------------------------
# Shopping — lists, price memo, comparison, purchase gate
# ----------------------------------------------------------------------
class TestShoppingList:

    def test_list_lifecycle(self, tmp_path):
        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
        created = provider.execute("shopping_list", action="create",
                                   list_name="Weekly")
        assert created["success"] is True
        added = provider.execute("shopping_list", action="add",
                                 list_name="Weekly", name="Milk", qty=2)
        assert added["success"] is True
        assert added["data"]["item"]["category"] == "dairy"
        assert added["data"]["item"]["checked"] is False

        toggled = provider.execute("shopping_list", action="toggle",
                                   list_name="Weekly", name="Milk")
        assert toggled["data"]["item"]["checked"] is True

        listed = provider.execute("shopping_list", action="list")
        assert listed["data"]["lists"]["Weekly"]["checked_count"] == 1

    def test_remove_requires_confirmation(self, tmp_path):
        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
        provider.execute("shopping_list", action="create", list_name="Weekly")
        provider.execute("shopping_list", action="add", list_name="Weekly",
                         name="Bread")
        denied = provider.execute("shopping_list", action="remove",
                                  list_name="Weekly", name="Bread")
        assert denied["success"] is False
        assert denied["requires_confirmation"] is True
        removed = provider.execute("shopping_list", action="remove",
                                   list_name="Weekly", name="Bread",
                                   confirmed=True)
        assert removed["success"] is True
        assert removed["data"]["item"] == "Bread"


class TestPriceMemoCompare:

    def test_price_memo_and_cheapest_per_item(self, tmp_path):
        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
        provider.execute("shopping_price_memo", action="set", item="milk",
                         store="StoreA", price=2.50)
        provider.execute("shopping_price_memo", action="set", item="milk",
                         store="StoreB", price=2.20)
        provider.execute("shopping_price_memo", action="set", item="bread",
                         store="StoreA", price=1.99)
        provider.execute("shopping_price_memo", action="set", item="bread",
                         store="StoreB", price=2.10)

        memo = provider.execute("shopping_price_memo", action="list")
        assert memo["data"]["item_count"] == 2

        comparison = provider.execute("shopping_compare")
        assert comparison["success"] is True
        assert comparison["data"]["market_data"] is False
        asserted = {row["item"]: row for row in comparison["data"]["rows"]}
        assert asserted["milk"]["cheapest_store"] == "StoreB"
        assert asserted["milk"]["price"] == 2.20
        assert asserted["bread"]["cheapest_store"] == "StoreA"
        assert asserted["bread"]["price"] == 1.99

    def test_price_memo_requires_price_and_validates(self, tmp_path):
        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
        missing = provider.execute("shopping_price_memo", action="set",
                                   item="milk", store="StoreA")
        assert missing["success"] is False
        negative = provider.execute("shopping_price_memo", action="set",
                                    item="milk", store="StoreA", price=-1)
        assert negative["success"] is False


class TestShoppingPurchase:

    def test_purchase_refused_without_confirmation(self, tmp_path):
        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
        result = provider.execute("shopping_purchase",
                                  items=[{"name": "Milk", "qty": 1}])
        assert result["success"] is False
        assert result["requires_confirmation"] is True
        assert provider.purchase_log() == []

    def test_purchase_not_configured_without_commerce_provider(self, tmp_path):
        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"))
        result = provider.execute("shopping_purchase",
                                  items=[{"name": "Milk", "qty": 1}],
                                  confirmed=True)
        assert result["success"] is False
        assert result["status"] == "NOT_CONFIGURED"
        assert result["data"]["purchased"] is False
        assert provider.purchase_log() == []

    def test_purchase_executes_with_commerce_provider_and_confirm(self, tmp_path):
        class FakeCommerce:
            name = "fake-commerce"

            def purchase(self, items=None, store=None):
                return {"accepted": True, "items": items, "store": store}

        provider = ShoppingProvider(kv_path=str(tmp_path / "shopping.json"),
                                    commerce_provider=FakeCommerce())
        provider.execute("shopping_price_memo", action="set", item="milk",
                         store="StoreA", price=2.00)
        result = provider.execute(
            "shopping_purchase",
            items=[{"name": "Milk", "qty": 2}], store="StoreA",
            confirmed=True)
        assert result["success"] is True
        assert result["data"]["purchased"] is True
        assert result["data"]["record"]["order_value"] == 4.00
        assert len(provider.purchase_log()) == 1


# ----------------------------------------------------------------------
# Supply chain & inventory
# ----------------------------------------------------------------------
class TestInventory:

    def test_receive_issue_math_and_audit(self, tmp_path):
        inventory = InventoryManager(path=str(tmp_path / "inventory.json"))
        inventory.add_item("SKU-A", "Widget", qty=0, min_qty=5, cost=2.0,
                           location="Shelf-1")
        received = inventory.receive("SKU-A", 10, ref="PO-100")
        assert received["success"] is True
        assert received["data"]["on_hand"] == 10

        issued = inventory.issue("SKU-A", 4, ref="WO-200")
        assert issued["data"]["on_hand"] == 6

        log = inventory.audit_log()
        assert len(log) == 3  # registration + receive + issue
        assert log[1]["reason"] == "receive"
        assert log[1]["ref"] == "PO-100"
        assert log[2]["delta"] == -4

    def test_cannot_issue_below_zero(self, tmp_path):
        inventory = InventoryManager(path=str(tmp_path / "inventory.json"))
        inventory.add_item("SKU-A", "Widget", qty=6, min_qty=0, cost=1.0)
        refused = inventory.issue("SKU-A", 10, ref="WO-300")
        assert refused["success"] is False
        assert refused["status"] == "UNAVAILABLE"
        assert refused["data"]["issued"] is False
        assert inventory.list_items()["data"]["items"][0]["qty"] == 6

    def test_adjustments_require_confirmation(self, tmp_path):
        inventory = InventoryManager(path=str(tmp_path / "inventory.json"))
        inventory.add_item("SKU-A", "Widget", qty=10, min_qty=0, cost=1.0)

        blocked_correction = inventory.adjust("SKU-A", -3, "stock correction")
        assert blocked_correction["success"] is False
        assert blocked_correction["requires_confirmation"] is True
        assert blocked_correction["status"] == "REQUIRES_PERMISSION"

        rid = pending("correct stock")
        correction = inventory.adjust("SKU-A", -3, "stock correction",
                                      confirmed=True, trusted=True,
                                      request_id=rid)
        assert correction["success"] is True
        assert correction["data"]["on_hand"] == 7

        blocked_large = inventory.adjust("SKU-A", 50, "night restock")
        assert blocked_large["success"] is False
        assert blocked_large["requires_confirmation"] is True

        large = inventory.adjust("SKU-A", 50, "night restock", confirmed=True)
        assert large["success"] is True
        assert large["data"]["on_hand"] == 57

    def test_reorder_suggestions(self, tmp_path):
        inventory = InventoryManager(path=str(tmp_path / "inventory.json"))
        inventory.add_item("SKU-A", "Widget", qty=10, min_qty=5, cost=2.0)
        inventory.add_item("SKU-B", "Gadget", qty=4, min_qty=10, cost=3.0)
        inventory.add_supplier("SUP-1", "Acme", items=["SKU-B"],
                               lead_time_days=3, min_order=20)
        result = inventory.reorder_suggestions()
        suggestions = {s["sku"]: s for s in result["data"]["suggestions"]}
        assert result["success"] is True
        assert "SKU-B" in suggestions
        assert suggestions["SKU-B"]["suggested_qty"] == max(20 - 4, 20)
        assert "SKU-A" not in suggestions

    def test_stock_value_and_bom(self, tmp_path):
        inventory = InventoryManager(path=str(tmp_path / "inventory.json"))
        inventory.add_item("SKU-A", "Widget", qty=6, cost=2.0)
        inventory.add_item("SKU-B", "Gadget", qty=4, cost=3.0)
        valuation = inventory.stock_value()
        assert valuation["data"]["stock_value"] == 24

        inventory.set_bom("PROD-A", {"SKU-A": 2, "SKU-B": 3})
        breakdown = inventory.bom_breakdown("PROD-A")
        assert breakdown["success"] is True
        assert breakdown["data"]["total_component_cost"] == 13
        by_sku = {c["sku"]: c for c in breakdown["data"]["components"]}
        assert by_sku["SKU-A"]["line_cost"] == 4
        assert by_sku["SKU-B"]["line_cost"] == 9


# ----------------------------------------------------------------------
# Service orchestration
# ----------------------------------------------------------------------
class TestServiceOrchestrator:

    def test_dependency_order_respects_deps(self, tmp_path):
        orchestrator = ServiceOrchestrator(path=str(tmp_path / "services.json"))
        orchestrator.register_service("db")
        orchestrator.register_service("api", deps=["db"])
        orchestrator.register_service("web", deps=["api"])
        result = orchestrator.dependency_order()
        order = result["data"]["order"]
        assert result["success"] is True
        assert order.index("db") < order.index("api") < order.index("web")

    def test_dependency_cycle_detected(self, tmp_path):
        orchestrator = ServiceOrchestrator(path=str(tmp_path / "cycle.json"))
        orchestrator.register_service("x", deps=["y"])
        orchestrator.register_service("y", deps=["x"])
        result = orchestrator.dependency_order()
        assert result["success"] is False
        assert result["status"] == "FAILED"
        assert set(result["data"]["cycle"]) == {"x", "y"}

    def test_duplicate_registration_rejected(self, tmp_path):
        orchestrator = ServiceOrchestrator(path=str(tmp_path / "services.json"))
        orchestrator.register_service("db")
        duplicate = orchestrator.register_service("db")
        assert duplicate["success"] is False

    def test_start_refused_when_deps_down_degraded_rollup(self, tmp_path):
        orchestrator = ServiceOrchestrator(path=str(tmp_path / "services.json"))
        orchestrator.register_service("db")
        orchestrator.register_service("web", deps=["db"])

        degraded = orchestrator.degraded_detection()
        assert any(d["service"] == "web" and "db" in d["missing_deps"]
                   for d in degraded["data"]["degraded"])

        refused = orchestrator.start_service("web")
        assert refused["success"] is False
        assert refused["status"] == "UNAVAILABLE"
        assert refused["data"]["missing_deps"] == ["db"]
        assert refused["data"]["service"]["status"] == "degraded"

        rollup = orchestrator.health_rollup("web")
        assert rollup["data"]["worst"] == "OFFLINE"

        orchestrator.start_service("db")
        started = orchestrator.start_service("web")
        assert started["success"] is True
        assert started["data"]["service"]["status"] == "running"

        healthy = orchestrator.health_rollup("web")
        assert healthy["data"]["worst"] == "AVAILABLE"
        assert orchestrator.degraded_detection()["data"]["degraded_count"] == 0

    def test_side_effect_service_requires_confirmation(self, tmp_path):
        orchestrator = ServiceOrchestrator(path=str(tmp_path / "services.json"))
        orchestrator.register_service("backup", side_effects=True)
        refused = orchestrator.start_service("backup")
        assert refused["success"] is False
        assert refused["requires_confirmation"] is True
        assert refused["data"]["started"] is False

        started = orchestrator.start_service("backup", confirmed=True)
        assert started["success"] is True
        assert started["data"]["service"]["status"] == "running"
        assert "state machine only" in started["data"]["external_side_effect_note"]

        stop_refused = orchestrator.stop_service("backup")
        assert stop_refused["success"] is False
        stopped = orchestrator.stop_service("backup", confirmed=True)
        assert stopped["success"] is True
        assert stopped["data"]["service"]["status"] == "stopped"

    def test_bottleneck_report(self, tmp_path):
        orchestrator = ServiceOrchestrator(path=str(tmp_path / "bottles.json"))
        orchestrator.register_service("core")
        orchestrator.register_service("svc-a", deps=["core"])
        orchestrator.register_service("svc-b", deps=["core"])
        orchestrator.register_service("leaf", deps=["svc-a"])
        report = orchestrator.bottleneck_report()
        by_service = {b["service"]: b for b in report["data"]["bottlenecks"]}
        assert by_service["core"]["blocked_dependents"] == 3
        assert by_service["svc-a"]["blocked_dependents"] == 1
        assert by_service["core"]["blocked_services"] == ["leaf", "svc-a", "svc-b"]