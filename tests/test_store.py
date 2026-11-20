"""SQLite persistence tests (v1.5.4 #5). In-memory DB; no files touched."""

import pytest
from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.models import AccountGroup
from fin_engine.store import JournalStore
from fin_engine.ledger_gl import trial_balance


def _company():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("1200", "Inventory", AccountGroup.ASSET))
    coa.add(Account("3000", "Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "20000.50"), Posting("3000", "-20000.50")]))
    j.post(JournalEntry("E1", "2026-11-05", "sale",
                        [Posting("1000", "9000"), Posting("4000", "-9000")]))
    return j, coa


def test_round_trip_preserves_exact_decimals():
    j, _ = _company()
    with JournalStore(":memory:") as store:
        store.save_journal(j)
        loaded = store.load_journal("demo")
    assert len(loaded.entries) == 2
    # Exact Decimal survived the text round-trip (no float drift).
    assert loaded.balance("1000") == Decimal("29000.50")
    assert loaded.balance("3000") == Decimal("-20000.50")
    # Reloaded journal still reconciles.
    assert trial_balance(loaded, loaded.chart, as_of="2026-11-30").balanced


def test_duplicate_entry_rejected_at_db_level():
    j, _ = _company()
    with JournalStore(":memory:") as store:
        store.save_journal(j)
        with pytest.raises(ValueError, match="already stored"):
            store.save_entry("demo", j.entries[0])  # E0 again


def test_duplicate_save_leaves_no_orphan_postings():
    # Re-saving an existing entry_id hits the UNIQUE constraint on the entries
    # insert; the whole transaction (entry + postings) must roll back, so no
    # duplicate postings are left behind. Verifies transaction atomicity.
    j, coa = _company()
    store = JournalStore(":memory:")
    store.save_journal(j)
    postings_before = store._conn.execute(
        "SELECT COUNT(*) FROM postings WHERE entry_id='E0'").fetchone()[0]
    with pytest.raises(ValueError, match="already stored"):
        store.save_entry("demo", j.entries[0])  # E0 again -> IntegrityError
    postings_after = store._conn.execute(
        "SELECT COUNT(*) FROM postings WHERE entry_id='E0'").fetchone()[0]
    assert postings_after == postings_before  # no extra postings from the failed save
    store.close()


def test_reload_revalidates_accounts():
    j, coa = _company()
    store = JournalStore(":memory:")
    store.save_journal(j)
    # Tamper: delete an account row the postings reference, then reload.
    store._conn.execute("DELETE FROM accounts WHERE code='4000'")
    store._conn.commit()
    with pytest.raises((KeyError, ValueError)):
        store.load_journal("demo")  # posting to a now-unknown account is caught
    store.close()


def test_chart_round_trip():
    _, coa = _company()
    with JournalStore(":memory:") as store:
        store.save_chart(coa)
        loaded = store.load_chart("demo")
    assert len(loaded.accounts()) == 4
    assert loaded.get("1200").name == "Inventory"
