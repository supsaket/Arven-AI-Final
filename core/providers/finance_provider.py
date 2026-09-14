"""FinanceProvider — Features 81 (Finance & Budget Management) and 102
(Transactions & Investment).

Capabilities:
- finance_status
- finance_transaction_add / finance_transaction_list
- finance_transaction_delete / finance_transaction_void (confirmed only)
- finance_budget_set / finance_budget_status
- finance_report
- finance_investment_watchlist
- finance_portfolio

Everything here is OFFline, REAL local bookkeeping over a KeyValueStore.
No market data is ever fetched and no values are invented: transactions,
budgets, watchlist symbols, cost basis, shares and prices are ALL
user-entered. Live market data is reported NOT_CONFIGURED, honestly.

Security: deleting/voiding a transaction (and removing watchlist/portfolio
entries) requires explicit confirmation — gate only when the
``confirmed``/``trusted``/``request_id`` kwargs are supplied.
"""

import time
from datetime import datetime

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.output import OutputManager, output_manager
from core.providers.base import (
    Provider,
    STATUS_AVAILABLE,
    STATUS_NOT_CONFIGURED,
    STATUS_REQUIRES_PERMISSION,
    STATUS_FAILED,
    ok,
    reject,
)

EXPENSE = "expense"
INCOME = "income"
TYPES = (EXPENSE, INCOME)

# ----------------------------------------------------------------------
# Keyword -> category heuristics (real, deterministic normalisation)
# ----------------------------------------------------------------------
_CATEGORY_KEYWORDS = {
    "housing": [
        "rent", "mortgage", "housing", "utilit", "electric", "water bill",
        "internet", "wifi", "property", "maintenance", "apartment", "home",
    ],
    "food": [
        "grocer", "supermarket", "restaurant", "lunch", "dinner", "breakfast",
        "coffee", "cafe", "takeout", "meal", "food", "snack", "dining",
    ],
    "transport": [
        "transport", "fuel", "petrol", "gasoline", "gas", "uber", "taxi",
        "train", "bus", "parking", "toll", "car payment",
    ],
    "health": [
        "medical", "doctor", "pharmacy", "pharma", "gym", "fitness",
        "hospital", "dentist", "insurance premium",
    ],
    "entertainment": [
        "movie", "cinema", "netflix", "spotify", "music", "game", "concert",
        "stream",
    ],
    "shopping": [
        "shop", "mall", "amazon", "store", "clothing", "retail", "bought",
    ],
    "education": [
        "tuition", "course", "book", "school", "university", "class",
        "training",
    ],
    "salary": ["salary", "paycheck", "wage", "payroll", "bonus"],
    "investment": ["dividend", "interest", "stock", "investment", "bond"],
}

CATEGORIES = tuple(_CATEGORY_KEYWORDS)


def _money(value):
    return round(float(value), 2)


def _confirm_gate(confirmed, trusted=False, request_id=None, destructive=False):
    """Honest explicit-confirmation gate.

    * destructive (delete/void): confirmed AND trusted AND a pending
      request_id that gets consumed (the double lock).
    * high (purchase/remove): ``confirmed`` is required; ``trusted`` or a
      pending ``request_id`` also unlock the action.
    """
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


def normalize_category(note="", category=None):
    """Map free text to a known category. Never invents data — default: other."""
    if category:
        return str(category).strip().lower()
    text = str(note or "").lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return cat
    return "other"


