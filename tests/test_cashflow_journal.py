"""Journal-derived (direct-method) cash flow tests (v1.5.7).

The key invariant: net cash flow == actual change in cash-account balances.
Expected sections are hand-calculated below.

Sample (entity demo, starter chart; Cash=1000, Bank=1010 are cash accounts):
  E0 capital 20000:        Dr Cash 20000 / Cr Owner's Equity   -> financing +20000
  E1 cash sale 9000:       Dr Cash 9000  / Cr Sales            -> operating  +9000
  E2 buy equipment 5000:   Dr Equipment  / Cr Bank -5000       -> investing  -5000
  E3 pay rent 800:         Dr Rent / Cr Cash -800              -> operating   -800
  E4 take loan 3000:       Dr Bank 3000 / Cr Long-term Loans   -> financing +3000
  E5 credit sale 500:      Dr AR / Cr Sales (NO cash)          -> ignored

Expected:
  operating = 9000 - 800          = 8200
  investing = -5000               = -5000
  financing = 20000 + 3000        = 23000
  net_change                      = 26200
Cash+Bank actual: Cash 20000+9000-800 = 28200; Bank -5000+3000 = -2000; total 26200.
"""

from decimal import Decimal

from fin_engine import (
    Account, ChartOfAccounts, Journal, JournalEntry, Posting, starter_chart,
)
from fin_engine.statements import cash_flow_from_journal
from fin_engine.ledger_gl import account_balance


def _company():
    coa = starter_chart("demo")
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "20000"), Posting("3000", "-20000")]))
    j.post(JournalEntry("E1", "2026-11-02", "cash sale",
                        [Posting("1000", "9000"), Posting("4000", "-9000")]))
    j.post(JournalEntry("E2", "2026-11-03", "buy equipment",
                        [Posting("1500", "5000"), Posting("1010", "-5000")]))
    j.post(JournalEntry("E3", "2026-11-04", "rent",
                        [Posting("6100", "800"), Posting("1000", "-800")]))
    j.post(JournalEntry("E4", "2026-11-05", "take loan",
                        [Posting("1010", "3000"), Posting("2200", "-3000")]))
    j.post(JournalEntry("E5", "2026-11-06", "credit sale (no cash)",
                        [Posting("1100", "500"), Posting("4000", "-500")]))
    return j, coa


def test_sections_match_hand_calc():
    j, coa = _company()
    cf = cash_flow_from_journal(j, coa, "2026-11")
    assert cf.operating == Decimal("8200")
    assert cf.investing == Decimal("-5000")
    assert cf.financing == Decimal("23000")
    assert cf.net_change == Decimal("26200")


def test_net_change_reconciles_to_cash_balances():
    # The invariant that makes this journal-derived: net cash flow == the actual
    # change in all cash-account balances.
    j, coa = _company()
    cf = cash_flow_from_journal(j, coa, "2026-11")
    cash_total = (account_balance(j, coa, "1000", as_of="2026-11-30")
                  + account_balance(j, coa, "1010", as_of="2026-11-30"))
    assert cf.net_change == cash_total == Decimal("26200")


def test_non_cash_entry_ignored():
    # A purely accrual entry (credit sale, no cash leg) contributes nothing.
    coa = starter_chart("demo")
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E1", "2026-11-01", "credit sale",
                        [Posting("1100", "500"), Posting("4000", "-500")]))
    cf = cash_flow_from_journal(j, coa, "2026-11")
    assert cf.net_change == Decimal("0")


def test_draft_entry_excluded():
    from fin_engine import EntryStatus
    coa = starter_chart("demo")
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("D1", "2026-11-01", "draft sale",
                        [Posting("1000", "1000"), Posting("4000", "-1000")],
                        status=EntryStatus.DRAFT))
    cf = cash_flow_from_journal(j, coa, "2026-11")
    assert cf.net_change == Decimal("0")
