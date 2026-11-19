"""General Ledger tests (prompt 9.3).

A small hand-calculated company ledger. Expected balances are worked out by
hand below, not read back from the code.

Sample journal (entity demo, Nov 2026), accounts from the starter chart:
  E1 2026-11-01  cash sale 1000:      Dr Cash 1000  / Cr Sales 1000
  E2 2026-11-03  pay rent 300:        Dr Rent 300   / Cr Cash 300
  E3 2026-11-10  buy equipment 2000:  Dr Equipment 2000 / Cr Bank 2000
  E4 2026-11-20  credit sale 500:     Dr AR 500     / Cr Sales 500

Expected normal-balance-positive balances as of 2026-11-30:
  Cash (1000, debit-normal):   +1000 - 300        = 700
  Bank (1010, debit-normal):   -2000              = -2000 (overdrawn)
  AR   (1100, debit-normal):   +500               = 500
  Equipment (1500, debit):     +2000              = 2000
  Sales (4000, credit-normal): credit 1500 -> +1500
  Rent (6100, debit-normal):   +300               = 300
Trial balance: debits 700 + 500 + 2000 + 300 = 3500 (Cash/AR/Equip/Rent),
               Bank -2000 sits on the credit side as 2000,
               credits 1500 (Sales) + 2000 (Bank) = 3500. Balanced.
"""

from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.ledger_gl import account_activity, account_balance, trial_balance
from fin_engine.models import AccountGroup


def _setup():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("1010", "Bank", AccountGroup.ASSET))
    coa.add(Account("1100", "AR", AccountGroup.ASSET))
    coa.add(Account("1500", "Equipment", AccountGroup.ASSET, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE))
    j = Journal(entity="demo", chart=coa)
    j.post(JournalEntry("E1", "2026-11-01", "cash sale",
                        [Posting("1000", "1000"), Posting("4000", "-1000")]))
    j.post(JournalEntry("E2", "2026-11-03", "rent",
                        [Posting("6100", "300"), Posting("1000", "-300")]))
    j.post(JournalEntry("E3", "2026-11-10", "equipment",
                        [Posting("1500", "2000"), Posting("1010", "-2000")]))
    j.post(JournalEntry("E4", "2026-11-20", "credit sale",
                        [Posting("1100", "500"), Posting("4000", "-500")]))
    return j, coa


def test_debit_normal_balance():
    j, coa = _setup()
    assert account_balance(j, coa, "1000") == Decimal("700")
    assert account_balance(j, coa, "1100") == Decimal("500")
    assert account_balance(j, coa, "6100") == Decimal("300")


def test_credit_normal_balance_is_positive():
    j, coa = _setup()
    # Sales is credit-normal; net credit 1500 reads as +1500.
    assert account_balance(j, coa, "4000") == Decimal("1500")


def test_overdrawn_debit_account_goes_negative():
    j, coa = _setup()
    assert account_balance(j, coa, "1010") == Decimal("-2000")


def test_as_of_date_excludes_later_entries():
    j, coa = _setup()
    # Before the credit sale (E4 on 11-20), AR is zero.
    assert account_balance(j, coa, "1100", as_of="2026-11-15") == Decimal("0")
    assert account_balance(j, coa, "1100", as_of="2026-11-30") == Decimal("500")


def test_trial_balance_is_balanced():
    j, coa = _setup()
    tb = trial_balance(j, coa, as_of="2026-11-30")
    assert tb.total_debits == Decimal("3500")
    assert tb.total_credits == Decimal("3500")
    assert tb.balanced
    assert tb.difference == Decimal("0")


def test_account_activity_opening_and_closing():
    j, coa = _setup()
    # Cash: opening before 11-02 = +1000 (E1 only). Period 11-02..11-30: credit
    # 300 (E2). Closing = 700.
    act = account_activity(j, coa, "1000", start="2026-11-02", end="2026-11-30")
    assert act.opening == Decimal("1000")
    assert act.period_debits == Decimal("0")
    assert act.period_credits == Decimal("300")
    assert act.closing == Decimal("700")


def test_missing_account_raises_not_zero():
    import pytest
    j, coa = _setup()
    with pytest.raises(KeyError):
        account_balance(j, coa, "9999")
