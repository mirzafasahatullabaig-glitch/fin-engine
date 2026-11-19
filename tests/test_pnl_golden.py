"""Golden P&L tests.

Examples A and B are taken verbatim from report §7.3. These are exactly the
cases where Granite 4.2 8B returned PBT = EBIT and ignored interest expense
(§7.1). The engine must return the corrected values 115,000 and 190,000.
"""

from decimal import Decimal

from fin_engine import calculate_pnl
from fin_engine.models import AccountGroup, Ledger, LedgerLine


def _line(group, amount):
    return LedgerLine(group=group, amount=amount)


def test_report_example_a_revenue_500k():
    """Report §7.3 Example A — the model wrongly said PBT = 120,000."""
    ledger = Ledger(
        entity="demo",
        period="2026-11",
        lines=[
            _line(AccountGroup.REVENUE, "500000"),
            _line(AccountGroup.COGS, "280000"),
            _line(AccountGroup.OPERATING_EXPENSE, "30000"),   # rent
            _line(AccountGroup.OPERATING_EXPENSE, "60000"),   # salaries
            _line(AccountGroup.OPERATING_EXPENSE, "10000"),   # utilities
            _line(AccountGroup.FINANCE_COST, "5000"),         # interest
        ],
    )
    pnl = calculate_pnl(ledger)
    assert pnl.gross_profit == Decimal("220000")
    assert pnl.operating_expenses == Decimal("100000")
    assert pnl.ebit == Decimal("120000")
    # The correction: PBT must subtract interest, not equal EBIT.
    assert pnl.pbt == Decimal("115000")
    assert pnl.net_profit == Decimal("115000")  # no tax line supplied


def test_report_example_b_revenue_800k():
    """Report §7.3 Example B — the model wrongly said PBT = 200,000."""
    ledger = Ledger(
        entity="demo",
        period="2026-11",
        lines=[
            _line(AccountGroup.REVENUE, "800000"),
            _line(AccountGroup.COGS, "420000"),
            _line(AccountGroup.OPERATING_EXPENSE, "40000"),    # rent
            _line(AccountGroup.OPERATING_EXPENSE, "100000"),   # salaries
            _line(AccountGroup.OPERATING_EXPENSE, "15000"),    # utilities
            _line(AccountGroup.OPERATING_EXPENSE, "25000"),    # marketing
            _line(AccountGroup.FINANCE_COST, "10000"),         # interest
        ],
    )
    pnl = calculate_pnl(ledger)
    assert pnl.gross_profit == Decimal("380000")
    assert pnl.operating_expenses == Decimal("180000")
    assert pnl.ebit == Decimal("200000")
    assert pnl.pbt == Decimal("190000")


def test_example_b_margins():
    """Report §7.3 states 47.50% / 25.00% / 23.75% gross/op/PBT margins."""
    ledger = Ledger(
        entity="demo",
        period="2026-11",
        lines=[
            LedgerLine(AccountGroup.REVENUE, "800000"),
            LedgerLine(AccountGroup.COGS, "420000"),
            LedgerLine(AccountGroup.OPERATING_EXPENSE, "180000"),
            LedgerLine(AccountGroup.FINANCE_COST, "10000"),
        ],
    )
    m = calculate_pnl(ledger).margins()
    assert m["gross"] == Decimal("0.475")
    assert m["operating"] == Decimal("0.25")
    assert m["pbt"] == Decimal("0.2375")


def test_tax_reduces_net_profit():
    ledger = Ledger(
        entity="demo",
        period="2026-11",
        lines=[
            LedgerLine(AccountGroup.REVENUE, "1000"),
            LedgerLine(AccountGroup.COGS, "400"),
            LedgerLine(AccountGroup.OPERATING_EXPENSE, "200"),
            LedgerLine(AccountGroup.FINANCE_COST, "100"),
            LedgerLine(AccountGroup.TAX, "60"),
        ],
    )
    pnl = calculate_pnl(ledger)
    assert pnl.ebit == Decimal("400")
    assert pnl.pbt == Decimal("300")
    assert pnl.net_profit == Decimal("240")


def test_other_income_increases_pbt():
    ledger = Ledger(
        entity="demo",
        period="2026-11",
        lines=[
            LedgerLine(AccountGroup.REVENUE, "1000"),
            LedgerLine(AccountGroup.COGS, "600"),
            LedgerLine(AccountGroup.OTHER_INCOME, "50"),   # e.g. interest earned
        ],
    )
    pnl = calculate_pnl(ledger)
    assert pnl.ebit == Decimal("400")
    assert pnl.pbt == Decimal("450")


def test_empty_ledger_is_all_zero_not_error():
    pnl = calculate_pnl(Ledger(entity="demo", period="2026-11", lines=[]))
    assert pnl.revenue == pnl.pbt == pnl.net_profit == Decimal("0")
    assert pnl.margins()["gross"] == Decimal("0")
