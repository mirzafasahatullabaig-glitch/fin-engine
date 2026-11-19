"""Double-entry journal tests.

Expected values are hand-specified here, independent of the implementation
(report §9: don't let the code under test also define the expected result).
"""

import pytest
from decimal import Decimal

from fin_engine import Journal, JournalEntry, Posting


def _sale():
    # Cash sale of 1,000: debit Cash 1000, credit Revenue 1000.
    return JournalEntry(
        entry_id="E1", date="2026-11-01", description="cash sale",
        postings=[Posting("Cash", "1000"), Posting("Revenue", "-1000")],
        ref="INV-001",
    )


def test_balanced_entry_posts():
    j = Journal(entity="demo")
    j.post(_sale())
    assert len(j.entries) == 1
    assert j.is_balanced()
    assert j.balance("Cash") == Decimal("1000")
    assert j.balance("Revenue") == Decimal("-1000")


def test_unbalanced_entry_rejected():
    with pytest.raises(ValueError, match="unbalanced"):
        JournalEntry(
            entry_id="E2", date="2026-11-01", description="bad",
            postings=[Posting("Cash", "1000"), Posting("Revenue", "-900")],
        )


def test_split_entry_balances():
    # Pay 1,000: 600 rent + 400 utilities out of cash.
    e = JournalEntry(
        entry_id="E3", date="2026-11-02", description="split payment",
        postings=[
            Posting("Rent", "600"),
            Posting("Utilities", "400"),
            Posting("Cash", "-1000"),
        ],
    )
    assert e.total_debits == Decimal("1000")


def test_single_posting_rejected():
    with pytest.raises(ValueError, match=">= 2 postings"):
        JournalEntry(entry_id="E4", date="2026-11-01", description="x",
                     postings=[Posting("Cash", "100")])


def test_zero_amount_posting_rejected():
    with pytest.raises(ValueError, match="zero amount"):
        Posting("Cash", "0")


def test_float_amount_rejected():
    # money() rejects float to avoid binary-rounding error.
    with pytest.raises(TypeError):
        Posting("Cash", 10.5)


def test_duplicate_entry_id_rejected():
    j = Journal(entity="demo")
    j.post(_sale())
    with pytest.raises(ValueError, match="duplicate entry_id"):
        j.post(_sale())  # same id E1


def test_duplicate_ref_flagged_not_rejected():
    j = Journal(entity="demo")
    j.post(_sale())
    j.post(JournalEntry(
        entry_id="E9", date="2026-11-03", description="same ref again",
        postings=[Posting("Cash", "1000"), Posting("Revenue", "-1000")],
        ref="INV-001",  # reused ref -> warning, still posts
    ))
    assert len(j.entries) == 2
    assert any("INV-001" in w for w in j.warnings)


def test_whole_journal_balance_invariant():
    j = Journal(entity="demo")
    j.post(_sale())
    j.post(JournalEntry(
        entry_id="E5", date="2026-11-02", description="pay rent",
        postings=[Posting("Rent", "600"), Posting("Cash", "-600")],
    ))
    assert j.is_balanced()  # every entry balances => whole journal balances
