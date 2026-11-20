"""SQLite persistence for accounts and journal entries (v1.5.4 #5).

Local-first durable storage using the stdlib ``sqlite3`` — no new dependency,
no server. The in-memory :class:`~fin_engine.journal.Journal` is unchanged; this
is a separate layer that saves and reloads it.

Transaction safety: an entry and all its postings are written inside ONE
transaction (``with self._conn`` commits on success, rolls back on any error),
so a partially-written entry can never be persisted. A UNIQUE constraint on
``(entity, entry_id)`` enforces duplicate rejection at the database level too.

Reload goes back through the normal constructors (``Account``, ``JournalEntry``,
``Journal.post``), so the same validation that guards fresh data also guards
data read from disk — a tampered row is rejected, not trusted.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from .accounts import Account, ChartOfAccounts
from .journal import EntryStatus, Journal, JournalEntry, Posting
from .logging_setup import get_logger
from .models import AccountGroup

_log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    entity TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    grp TEXT NOT NULL,
    current INTEGER NOT NULL,
    parent_code TEXT,
    is_active INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (entity, code)
);
CREATE TABLE IF NOT EXISTS entries (
    entity TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (entity, entry_id)
);
CREATE TABLE IF NOT EXISTS postings (
    entity TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    account TEXT NOT NULL,
    amount TEXT NOT NULL,          -- Decimal as text: exact, never float
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (entity, entry_id, seq),
    FOREIGN KEY (entity, entry_id) REFERENCES entries(entity, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_postings_entry ON postings(entity, entry_id);
"""


