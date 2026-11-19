"""Phase 5 router tests (prompt 9.5): metric-specific routing.

Verifies the router runs the CORRECT deterministic calculation and never
substitutes P&L for a balance-sheet metric. Uses the self-balancing sample
company from test_statements (reconstructed here) and a fake KB-A.
"""

from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.models import AccountGroup
from fin_engine.router import Metric, QueryRouter, detect_metric


class _FakeKB:
    def answer(self, q):
        from fin_engine.rag.pipeline import Answer
        return Answer(text="(reference)", sources=[], grounded=False)


def _company():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("1200", "Inventory", AccountGroup.ASSET))
    coa.add(Account("2000", "Accounts Payable", AccountGroup.LIABILITY))
    coa.add(Account("3000", "Owner's Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE, current=False))
    j = Journal(entity="demo", chart=coa)
    # Capital 10000, sale 6000, buy inventory 3000 on credit (AP), rent 800.
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "10000"), Posting("3000", "-10000")]))
    j.post(JournalEntry("E1", "2026-11-02", "sale",
                        [Posting("1000", "6000"), Posting("4000", "-6000")]))
    j.post(JournalEntry("E2", "2026-11-03", "inventory on credit",
                        [Posting("1200", "3000"), Posting("2000", "-3000")]))
    j.post(JournalEntry("E3", "2026-11-04", "rent",
                        [Posting("6100", "800"), Posting("1000", "-800")]))
    return j, coa


def _router():
    j, coa = _company()
    return QueryRouter(
        kb_a=_FakeKB(),
        accounting_provider=lambda: (j, coa, "2026-11", "2026-11-30"),
    )


# Hand-calc as of 2026-11-30:
#   Cash 10000+6000-800 = 15200; Inventory 3000; current assets = 18200
#   AP (current liab) = 3000
#   Working capital = 18200 - 3000 = 15200
#   Current ratio = 18200/3000 = 6.0666...; Quick = (18200-3000)/3000 = 5.0666...
#   Revenue = 6000; Net profit = 6000 - 800 = 5200
#   Equity = 10000 + 5200 = 15200; Total assets = 18200


def test_detect_metric_specificity():
    assert detect_metric("what is our gross profit?") is Metric.GROSS_PROFIT
    assert detect_metric("is our working capital healthy?") is Metric.WORKING_CAPITAL
    assert detect_metric("calculate our current ratio") is Metric.CURRENT_RATIO


def test_working_capital_uses_balance_sheet_not_pnl():
    r = _router().ask("is our working capital healthy?")
    assert r.metric is Metric.WORKING_CAPITAL
    assert r.value == Decimal("15200")
    assert r.bs is not None       # computed from the balance sheet
    assert r.pnl is None          # NOT substituted with P&L


def test_current_ratio():
    r = _router().ask("calculate our current ratio")
    assert r.metric is Metric.CURRENT_RATIO
    assert r.value == Decimal("18200") / Decimal("3000")
    assert r.bs is not None


def test_quick_ratio_excludes_inventory():
    r = _router().ask("what is our quick ratio?")
    assert r.metric is Metric.QUICK_RATIO
    assert r.value == Decimal("15200") / Decimal("3000")


def test_total_assets():
    r = _router().ask("show our total assets")
    assert r.metric is Metric.TOTAL_ASSETS
    assert r.value == Decimal("18200")


def test_revenue_uses_pnl():
    r = _router().ask("show our revenue")
    assert r.metric is Metric.REVENUE
    assert r.value == Decimal("6000")
    assert r.pnl is not None
    assert r.bs is None


def test_pbt_metric():
    r = _router().ask("what is our pbt this month?")
    assert r.metric is Metric.PBT
    assert r.value == Decimal("5200")   # 6000 - 800, no finance/tax


def test_no_data_reports_gap_not_invented():
    r = QueryRouter(kb_a=_FakeKB()).ask("what is our working capital?")
    assert r.value is None
    assert "No business records" in r.answer
