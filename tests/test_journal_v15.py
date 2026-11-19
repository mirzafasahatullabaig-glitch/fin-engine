"""Phase 2 journal tests: chart integration + posting lifecycle (prompt 9.2).

Expected balances are hand-computed. Pre-v1.5 journal tests live in
test_journal.py and must keep passing (no chart = free-text accounts).
"""

import pytest
from decimal import Decimal

from fin_engine import (
    Account, ChartOfAccounts, EntryStatus, Journal, JournalEntry, Posting,
)
from fin_engine.models import AccountGroup


def _chart():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE,
                    is_active=False))  # inactive on purpose
    return coa


def _sale(entry_id="E1", date="2026-11-01"):
    return JournalEntry(
        entry_id=entry_id, date=date, description="cash sale",
        postings=[Posting("1000", "1000"), Posting("4000", "-1000")],
    )


def test_post_with_chart_validates_accounts():
    j = Journal(entity="demo", chart=_chart())
    j.post(_sale())
    assert j.balance("1000") == Decimal("1000")


def test_post_unknown_account_rejected():
    j = Journal(entity="demo", chart=_chart())
    bad = JournalEntry(
        entry_id="E2", date="2026-11-01", description="bad",
        postings=[Posting("9999", "500"), Posting("4000", "-500")],
    )
    with pytest.raises(KeyError):
        j.post(bad)


def test_post_inactive_account_rejected():
    j = Journal(entity="demo", chart=_chart())
    bad = JournalEntry(
        entry_id="E3", date="2026-11-01", description="rent on dead account",
        postings=[Posting("6100", "300"), Posting("1000", "-300")],
    )
    with pytest.raises(ValueError, match="inactive"):
        j.post(bad)


def test_draft_entry_excluded_from_balances():
    j = Journal(entity="demo", chart=_chart())
    draft = JournalEntry(
        entry_id="D1", date="2026-11-01", description="not yet posted",
        postings=[Posting("1000", "5000"), Posting("4000", "-5000")],
        status=EntryStatus.DRAFT,
    )
    j.post(draft)
    assert j.balance("1000") == Decimal("0")  # draft does not count
    assert j.is_balanced()


def test_reversal_offsets_original():
    j = Journal(entity="demo", chart=_chart())
    j.post(_sale("E1"))
    assert j.balance("1000") == Decimal("1000")
    j.reverse("E1", reversal_id="E1R", date="2026-11-05")
    # Original REVERSED + reversing entry => net zero, journal still balanced.
    assert j.balance("1000") == Decimal("0")
    assert j.balance("4000") == Decimal("0")
    assert j.is_balanced()
    original = next(e for e in j.entries if e.entry_id == "E1")
    assert original.status is EntryStatus.REVERSED
    assert any(e.entry_id == "E1R" for e in j.entries)  # original NOT deleted


def test_cannot_reverse_a_reversed_entry():
    j = Journal(entity="demo", chart=_chart())
    j.post(_sale("E1"))
    j.reverse("E1", "E1R", "2026-11-05")
    with pytest.raises(ValueError, match="only POSTED"):
        j.reverse("E1", "E1R2", "2026-11-06")


def test_cannot_reverse_unknown_entry():
    j = Journal(entity="demo", chart=_chart())
    with pytest.raises(ValueError, match="unknown entry"):
        j.reverse("nope", "R", "2026-11-05")


def test_no_chart_still_accepts_free_text_accounts():
    # Backward compatibility: pre-v1.5 behaviour.
    j = Journal(entity="demo")
    j.post(_sale())
    assert j.balance("1000") == Decimal("1000")
