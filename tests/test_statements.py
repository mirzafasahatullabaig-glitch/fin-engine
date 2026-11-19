"""Journal-derived statement tests (prompt 9.4).

A complete, self-balancing sample company, hand-calculated. The SAME journal
must produce a correct trial balance, P&L and balance sheet (prompt final
mission). Expected values are computed by hand in the comments.

Opening the business (2026-11-01):
  E0  owner injects 10,000 cash:   Dr Cash 10000 / Cr Owner's Equity 10000
Trading in November:
  E1  cash sale 6,000:             Dr Cash 6000  / Cr Sales 6000
  E2  buy inventory 2,500 cash:    Dr Inventory 2500 / Cr Cash 2500
  E3  COGS on goods sold 1,500:    Dr COGS 1500  / Cr Inventory 1500
  E4  pay rent 800 cash:           Dr Rent 800   / Cr Cash 800
  E5  interest on loan 200 cash:   Dr Finance Costs 200 / Cr Cash 200

Hand-calculated P&L for 2026-11 (no tax, no other income):
  Revenue           6000
  COGS              1500
  Gross profit      4500
  Operating exp      800  (rent)
  EBIT              3700
  Finance costs      200
  PBT               3500
  Net profit        3500

Hand-calculated balances as of 2026-11-30 (normal-balance-positive):
  Cash:      10000 +6000 -2500 -800 -200 = 12500
  Inventory:  2500 -1500                 = 1000
  Owner's Equity:                        = 10000
  Retained earnings (net profit folded): = 3500
Balance sheet:
  Current assets   = Cash 12500 + Inventory 1000 = 13500
  Non-current      = 0
  Total assets     = 13500
  Liabilities      = 0
  Equity           = 10000 + 3500 (net profit) = 13500
  => Assets 13500 == Liab 0 + Equity 13500. Balances.
  Working capital  = 13500 - 0 = 13500
  Current ratio    = n/a (no current liabilities) -> None
"""

from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.models import AccountGroup
from fin_engine.statements import balance_sheet_from_journal, pnl_from_journal
from fin_engine.ledger_gl import trial_balance


def _company():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("1200", "Inventory", AccountGroup.ASSET))
    coa.add(Account("3000", "Owner's Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    coa.add(Account("5000", "COGS", AccountGroup.COGS, current=False))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE, current=False))
    coa.add(Account("7000", "Finance Costs", AccountGroup.FINANCE_COST, current=False))
    j = Journal(entity="demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "owner capital",
                        [Posting("1000", "10000"), Posting("3000", "-10000")]))
    j.post(JournalEntry("E1", "2026-11-02", "cash sale",
                        [Posting("1000", "6000"), Posting("4000", "-6000")]))
    j.post(JournalEntry("E2", "2026-11-03", "buy inventory",
                        [Posting("1200", "2500"), Posting("1000", "-2500")]))
    j.post(JournalEntry("E3", "2026-11-10", "cogs",
                        [Posting("5000", "1500"), Posting("1200", "-1500")]))
    j.post(JournalEntry("E4", "2026-11-15", "rent",
                        [Posting("6100", "800"), Posting("1000", "-800")]))
    j.post(JournalEntry("E5", "2026-11-20", "loan interest",
                        [Posting("7000", "200"), Posting("1000", "-200")]))
    return j, coa


def test_trial_balance_balances():
    j, coa = _company()
    assert trial_balance(j, coa, as_of="2026-11-30").balanced


def test_pnl_from_journal_matches_hand_calc():
    j, coa = _company()
    pnl = pnl_from_journal(j, coa, period="2026-11",
                           start="2026-11-01", end="2026-11-30")
    assert pnl.revenue == Decimal("6000")
    assert pnl.cogs == Decimal("1500")
    assert pnl.gross_profit == Decimal("4500")
    assert pnl.operating_expenses == Decimal("800")
    assert pnl.ebit == Decimal("3700")
    assert pnl.finance_costs == Decimal("200")
    assert pnl.pbt == Decimal("3500")
    assert pnl.net_profit == Decimal("3500")


def test_balance_sheet_from_journal_balances():
    j, coa = _company()
    bs = balance_sheet_from_journal(j, coa, as_of="2026-11-30")
    assert bs.current_assets == Decimal("13500")
    assert bs.total_assets == Decimal("13500")
    assert bs.total_liabilities == Decimal("0")
    assert bs.equity == Decimal("13500")       # 10000 capital + 3500 net profit
    assert bs.validation_warnings() == []       # identity holds
    assert bs.working_capital == Decimal("13500")
    assert bs.current_ratio is None             # no current liabilities


def test_same_journal_pnl_and_bs_are_consistent():
    # The P&L net profit must be exactly the retained-earnings in the BS equity.
    j, coa = _company()
    pnl = pnl_from_journal(j, coa, "2026-11", "2026-11-01", "2026-11-30")
    bs = balance_sheet_from_journal(j, coa, as_of="2026-11-30")
    recorded_equity = Decimal("10000")
    assert bs.equity - recorded_equity == pnl.net_profit
