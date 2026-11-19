"""Reconciliation tests (prompt 9.6/9.7). Includes negative tests that
deliberately introduce errors and confirm reconciliation CATCHES them."""

from dataclasses import replace
from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.models import AccountGroup
from fin_engine.reconciliation import reconcile


def _company():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("2000", "Accounts Payable", AccountGroup.LIABILITY))
    coa.add(Account("3000", "Owner's Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE, current=False))
    j = Journal(entity="demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "10000"), Posting("3000", "-10000")]))
    j.post(JournalEntry("E1", "2026-11-02", "sale",
                        [Posting("1000", "6000"), Posting("4000", "-6000")]))
    j.post(JournalEntry("E2", "2026-11-03", "rent",
                        [Posting("6100", "800"), Posting("1000", "-800")]))
    return j, coa


def test_clean_company_reconciles():
    j, coa = _company()
    rep = reconcile(j, coa, as_of="2026-11-30")
    assert rep.passed
    assert rep.failures == []


def test_unbalanced_entry_is_caught():
    # Corrupt the journal AFTER posting (bypassing the constructor's balance
    # check) to simulate bad data, and confirm reconciliation detects it.
    j, coa = _company()
    good = j.entries[1]
    object.__setattr__(good, "postings",
                       (Posting("1000", "6000"), Posting("4000", "-5000")))
    rep = reconcile(j, coa, as_of="2026-11-30")
    assert not rep.passed
    assert any(c.name.startswith("J1:entry_balances") and not c.passed
               for c in rep.checks)


def test_trial_balance_break_is_caught():
    # Corrupt a posting so the journal no longer balances overall: cash debited
    # 10000 but equity credited only 9000. Trial balance and entry-balance both
    # fail; reconciliation must report it, not pass.
    j, coa = _company()
    cap = j.entries[0]
    object.__setattr__(cap, "postings",
                       (Posting("1000", "10000"), Posting("3000", "-9000")))
    rep = reconcile(j, coa, as_of="2026-11-30")
    assert not rep.passed
    assert any(c.name == "T1:trial_balance" and not c.passed for c in rep.checks)


def test_report_is_structured():
    j, coa = _company()
    rep = reconcile(j, coa, as_of="2026-11-30")
    assert rep.entity == "demo"
    assert rep.as_of == "2026-11-30"
    assert any(c.name == "T1:trial_balance" for c in rep.checks)
    assert any(c.name == "B1:accounting_identity" for c in rep.checks)
    assert any(c.name == "B2:working_capital" for c in rep.checks)
