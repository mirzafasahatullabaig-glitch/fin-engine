"""General Ledger: account balances derived from posted journal entries
(v1.5.0, prompt Part 4.4 / Part 8.2).

This is the bridge that makes the journal the single source of truth: P&L and
balance sheet read balances from here, never from hand-entered figures.

Sign conventions (prompt 4.4 — stated once, used everywhere):
- A :class:`~fin_engine.journal.Posting` stores a SIGNED amount: debit +,
  credit -. ``Journal.balance(code)`` returns that signed net (debit-positive).
- :func:`account_balance` returns a NORMAL-BALANCE-POSITIVE figure: a
  debit-normal account (asset/expense) with a net debit returns positive; a
  credit-normal account (liability/equity/revenue) with a net credit returns
  positive. This is what statements and the trial balance consume.
- :func:`trial_balance` reports each account in its natural debit/credit column
  using the raw signed net, so total debits must equal total credits.

Dates are ISO ``YYYY-MM-DD`` strings. For that fixed format lexical comparison
equals chronological comparison, so we compare strings directly and avoid
parsing here; Part 6 adds typed period handling on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .accounts import ChartOfAccounts, NormalBalance
from .journal import EntryStatus, Journal
from .models import FORMULA_VERSION


def _signed_net(journal: Journal, code: str,
                start: Optional[str], end: Optional[str]) -> Decimal:
    """Signed (debit-positive) net of postings to ``code`` within [start, end].

    Only statement-affecting entries count (POSTED + REVERSED; DRAFT excluded),
    matching ``Journal._effective``. ``start``/``end`` are inclusive ISO dates;
    ``None`` means unbounded on that side.
    """
    total = Decimal(0)
    for e in journal.entries:
        if e.status is EntryStatus.DRAFT:
            continue
        if start is not None and e.date < start:
            continue
        if end is not None and e.date > end:
            continue
        for p in e.postings:
            if p.account == code:
                total += p.amount
    return total


def account_balance(journal: Journal, chart: ChartOfAccounts, code: str,
                    as_of: Optional[str] = None) -> Decimal:
    """Normal-balance-positive balance of ``code`` as of a date (inclusive).

    Raises ``KeyError`` if the account is unknown — missing accounts are never
    treated as zero (prompt rule 12).
    """
    acct = chart.get(code)  # raises if unknown
    signed = _signed_net(journal, code, start=None, end=as_of)
    # Flip sign so a credit-normal account reads positive when it has a net
    # credit balance.
    return signed if acct.normal_balance is NormalBalance.DEBIT else -signed


@dataclass(frozen=True)
class AccountActivity:
    """Opening / period / closing for one account, normal-balance-positive."""

    code: str
    opening: Decimal
    period_debits: Decimal      # raw debit postings in the period (>= 0)
    period_credits: Decimal     # raw credit postings in the period (>= 0)
    closing: Decimal
    formula_version: str = FORMULA_VERSION


def account_activity(journal: Journal, chart: ChartOfAccounts, code: str,
                    start: str, end: str) -> AccountActivity:
    """Opening (before ``start``), period movement, and closing (through ``end``).

    ``period_debits``/``period_credits`` are raw magnitudes of the signed
    postings within the period, so a reader can see gross movement, not just
    the net. Opening and closing are normal-balance-positive.
    """
    acct = chart.get(code)
    flip = acct.normal_balance is NormalBalance.CREDIT

    # Opening: net of everything strictly before start.
    opening_signed = sum(
        (p.amount for e in journal.entries if e.status is not EntryStatus.DRAFT
         and e.date < start for p in e.postings if p.account == code),
        Decimal(0),
    )
    debits = Decimal(0)
    credits = Decimal(0)
    for e in journal.entries:
        if e.status is EntryStatus.DRAFT or not (start <= e.date <= end):
            continue
        for p in e.postings:
            if p.account != code:
                continue
            if p.amount > 0:
                debits += p.amount
            else:
                credits += -p.amount

    period_signed = debits - credits
    closing_signed = opening_signed + period_signed
    opening = -opening_signed if flip else opening_signed
    closing = -closing_signed if flip else closing_signed
    return AccountActivity(code, opening, debits, credits, closing)


@dataclass(frozen=True)
class TrialBalanceLine:
    code: str
    name: str
    debit: Decimal      # >= 0; this account's balance if it sits on the debit side
    credit: Decimal     # >= 0; ... or the credit side


@dataclass(frozen=True)
class TrialBalance:
    """Trial balance as of a date. ``balanced`` iff total debits == total credits."""

    entity: str
    as_of: Optional[str]
    lines: tuple[TrialBalanceLine, ...]
    total_debits: Decimal
    total_credits: Decimal
    formula_version: str = FORMULA_VERSION

    @property
    def difference(self) -> Decimal:
        return self.total_debits - self.total_credits

    @property
    def balanced(self) -> bool:
        return self.difference == 0


def trial_balance(journal: Journal, chart: ChartOfAccounts,
                  as_of: Optional[str] = None) -> TrialBalance:
    """Trial balance from the GL: every account's net on its natural side.

    A positive signed net (debit) goes in the debit column, negative in the
    credit column. Because every posted entry balances, the column totals must
    be equal — ``balanced`` is the reconciliation check (prompt 8.2).
    """
    lines: list[TrialBalanceLine] = []
    total_debits = Decimal(0)
    total_credits = Decimal(0)
    for acct in chart.accounts():
        signed = _signed_net(journal, acct.code, start=None, end=as_of)
        if signed == 0:
            continue
        if signed > 0:
            lines.append(TrialBalanceLine(acct.code, acct.name, signed, Decimal(0)))
            total_debits += signed
        else:
            lines.append(TrialBalanceLine(acct.code, acct.name, Decimal(0), -signed))
            total_credits += -signed
    return TrialBalance(
        entity=journal.entity, as_of=as_of, lines=tuple(lines),
        total_debits=total_debits, total_credits=total_credits,
    )
