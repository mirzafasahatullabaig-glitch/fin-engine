"""Double-entry journal: the posting layer the P&L/cash-flow engine assumes.

Until now a :class:`~fin_engine.models.Ledger` was just a bag of pre-classified
magnitudes. This module adds the step before that: real journal entries with a
debit side and a credit side that must balance, duplicate detection, and
validation warnings surfaced to every report (report §2.B/§2.D).

Design notes (ponytail: smallest thing that is actually double-entry):
- An entry is one or more postings; each posting is an account + a SIGNED
  amount where debit is +, credit is -. The entry balances when its postings
  sum to exactly zero. This is simpler and harder to get wrong than separate
  debit/credit magnitude fields, and it generalises to split entries for free.
- Amounts stay Decimal via ``money()`` — no float ever enters a posting.
- Nothing here guesses or auto-posts: unbalanced or duplicate entries are
  REJECTED (raise) or FLAGGED (warnings list), never silently fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from typing import Optional

from .models import FORMULA_VERSION, money
from .logging_setup import get_logger

_log = get_logger(__name__)


class EntryStatus(str, Enum):
    """Posting lifecycle (v1.5.0, prompt 4.3). Only POSTED entries affect
    statements; a REVERSED original is offset by a posted reversing entry rather
    than deleted (append-only audit trail)."""

    DRAFT = "draft"
    POSTED = "posted"
    REVERSED = "reversed"


@dataclass(frozen=True)
class Posting:
    """One side of a journal entry.

    ``amount`` is signed: a debit is positive, a credit is negative. A balanced
    entry's postings sum to zero.
    """

    account: str
    amount: Decimal
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", money(self.amount))
        if self.amount == 0:
            raise ValueError(f"posting to {self.account!r} has zero amount")
        if not self.account.strip():
            raise ValueError("posting account must be non-empty")

    @property
    def is_debit(self) -> bool:
        return self.amount > 0


@dataclass(frozen=True)
class JournalEntry:
    """A balanced set of postings recorded on one date.

    Raises ``ValueError`` at construction if debits != credits, so an unbalanced
    entry can never be posted. ``ref`` is the caller's unique reference used for
    duplicate detection; two entries with the same ``ref`` are duplicates.
    """

    entry_id: str
    date: str          # ISO "YYYY-MM-DD"; validated at construction (v1.5.4)
    description: str
    postings: tuple[Posting, ...]
    ref: str = ""      # external reference (invoice no., bank txn id, ...)
    status: EntryStatus = EntryStatus.POSTED  # default keeps pre-v1.5 behaviour
    created_by: str = ""   # audit: who recorded it (v1.5.6); defaults to OS user
    created_at: str = ""   # audit: when, ISO-8601 UTC; stamped if left blank
    formula_version: str = FORMULA_VERSION

    def __post_init__(self) -> None:
        # Strict date: reject impossible/misformatted dates at the boundary so a
        # bad date can never enter the ledger (v1.5.4). Keeps the string type.
        from .periods import parse_date
        try:
            parse_date(self.date)
        except ValueError as e:
            raise ValueError(f"entry {self.entry_id!r}: {e}") from None
        # Audit stamp (v1.5.6): fill who/when when not supplied, so every entry
        # carries provenance. A reload passes the stored values, so they persist
        # unchanged rather than being re-stamped.
        if not self.created_at:
            from datetime import datetime, timezone
            object.__setattr__(self, "created_at",
                               datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if not self.created_by:
            import getpass
            try:
                object.__setattr__(self, "created_by", getpass.getuser())
            except Exception:
                object.__setattr__(self, "created_by", "unknown")
        if isinstance(self.postings, list):
            object.__setattr__(self, "postings", tuple(self.postings))
        if len(self.postings) < 2:
            raise ValueError(
                f"entry {self.entry_id!r} needs >= 2 postings (a debit and a "
                f"credit), got {len(self.postings)}"
            )
        imbalance = sum((p.amount for p in self.postings), Decimal(0))
        if imbalance != 0:
            raise ValueError(
                f"entry {self.entry_id!r} is unbalanced: debits - credits = "
                f"{imbalance} (must be 0)"
            )

    @property
    def total_debits(self) -> Decimal:
        return sum((p.amount for p in self.postings if p.amount > 0), Decimal(0))


@dataclass
class Journal:
    """An append-only collection of balanced entries for one entity.

    ``post`` enforces unique ``entry_id`` and flags duplicate ``ref`` values.
    Validation never silently drops data: a duplicate id is rejected outright
    (it would corrupt the audit trail), while a repeated ``ref`` is recorded in
    ``warnings`` for review (same bank reference may legitimately recur, so we
    flag not reject — report §2.D).
    """

    entity: str
    entries: list[JournalEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    chart: Optional["object"] = None  # ChartOfAccounts; optional to keep old API

    def __post_init__(self) -> None:
        # Entity isolation (v1.5.4): a journal and its chart must describe the
        # same entity, so Entity A's journal can never post into Entity B's
        # chart of accounts.
        if self.chart is not None:
            chart_entity = getattr(self.chart, "entity", None)
            if chart_entity is not None and chart_entity != self.entity:
                raise ValueError(
                    f"entity mismatch: journal {self.entity!r} attached to a "
                    f"chart for {chart_entity!r}"
                )

    def post(self, entry: JournalEntry) -> None:
        if any(e.entry_id == entry.entry_id for e in self.entries):
            _log.warning("rejected entry %r: duplicate entry_id", entry.entry_id)
            raise ValueError(
                f"duplicate entry_id {entry.entry_id!r}; ids must be unique"
            )
        # When a chart is attached, every posting must hit a known, active
        # account (prompt 4.2). Without a chart, accounts are free text (the
        # pre-v1.5 behaviour used by unit tests).
        if self.chart is not None:
            for p in entry.postings:
                self.chart.validate_postable(p.account)  # raises if bad
        if entry.ref and any(e.ref == entry.ref for e in self.entries):
            self.warnings.append(
                f"entry {entry.entry_id!r} reuses ref {entry.ref!r} — possible "
                f"duplicate transaction, review before trusting totals"
            )
        self.entries.append(entry)
        # Log the event and leg count only — never amounts/descriptions.
        _log.info("posted entry %r (%d legs, status=%s)",
                  entry.entry_id, len(entry.postings), entry.status.value)

    def reverse(self, entry_id: str, reversal_id: str, date: str) -> JournalEntry:
        """Reverse a POSTED entry with an auditable offsetting entry (prompt 4.3).

        The original is marked REVERSED (not deleted); a new POSTED entry with
        negated postings is created and posted. The two net to zero in balances.
        """
        idx = next((i for i, e in enumerate(self.entries)
                    if e.entry_id == entry_id), None)
        if idx is None:
            raise ValueError(f"cannot reverse unknown entry {entry_id!r}")
        original = self.entries[idx]
        if original.status is not EntryStatus.POSTED:
            raise ValueError(
                f"entry {entry_id!r} is {original.status.value}, only POSTED "
                f"entries can be reversed"
            )
        reversing = JournalEntry(
            entry_id=reversal_id,
            date=date,
            description=f"Reversal of {entry_id}: {original.description}",
            postings=tuple(replace(p, amount=-p.amount) for p in original.postings),
            ref=original.ref,
            status=EntryStatus.POSTED,
        )
        self.post(reversing)
        self.entries[idx] = replace(original, status=EntryStatus.REVERSED)
        return reversing

    def _effective(self) -> list[JournalEntry]:
        """Entries that affect statements: POSTED and REVERSED only.

        A REVERSED original stays in because its posted reversing entry negates
        it — dropping it would double-remove. DRAFT entries never count.
        """
        return [e for e in self.entries if e.status is not EntryStatus.DRAFT]

    def balance(self, account: str) -> Decimal:
        """Net balance of one account over statement-affecting entries.

        Signed: debit-positive / credit-negative. DRAFT entries excluded.
        """
        return sum(
            (p.amount for e in self._effective() for p in e.postings
             if p.account == account),
            Decimal(0),
        )

    def is_balanced(self) -> bool:
        """Whole-journal invariant: all signed postings sum to zero.

        Checked over statement-affecting entries (prompt 4.3: drafts excluded).
        """
        return sum(
            (p.amount for e in self._effective() for p in e.postings),
            Decimal(0),
        ) == 0