class JournalStore:
    """A SQLite-backed store for one or more entities' accounts and journals."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets concurrent readers proceed while a single writer commits
        # (SQLite is single-writer by design). Skip it for in-memory DBs.
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        with self._conn:
            self._conn.executescript(_SCHEMA)
            self._migrate()
        _log.info("journal store opened at %s", self.path)

    def backup(self, dest_path: str | Path) -> str:
        """Write a consistent copy of the whole DB to ``dest_path``.

        Uses SQLite's online backup API, which is safe to run while the store
        is open (it copies a transactionally-consistent snapshot). Returns the
        destination path. Verify a backup with ``integrity_check`` after.
        """
        dest = sqlite3.connect(str(dest_path))
        try:
            with dest:
                self._conn.backup(dest)
        finally:
            dest.close()
        _log.info("backed up %s -> %s", self.path, dest_path)
        return str(dest_path)

    def integrity_check(self) -> bool:
        """True iff SQLite reports the database structurally sound.

        Runs ``PRAGMA integrity_check`` (detects corruption). Use on a restored
        backup before trusting it, or as a periodic health check.
        """
        row = self._conn.execute("PRAGMA integrity_check").fetchone()
        ok = bool(row) and row[0] == "ok"
        if not ok:
            _log.warning("integrity check FAILED: %s", row)
        return ok

    @classmethod
    def restore(cls, backup_path: str | Path, dest_path: str | Path) -> "JournalStore":
        """Restore a backup file to ``dest_path`` and open it.

        Refuses to proceed if the backup fails its integrity check, so a
        corrupt backup can't silently become the live ledger.
        """
        src = JournalStore(backup_path)
        try:
            if not src.integrity_check():
                raise ValueError(f"backup {backup_path} failed integrity check; "
                                 "not restoring")
            src.backup(dest_path)
        finally:
            src.close()
        return cls(dest_path)

    def _migrate(self) -> None:
        """Add audit columns to a pre-v1.5.6 entries table (idempotent)."""
        cols = {r[1] for r in self._conn.execute(
            "PRAGMA table_info(entries)").fetchall()}
        for col in ("created_by", "created_at"):
            if col not in cols:
                self._conn.execute(
                    f"ALTER TABLE entries ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "JournalStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- chart -----------------------------------------------------------
    def save_chart(self, chart: ChartOfAccounts) -> None:
        """Persist every account for the chart's entity (one transaction)."""
        with self._conn:  # commit on success, rollback on error
            for a in chart.accounts():
                self._conn.execute(
                    "INSERT OR REPLACE INTO accounts "
                    "(entity, code, name, grp, current, parent_code, is_active, description) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (chart.entity, a.code, a.name, a.group.value,
                     int(a.current), a.parent_code, int(a.is_active), a.description),
                )

    def load_chart(self, entity: str) -> ChartOfAccounts:
        """Rebuild a ChartOfAccounts from disk, re-running account validation."""
        rows = self._conn.execute(
            "SELECT code, name, grp, current, parent_code, is_active, description "
            "FROM accounts WHERE entity=? ORDER BY code", (entity,)
        ).fetchall()
        coa = ChartOfAccounts(entity)
        # Parents must exist before children: accounts without a parent first.
        rows.sort(key=lambda r: r[4] is not None)
        for code, name, grp, current, parent, active, desc in rows:
            coa.add(Account(code=code, name=name, group=AccountGroup(grp),
                            current=bool(current), parent_code=parent,
                            is_active=bool(active), description=desc))
        return coa

    # --- entries ---------------------------------------------------------
    def save_entry(self, entity: str, entry: JournalEntry) -> None:
        """Persist one entry and all its postings in a single transaction.

        Raises ``ValueError`` on a duplicate entry_id (the UNIQUE constraint),
        leaving the store unchanged — the transaction rolls back.
        """
        try:
            with self._conn:  # atomic: entry + all postings, or nothing
                self._conn.execute(
                    "INSERT INTO entries "
                    "(entity, entry_id, date, description, ref, status, "
                    " created_by, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (entity, entry.entry_id, entry.date, entry.description,
                     entry.ref, entry.status.value,
                     entry.created_by, entry.created_at),
                )
                for seq, p in enumerate(entry.postings):
                    self._conn.execute(
                        "INSERT INTO postings "
                        "(entity, entry_id, seq, account, amount, description) "
                        "VALUES (?,?,?,?,?,?)",
                        (entity, entry.entry_id, seq, p.account,
                         str(p.amount), p.description),
                    )
            _log.info("persisted entry %r for %s", entry.entry_id, entity)
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"cannot persist entry {entry.entry_id!r}: already stored "
                f"for entity {entity!r}"
            ) from e

    def save_journal(self, journal: Journal) -> None:
        """Persist a whole journal (chart first if attached, then entries)."""
        if journal.chart is not None:
            self.save_chart(journal.chart)
        for e in journal.entries:
            # Skip entries already stored so re-saving is safe (idempotent).
            exists = self._conn.execute(
                "SELECT 1 FROM entries WHERE entity=? AND entry_id=?",
                (journal.entity, e.entry_id)).fetchone()
            if not exists:
                self.save_entry(journal.entity, e)

    def load_journal(self, entity: str) -> Journal:
        """Rebuild a Journal (with its chart) from disk.

        Reconstruction posts through ``Journal.post``, so every reloaded entry
        is revalidated (balance, known/active accounts) — disk data is not
        blindly trusted.
        """
        chart = self.load_chart(entity)
        journal = Journal(entity, chart=chart if chart.accounts() else None)
        erows = self._conn.execute(
            "SELECT entry_id, date, description, ref, status, created_by, "
            "created_at FROM entries WHERE entity=? ORDER BY date, entry_id",
            (entity,)
        ).fetchall()
        for entry_id, date, desc, ref, status, cby, cat in erows:
            prows = self._conn.execute(
                "SELECT account, amount, description FROM postings "
                "WHERE entity=? AND entry_id=? ORDER BY seq", (entity, entry_id)
            ).fetchall()
            postings = [Posting(acct, Decimal(amt), pdesc)
                        for acct, amt, pdesc in prows]
            # Pass stored audit values so they persist unchanged across reloads.
            journal.post(JournalEntry(entry_id, date, desc, postings, ref=ref,
                                      status=EntryStatus(status),
                                      created_by=cby, created_at=cat))
        return journal
