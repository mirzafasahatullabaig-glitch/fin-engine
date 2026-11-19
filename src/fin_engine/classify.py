"""Deterministic, rule-based transaction classification (report §7.4 / §8.3).

Each transaction gets TWO labels, not one: its P&L/balance-sheet group and its
cash-flow category. The report showed a single mutually-exclusive label is
insufficient (a bank loan is both a liability and a financing inflow).

This is a keyword baseline the LLM can propose *into*, but the result returned
to a user is this deterministic output plus a confidence flag — the model never
decides the authoritative classification on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import AccountGroup, CashFlowCategory

# Ordered rules: (keywords, account group, cash-flow category).
# Keywords match on WORD BOUNDARIES, not substrings, so "sale" no longer
# matches "wholesale". More specific rules come first; if two DIFFERENT rules
# both match, the transaction is flagged for review rather than silently taking
# the first (report §8.3: abstain/review when uncertain).
_RULES: list[tuple[tuple[str, ...], AccountGroup, CashFlowCategory]] = [
    (("loan received", "loan disbursed", "borrowing", "loan proceeds"),
     AccountGroup.LIABILITY, CashFlowCategory.FINANCING),
    (("loan repayment", "repay loan", "principal repayment"),
     AccountGroup.LIABILITY, CashFlowCategory.FINANCING),
    (("interest paid", "interest expense", "finance cost"),
     AccountGroup.FINANCE_COST, CashFlowCategory.FINANCING),
    # Capital assets -> investing. Broad coverage so "office building" lands here,
    # not in operating expenses.
    (("machinery", "equipment", "vehicle", "plant", "fixed asset", "property",
      "building", "land", "furniture", "computer hardware"),
     AccountGroup.ASSET, CashFlowCategory.INVESTING),
    (("dividend paid",),
     AccountGroup.EQUITY, CashFlowCategory.FINANCING),
    (("rent", "electricity", "utility", "utilities", "salary", "salaries",
      "wages", "payroll", "marketing", "advertising", "insurance premium",
      "office supplies", "stationery"),
     AccountGroup.OPERATING_EXPENSE, CashFlowCategory.OPERATING),
    (("purchase of goods", "inventory purchase", "raw material", "cogs",
      "cost of goods"),
     AccountGroup.COGS, CashFlowCategory.OPERATING),
    (("sale", "sales", "revenue", "invoice issued", "service income"),
     AccountGroup.REVENUE, CashFlowCategory.OPERATING),
    (("income tax", "tax paid"),
     AccountGroup.TAX, CashFlowCategory.OPERATING),
]

# Words that signal money coming IN. If present with an expense-type keyword
# (e.g. "insurance claim RECEIVED"), the sign is ambiguous -> force review
# rather than booking income as an expense.
_INFLOW_HINTS = ("received", "refund", "rebate", "claim", "recovery",
                 "reimbursement", "credit note")


def _matches(keyword: str, text: str) -> bool:
    """Whole-word / phrase match, case-insensitive. 'sale' != 'wholesale'."""
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None


@dataclass(frozen=True)
class Classification:
    """Dual-dimension classification plus a review flag."""

    group: AccountGroup
    cash_flow: CashFlowCategory
    confidence: str          # "high" | "low"
    matched_rule: str        # keyword that matched, "" if none
    needs_review: bool


def classify_transaction(description: str) -> Classification:
    """Classify a transaction description into (group, cash-flow category).

    Rules match on word boundaries. A result is flagged for review (low
    confidence) when: nothing matched, more than one DIFFERENT rule matched
    (ambiguous), or an expense-type match co-occurs with an inflow hint such as
    "received"/"claim" (sign ambiguous). The report requires abstaining when
    uncertain rather than guessing (§8.3, §11.1).
    """
    text = (description or "").lower()

    # Collect every distinct rule that matches (by resulting group/cash-flow).
    matches: list[tuple[AccountGroup, CashFlowCategory, str]] = []
    for keywords, group, cash_flow in _RULES:
        for kw in keywords:
            if _matches(kw, text):
                matches.append((group, cash_flow, kw))
                break  # one keyword per rule is enough

    if not matches:
        return Classification(
            group=AccountGroup.OPERATING_EXPENSE,  # placeholder, do not trust
            cash_flow=CashFlowCategory.NONE,
            confidence="low",
            matched_rule="",
            needs_review=True,
        )

    group, cash_flow, kw = matches[0]  # highest-priority rule
    distinct = {(g, c) for g, c, _ in matches}
    ambiguous_rules = len(distinct) > 1

    # Income flowing in but matched as an expense? Sign is ambiguous.
    inflow_conflict = (
        group is AccountGroup.OPERATING_EXPENSE
        and any(_matches(h, text) for h in _INFLOW_HINTS)
    )

    needs_review = ambiguous_rules or inflow_conflict
    return Classification(
        group=group,
        cash_flow=cash_flow,
        confidence="low" if needs_review else "high",
        matched_rule=kw,
        needs_review=needs_review,
    )
