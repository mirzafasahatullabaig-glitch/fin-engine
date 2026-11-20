"""Audit-trail tests (v1.5.6): who/when stamped, preserved, persisted, migrated."""

import sqlite3
from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.models import AccountGroup
from fin_engine.store import JournalStore


def _entry(eid="E1", **kw):
    return JournalEntry(eid, "2026-11-01", "sale",
                        [Posting("1000", "100"), Posting("4000", "-100")], **kw)


def test_audit_stamp_autofilled():
    e = _entry()
    assert e.created_at  # non-empty ISO timestamp
    assert "T" in e.created_at  # ISO datetime
    assert e.created_by  # some user string


def test_explicit_audit_values_preserved():
    e = _entry(created_by="alice", created_at="2026-11-01T09:00:00+00:00")
    assert e.created_by == "alice"
    assert e.created_at == "2026-11-01T09:00:00+00:00"


def _chart():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    return coa


def test_audit_round_trips_through_store():
    j = Journal("demo", chart=_chart())
    j.post(_entry(created_by="alice", created_at="2026-11-01T09:00:00+00:00"))
    with JournalStore(":memory:") as store:
        store.save_journal(j)
        loaded = store.load_journal("demo")
    e = loaded.entries[0]
    assert e.created_by == "alice"           # preserved, not re-stamped
    assert e.created_at == "2026-11-01T09:00:00+00:00"


def test_migration_adds_columns_to_old_db(tmp_path):
    # Build a pre-v1.5.6 entries table WITHOUT the audit columns, then open it
    # with JournalStore and confirm the migration added them.
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE entries (entity TEXT, entry_id TEXT, date TEXT, "
        "description TEXT, ref TEXT, status TEXT, PRIMARY KEY(entity, entry_id));"
        "CREATE TABLE accounts (entity TEXT, code TEXT, name TEXT, grp TEXT, "
        "current INTEGER, parent_code TEXT, is_active INTEGER, description TEXT, "
        "PRIMARY KEY(entity, code));"
        "CREATE TABLE postings (entity TEXT, entry_id TEXT, seq INTEGER, "
        "account TEXT, amount TEXT, description TEXT, "
        "PRIMARY KEY(entity, entry_id, seq));"
    )
    con.commit(); con.close()
    with JournalStore(str(db)) as store:
        cols = {r[1] for r in store._conn.execute(
            "PRAGMA table_info(entries)").fetchall()}
    assert "created_by" in cols
    assert "created_at" in cols
