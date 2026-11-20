"""v1.5.4 tests: date/entity validation, refund netting, advice gating."""

import pytest
from decimal import Decimal

from fin_engine import (
    Account, ChartOfAccounts, Journal, JournalEntry, Posting, advise,
)
from fin_engine.models import AccountGroup
from fin_engine.statements import pnl_from_journal


def _chart(entity="demo"):
    coa = ChartOfAccounts(entity)
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("3000", "Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE, current=False))
    return coa


# --- #2 strict date validation -------------------------------------------
def test_invalid_date_rejected_at_entry_construction():
    with pytest.raises(ValueError, match="E1"):  # rejected, message names entry
        JournalEntry("E1", "2026-02-30", "impossible date",
                     [Posting("1000", "100"), Posting("4000", "-100")])
    with pytest.raises(ValueError):  # bad format too
        JournalEntry("E2", "15/11/2026", "bad format",
                     [Posting("1000", "100"), Posting("4000", "-100")])


def test_valid_date_accepted():
    e = JournalEntry("E1", "2026-11-15", "ok",
                     [Posting("1000", "100"), Posting("4000", "-100")])
    assert e.date == "2026-11-15"


# --- #2 entity isolation --------------------------------------------------
def test_journal_rejects_foreign_entity_chart():
    foreign = _chart("other-co")
    with pytest.raises(ValueError, match="entity mismatch"):
        Journal("demo", chart=foreign)


def test_matching_entity_ok():
    j = Journal("demo", chart=_chart("demo"))
    assert j.entity == "demo"


# --- #4 refund / contra netting -------------------------------------------
def test_refund_nets_within_revenue_not_crash():
    # Sale 1000, then a 300 refund (debit revenue). Net revenue = 700.
    j = Journal("demo", chart=_chart())
    j.post(JournalEntry("E1", "2026-11-01", "sale",
                        [Posting("1000", "1000"), Posting("4000", "-1000")]))
    j.post(JournalEntry("E2", "2026-11-02", "refund",
                        [Posting("4000", "300"), Posting("1000", "-300")]))
    pnl = pnl_from_journal(j, _chart(), "2026-11")
    assert pnl.revenue == Decimal("700")


def test_net_negative_revenue_flows_through_not_crash():
    # Refunds exceed sales: revenue nets to -200. Must produce a P&L, not raise.
    j = Journal("demo", chart=_chart())
    j.post(JournalEntry("E1", "2026-11-01", "sale",
                        [Posting("1000", "100"), Posting("4000", "-100")]))
    j.post(JournalEntry("E2", "2026-11-02", "big refund",
                        [Posting("4000", "300"), Posting("1000", "-300")]))
    pnl = pnl_from_journal(j, _chart(), "2026-11")
    assert pnl.revenue == Decimal("-200")
    assert pnl.gross_profit == Decimal("-200")


# --- #3 advice gated on reconciliation ------------------------------------
def test_advice_refused_when_books_do_not_reconcile():
    j = Journal("demo", chart=_chart())
    j.post(JournalEntry("E1", "2026-11-01", "sale",
                        [Posting("1000", "1000"), Posting("4000", "-1000")]))
    # Corrupt the entry so the journal no longer balances.
    e = j.entries[0]
    object.__setattr__(e, "postings",
                       (Posting("1000", "1000"), Posting("4000", "-900")))

    called = {"n": 0}
    def gen(prompt):
        called["n"] += 1
        return "advice"

    class _KB:
        def retrieve(self, q, k=3):
            return []

    adv = advise("what should I do?", j, _chart(), "2026-11", "2026-11-30",
                 _KB(), gen)
    assert adv.grounded is False
    assert "do not reconcile" in adv.recommendation
    assert called["n"] == 0  # the model is never called on bad books
