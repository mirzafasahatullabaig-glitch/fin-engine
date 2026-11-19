"""Reconciliation: accounting invariants over the unified engine (v1.5.0, Part 8).

Runs the checks that must hold if the journal, general ledger and derived
statements are consistent, and returns a structured report. A failed check is
recorded as failed — never silently passed (prompt 8.4 / rule 14).

Checks (prompt 8.1 / 8.3):
  J1  every statement-affecting entry balances (debits == credits)
  J2  every posting references a known, active account (when a chart is set)
  T1  trial balance balances (total debits == total credits)
  B1  balance-sheet identity: assets == liabilities + equity
  B2  working capital == current assets - current liabilities
  B3  current ratio == current assets / current liabilities (or both undefined)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .accounts import ChartOfAccounts
from .journal import EntryStatus, Journal
from .ledger_gl import trial_balance
from .models import FORMULA_VERSION
from .statements import balance_sheet_from_journal


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ReconciliationReport:
    entity: str
    as_of: str
    checks: list[Check] = field(default_factory=list)
    formula_version: str = FORMULA_VERSION

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(name, passed, detail))


def reconcile(journal: Journal, chart: ChartOfAccounts,
              as_of: str) -> ReconciliationReport:
    """Run all invariants and return a structured report (prompt 8.4)."""
    rep = ReconciliationReport(entity=journal.entity, as_of=as_of)

    # J1: every statement-affecting entry balances. (Construction already
    # enforces this, but a reconciliation re-checks independently.)
    for e in journal.entries:
        if e.status is EntryStatus.DRAFT:
            continue
        imbalance = sum((p.amount for p in e.postings), Decimal(0))
        rep.add(f"J1:entry_balances:{e.entry_id}", imbalance == 0,
                "" if imbalance == 0 else f"off by {imbalance}")

    # J2: postings reference known, active accounts.
    for e in journal.entries:
        if e.status is EntryStatus.DRAFT:
            continue
        for p in e.postings:
            try:
                chart.validate_postable(p.account)
                ok, detail = True, ""
            except (KeyError, ValueError) as exc:
                ok, detail = False, str(exc)
            rep.add(f"J2:valid_account:{e.entry_id}:{p.account}", ok, detail)

    # T1: trial balance balances.
    tb = trial_balance(journal, chart, as_of=as_of)
    rep.add("T1:trial_balance", tb.balanced,
            "" if tb.balanced else f"difference {tb.difference}")

    # B1/B2/B3: balance-sheet invariants.
    bs = balance_sheet_from_journal(journal, chart, as_of=as_of)
    identity_gap = bs.total_assets - (bs.total_liabilities + bs.equity)
    rep.add("B1:accounting_identity", identity_gap == 0,
            "" if identity_gap == 0 else f"assets - (liab+equity) = {identity_gap}")

    wc_ok = bs.working_capital == bs.current_assets - bs.current_liabilities
    rep.add("B2:working_capital", wc_ok)

    expected_cr = (None if bs.current_liabilities == 0
                   else bs.current_assets / bs.current_liabilities)
    rep.add("B3:current_ratio", bs.current_ratio == expected_cr)

    return rep