class FinanceProvider(Provider):
    name = "finance"
    capabilities = (
        "finance_status",
        "finance_transaction_add",
        "finance_transaction_list",
        "finance_transaction_delete",
        "finance_transaction_void",
        "finance_budget_set",
        "finance_budget_status",
        "finance_report",
        "finance_investment_watchlist",
        "finance_portfolio",
    )
    category = "finance"
    requires_network = False
    confirm_capabilities = (
        "finance_transaction_delete",
        "finance_transaction_void",
        "finance_watchlist_remove",
        "finance_portfolio_remove",
    )

    def __init__(self, settings=None, kv_path=None, output_dir=None):
        super().__init__(settings)
        self._kv = KeyValueStore(kv_path or "data/finance.json")
        if output_dir:
            self._out = OutputManager(root=output_dir)
        else:
            self._out = output_manager

    # ------------------------------------------------------------------
    # Pass-through execute: confirmation kwargs reach the gated methods,
    # which are the single authority for the confirmation gate.
    # ------------------------------------------------------------------
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
    # check / status
    # ------------------------------------------------------------------
    def check(self):
        return self.set_status(
            STATUS_AVAILABLE,
            "local finance ledger available (offline-capable)",
            {"store": self._kv.path},
        )

    def _transactions(self):
        raw = self._kv.get("transactions", [])
        return raw if isinstance(raw, list) else []

    def _save_transactions(self, transactions):
        self._kv.set("transactions", transactions)

    def _budgets(self):
        raw = self._kv.get("budgets", {})
        return raw if isinstance(raw, dict) else {}

    def _save_budgets(self, budgets):
        self._kv.set("budgets", budgets)

    def _watchlist(self):
        raw = self._kv.get("watchlist", [])
        return raw if isinstance(raw, list) else []

    def _save_watchlist(self, symbols):
        self._kv.set("watchlist", symbols)

    def _portfolio(self):
        raw = self._kv.get("portfolio", [])
        return raw if isinstance(raw, list) else []

    def _save_portfolio(self, holdings):
        self._kv.set("portfolio", holdings)

    @staticmethod
    def _month(value=None):
        if value:
            text = str(value).strip()
            if len(text) >= 7:
                return text[:7]
        return datetime.now().strftime("%Y-%m")

    @staticmethod
    def _valid_date(value):
        try:
            datetime.strptime(str(value).strip(), "%Y-%m-%d")
            return True
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # Transaction ledger (real math)
    # ------------------------------------------------------------------
    def validate_transaction(self, date, amount, type_):
        errors = []
        if not date or not self._valid_date(date):
            errors.append(f"invalid date: {date!r} (expected ISO YYYY-MM-DD)")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            errors.append(f"invalid amount: {amount!r}")
            amount = None
        if amount is not None and amount <= 0:
            errors.append("amount must be a positive number")
        if type_ not in TYPES:
            errors.append(f"type must be one of {TYPES}, got {type_!r}")
        return errors, amount

    def add_transaction(self, date, amount, type_, note="", category=None):
        """Real ledger append. Returns (result_dict, transaction_or_errors)."""
        errors, amount = self.validate_transaction(date, amount, type_)
        if errors:
            return reject(
                STATUS_FAILED,
                "invalid transaction",
                data={"errors": errors},
            ), errors
        transaction = {
            "id": f"tx-{time.time_ns()}",
            "date": str(date).strip(),
            "category": normalize_category(note, category),
            "amount": _money(amount),
            "type": type_,
            "note": str(note or "").strip(),
            "created_at": datetime.now().isoformat(),
            "voided": False,
        }
        self._kv.update(
            "transactions",
            lambda prev: (prev if isinstance(prev, list) else []) + [transaction],
        )
        return ok("transaction added", data={"transaction": transaction,
                                             "ledger_count": self._ledger_count()}), transaction

    def _ledger_count(self):
        return len(self._transactions())

    def summaries(self):
        transactions = self._transactions()
        income = sum(t["amount"] for t in transactions
                     if not t.get("voided") and t["type"] == INCOME)
        expense = sum(t["amount"] for t in transactions
                      if not t.get("voided") and t["type"] == EXPENSE)
        return {
            "transaction_count": len(transactions),
            "active_count": sum(1 for t in transactions if not t.get("voided")),
            "income": _money(income),
            "expense": _money(expense),
            "net": _money(income - expense),
        }

    # ------------------------------------------------------------------
    # _cap_finance_status
    # ------------------------------------------------------------------
    def _cap_finance_status(self, **_kw):
        self.check()
        budgets = self._budgets()
        month = self._month()
        data = {
            "status": self.status_code,
            "store": self._kv.path,
            "month": month,
            "monthly_totals": self.period_summary(month=month),
            "budget_count": len(budgets),
            "watchlist_symbols": sorted(s["symbol"] for s in self._watchlist()),
            "portfolio_holdings": len(self._portfolio()),
            "live_market_data": False,
        }
        return ok("finance status", data=data)

    # ------------------------------------------------------------------
    # _cap_finance_transaction_add / list
    # ------------------------------------------------------------------
    def _cap_finance_transaction_add(self, date=None, amount=None, type=None,
                                     note="", category=None, **_kw):
        result, _ = self.add_transaction(date, amount, type, note, category)
        return result

    def _filtered(self, transactions, category=None, month=None,
                  start_date=None, end_date=None):
        out = []
        for t in transactions:
            if t.get("voided"):
                continue
            if category and t.get("category") != category:
                continue
            d = t.get("date", "")
            if month and not d.startswith(month):
                continue
            if start_date and d < start_date:
                continue
            if end_date and d > end_date:
                continue
            out.append(t)
        return out

    def _summarize(self, rows):
        income = _money(sum(t["amount"] for t in rows if t["type"] == INCOME))
        expense = _money(sum(t["amount"] for t in rows if t["type"] == EXPENSE))
        breakdown = {}
        for t in rows:
            bucket = breakdown.setdefault(
                t.get("category", "other"), {"expense": 0.0, "income": 0.0})
            bucket[t["type"]] = _money(bucket[t["type"]] + t["amount"])
        return {
            "transaction_count": len(rows),
            "income": income,
            "expense": expense,
            "net": _money(income - expense),
            "category_breakdown": breakdown,
        }

    def _running_totals(self, rows):
        ordered = sorted(rows, key=lambda r: (r.get("date", ""), r.get("id", "")))
        run = 0.0
        totals = []
        for t in ordered:
            run += t["amount"] if t["type"] == INCOME else -t["amount"]
            totals.append({
                "id": t["id"],
                "date": t["date"],
                "running_net": _money(run),
            })
        return totals

    def period_summary(self, month=None, category=None,
                       start_date=None, end_date=None):
        rows = self._filtered(
            self._transactions(), category, month, start_date, end_date)
        summary = self._summarize(rows)
        summary["running_totals"] = self._running_totals(rows)
        summary["period"] = (month or self._month()) if month else "all-time"
        if start_date or end_date:
            summary["date_range"] = {"start": start_date, "end": end_date}
        return summary

    def _cap_finance_transaction_list(self, category=None, month=None,
                                      start_date=None, end_date=None, **_kw):
        rows = self._filtered(
            self._transactions(), category, month, start_date, end_date)
        summary = self._summarize(rows)
        summary["running_totals"] = self._running_totals(rows)
        summary["period"] = month or ("all-time" if not (start_date or end_date)
                                      else "custom-range")
        data = {
            "transactions": rows,
            "summary": summary,
            "filters": {
                "category": category,
                "month": month,
                "start_date": start_date,
                "end_date": end_date,
            },
        }
        return ok("transactions listed", data=data)

    # ------------------------------------------------------------------
    # Delete / void (confirmed)
    # ------------------------------------------------------------------
    def _find_transaction(self, transaction_id):
        for t in self._transactions():
            if t["id"] == transaction_id:
                return t
        return None

    def delete_transaction(self, transaction_id, confirmed=False, trusted=False,
                           request_id=None):
        allowed, reason = _confirm_gate(
            confirmed, trusted, request_id, destructive=True)
        if not allowed:
            return reject(
                STATUS_REQUIRES_PERMISSION,
                f"deleting a transaction requires confirmation: {reason}",
                data={"transaction_id": transaction_id},
                requires_confirmation=True,
            )
        transactions = self._transactions()
        remaining = [t for t in transactions if t["id"] != transaction_id]
        if len(remaining) == len(transactions):
            return reject(STATUS_FAILED,
                          f"transaction not found: {transaction_id}")
        self._save_transactions(remaining)
        return ok("transaction deleted", data={"transaction_id": transaction_id})

    def void_transaction(self, transaction_id, confirmed=False, trusted=False,
                         request_id=None):
        allowed, reason = _confirm_gate(
            confirmed, trusted, request_id, destructive=True)
        if not allowed:
            return reject(
                STATUS_REQUIRES_PERMISSION,
                f"voiding a transaction requires confirmation: {reason}",
                data={"transaction_id": transaction_id},
                requires_confirmation=True,
            )
        for t in self._transactions():
            if t["id"] == transaction_id:
                t["voided"] = True
                t["voided_at"] = datetime.now().isoformat()
                self._save_transactions(self._transactions())
                return ok("transaction voided", data={"transaction_id": transaction_id})
        return reject(STATUS_FAILED, f"transaction not found: {transaction_id}")

    def _cap_finance_transaction_delete(self, transaction_id=None, confirmed=False,
                                        trusted=False, request_id=None, **_kw):
        return self.delete_transaction(transaction_id, confirmed, trusted, request_id)

    def _cap_finance_transaction_void(self, transaction_id=None, confirmed=False,
                                      trusted=False, request_id=None, **_kw):
        return self.void_transaction(transaction_id, confirmed, trusted, request_id)

    # ------------------------------------------------------------------
    # Budgets (per category monthly limit)
    # ------------------------------------------------------------------
    def set_budget(self, category, limit, month=None, note=""):
        try:
            limit = float(limit)
        except (TypeError, ValueError):
            return reject(STATUS_FAILED, "budget limit must be a number")
        if limit <= 0:
            return reject(STATUS_FAILED, "budget limit must be positive")
        category = normalize_category("", category)
        month = self._month(month)
        budgets = self._budgets()
        budgets[category] = {
            "category": category,
            "month": month,
            "limit": _money(limit),
            "note": str(note or ""),
            "set_at": datetime.now().isoformat(),
        }
        self._save_budgets(budgets)
        return ok("budget set", data={"budget": budgets[category],
                                      "category": category,
                                      "month": month,
                                      "limit": _money(limit)})

    def budget_compliance(self, month=None):
        month = self._month(month)
        budgets = self._budgets()
        transactions = self._transactions()
        rows = []
        for category, budget in sorted(budgets.items()):
            if budget.get("month") != month:
                continue
            limit = _money(budget.get("limit", 0))
            spend = _money(sum(
                t["amount"] for t in transactions
                if not t.get("voided") and t["type"] == EXPENSE
                and t.get("category") == category
                and t.get("date", "").startswith(month)))
            variance = _money(limit - spend)
            overspend = spend > limit
            rows.append({
                "category": category,
                "month": month,
                "limit": limit,
                "spend": spend,
                "variance": variance,
                "remaining": _money(max(0.0, variance)),
                "overspend": overspend,
                "alert": "OVER_BUDGET" if overspend else "OK",
            })
        alerts = [r for r in rows if r["overspend"]]
        return {
            "month": month,
            "budget_count": len(rows),
            "budgets": rows,
            "alerts": alerts,
            "overspend_count": len(alerts),
        }

    def _cap_finance_budget_set(self, category=None, limit=None, month=None,
                                note="", **_kw):
        if not category:
            return reject(STATUS_FAILED, "category is required")
        if limit is None:
            return reject(STATUS_FAILED, "limit is required")
        return self.set_budget(category, limit, month, note)

    def _cap_finance_budget_status(self, month=None, **_kw):
        compliance = self.budget_compliance(month)
        data = {
            "month": compliance["month"],
            "budget_count": compliance["budget_count"],
            "budgets": compliance["budgets"],
            "alerts": compliance["alerts"],
            "overspend_count": compliance["overspend_count"],
        }
        return ok("budget status", data=data)

    # ------------------------------------------------------------------
    # _cap_finance_report — markdown artefact via output_manager
    # ------------------------------------------------------------------
    def _finance_dir(self):
        if self._out is output_manager:
            return "Output/Finance"
        return str(self._out.root / "Output" / "Finance")

    def _cap_finance_report(self, month=None, category=None, **_kw):
        month = self._month(month)
        rows = self._filtered(self._transactions(), category, month=month)
        summary = self._summarize(rows)
        compliance = self.budget_compliance(month)
        ordered = sorted(rows, key=lambda r: r.get("date", ""))
        md = [
            f"# ARVEN Finance Report — {month}",
            "",
            f"Generated {datetime.now().isoformat()}",
            "",
            "## Period totals",
            "",
            f"| Income | Expenses | Net |",
            f"| --- | --- | --- |",
            f"| {summary['income']:.2f} | {summary['expense']:.2f} | {summary['net']:.2f} |",
            "",
            "## Category breakdown",
            "",
            "| Category | Expense | Income |",
            "| --- | --- | --- |",
        ]
        for cat in sorted(summary["category_breakdown"]):
            bucket = summary["category_breakdown"][cat]
            md.append(
                f"| {cat} | {bucket['expense']:.2f} | {bucket['income']:.2f} |")
        md += [
            "",
            "## Budget compliance",
            "",
            "| Category | Limit | Spend | Variance | Status |",
            "| --- | --- | --- | --- | --- |",
        ]
        if compliance["budgets"]:
            for b in compliance["budgets"]:
                md.append(
                    f"| {b['category']} | {b['limit']:.2f} | {b['spend']:.2f} "
                    f"| {b['variance']:.2f} | {b['alert']} |")
        else:
            md.append("| _no budgets set for this month_ |")
        md += ["", "## Transactions", ""]
        if ordered:
            md.append("| Date | Type | Category | Amount | Note |")
            md.append("| --- | --- | --- | --- | --- |")
            for t in ordered:
                md.append(
                    f"| {t['date']} | {t['type']} | {t['category']} "
                    f"| {t['amount']:.2f} | {t.get('note', '')} |")
        else:
            md.append("_no transactions in this period_")
        content = "\n".join(md) + "\n"
        result = self._out.write(
            self._finance_dir(),
            f"finance_report_{month}.md",
            content,
            metadata={
                "feature": "81/102",
                "module": self.name,
                "month": month,
                "period_totals": summary,
                "budget_alerts": compliance["overspend_count"],
            },
        )
        return ok(
            "finance report written",
            data={
                "path": result["path"],
                "sidecar": result["sidecar"],
                "month": month,
                "period_totals": summary,
                "budget_compliance": compliance,
            },
        )

    # ------------------------------------------------------------------
    # Investment watchlist (user-entered symbols only)
    # ------------------------------------------------------------------
    def _cap_finance_investment_watchlist(self, action="add", symbol=None,
                                          confirmed=False, trusted=False,
                                          request_id=None, **_kw):
        action = (action or "add").lower()
        if action == "list":
            symbols = [s["symbol"] for s in self._watchlist()]
            return ok("watchlist",
                      data={"watchlist": symbols, "symbol_count": len(symbols)})
        if not symbol:
            return reject(STATUS_FAILED, "symbol is required")
        symbol = str(symbol).strip().upper()
        if action == "add":
            symbols = self._watchlist()
            if any(s["symbol"] == symbol for s in symbols):
                return ok("symbol already on watchlist",
                          data={"symbol": symbol, "watchlist": [s["symbol"] for s in symbols]})
            symbols.append({
                "symbol": symbol,
                "added_at": datetime.now().isoformat(),
                "source": "user",
            })
            self._save_watchlist(symbols)
            return ok("symbol added to watchlist",
                      data={"symbol": symbol, "watchlist": [s["symbol"] for s in symbols]})
        if action == "remove":
            allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                            destructive=False)
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"removing a watchlist symbol requires confirmation: {reason}",
                    data={"symbol": symbol},
                    requires_confirmation=True,
                )
            remaining = [s for s in self._watchlist() if s["symbol"] != symbol]
            if len(remaining) == len(self._watchlist()):
                return reject(STATUS_FAILED, f"symbol not on watchlist: {symbol}")
            self._save_watchlist(remaining)
            return ok("symbol removed from watchlist",
                      data={"symbol": symbol, "watchlist": [s["symbol"] for s in remaining]})
        return reject(STATUS_FAILED, f"unknown watchlist action: {action}")

    # ------------------------------------------------------------------
    # Portfolio — user-entered cost basis/shares; NO market data.
    # ------------------------------------------------------------------
    def _cap_finance_portfolio(self, action="list", symbol=None, shares=None,
                               cost_per_share=None, price=None,
                               confirmed=False, trusted=False, request_id=None,
                               live=False, **_kw):
        if live:
            return reject(
                STATUS_NOT_CONFIGURED,
                "live market data is not configured — no market feed provider; "
                "portfolio uses only user-entered prices",
                data={"market_data": False, "estimate": False, "live": True},
            )
        action = (action or "list").lower()

        def _rows():
            rows = []
            total_cost, total_value, priced = 0.0, 0.0, 0
            for holding in self._portfolio():
                cost = _money(float(holding.get("cost_per_share", 0)) * float(holding.get("shares", 0)))
                p = holding.get("price")
                current = _money(float(p) * float(holding["shares"])) if p is not None else None
                row = {
                    "symbol": holding["symbol"],
                    "shares": float(holding["shares"]),
                    "cost_per_share": _money(float(holding.get("cost_per_share", 0))),
                    "price": _money(p) if p is not None else None,
                    "cost_basis": cost,
                    "current_value": current,
                    "pnl": _money(current - cost) if current is not None else None,
                    "market_data": False,
                    "estimate": p is not None,
                }
                rows.append(row)
                total_cost = _money(total_cost + cost)
                if current is not None:
                    total_value = _money(total_value + current)
                    priced += 1
            agg = {
                "total_cost_basis": total_cost,
                "total_current_value": total_value if priced else None,
                "priced_holdings": priced,
                "holding_count": len(rows),
                "unrealized_pnl": _money(total_value - total_cost) if priced else None,
            }
            return rows, agg

        if action == "add":
            if not symbol:
                return reject(STATUS_FAILED, "symbol is required")
            errors = []
            try:
                shares = float(shares)
            except (TypeError, ValueError):
                errors.append("shares must be a number")
            try:
                cost_per_share = float(cost_per_share)
            except (TypeError, ValueError):
                errors.append("cost_per_share must be a number")
            if errors:
                return reject(STATUS_FAILED, "invalid portfolio holding", data={"errors": errors})
            if shares <= 0:
                return reject(STATUS_FAILED, "shares must be positive")
            if cost_per_share < 0:
                return reject(STATUS_FAILED, "cost_per_share cannot be negative")
            if price is not None:
                try:
                    price = float(price)
                except (TypeError, ValueError):
                    return reject(STATUS_FAILED, "price must be a number")
            holding = {
                "symbol": str(symbol).strip().upper(),
                "shares": shares,
                "cost_per_share": _money(cost_per_share),
                "price": _money(price) if price is not None else None,
                "added_at": datetime.now().isoformat(),
                "source": "user",
            }
            holdings = self._portfolio()
            holdings = [h for h in holdings if h["symbol"] != holding["symbol"]]
            holdings.append(holding)
            self._save_portfolio(holdings)
            rows, agg = _rows()
            return ok("portfolio holding added",
                      data={"holding": holding, "portfolio": rows, "aggregate": agg})
        if action == "list":
            rows, agg = _rows()
            return ok("portfolio (user-entered values; no market data)",
                      data={"portfolio": rows, "aggregate": agg,
                            "market_data": False, "estimate": True})
        if action == "remove":
            allowed, reason = _confirm_gate(confirmed, trusted, request_id,
                                            destructive=False)
            if not allowed:
                return reject(
                    STATUS_REQUIRES_PERMISSION,
                    f"removing a portfolio holding requires confirmation: {reason}",
                    data={"symbol": symbol},
                    requires_confirmation=True,
                )
            if not symbol:
                return reject(STATUS_FAILED, "symbol is required")
            holding = str(symbol).strip().upper()
            remaining = [h for h in self._portfolio() if h["symbol"] != holding]
            if len(remaining) == len(self._portfolio()):
                return reject(STATUS_FAILED, f"no holding for symbol: {holding}")
            self._save_portfolio(remaining)
            rows, agg = _rows()
            return ok("portfolio holding removed",
                      data={"symbol": holding, "portfolio": rows, "aggregate": agg})
        return reject(STATUS_FAILED, f"unknown portfolio action: {action}")


# ---- Registration at import time ----
from core.providers.registry import providers_registry  # noqa: E402

if not providers_registry.has("finance"):
    providers_registry.register(FinanceProvider())

__all__ = ["FinanceProvider", "normalize_category", "CATEGORIES", "TYPES"]