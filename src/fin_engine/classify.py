"""Deterministic, rule-based transaction classification (report §7.4 / §8.3).

Each transaction gets TWO labels, not one: its P&L/balance-sheet group and its
cash-flow category. The report showed a single mutually-exclusive label is
insufficient (a bank loan is both a liability and a financing inflow).

This is a keyword baseline the LLM can propose *into*, but the result returned
to a user is this deterministic output plus a confidence flag — the model never
decides the authoritative classification on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AccountGroup, CashFlowCategory

# Ordered rules: (keywords, account group, cash-flow category).
# First matching rule wins, so put more specific rules first.
_RULES: list[tuple[tuple[str, ...], AccountGroup, CashFlowCategory]] = [
    (("loan received", "loan disbursed", "borrowing"),
     AccountGroup.LIABILITY, CashFlowCategory.FINANCING),
    (("loan repayment", "repay loan", "principal repayment"),
     AccountGroup.LIABILITY, CashFlowCategory.FINANCING),
    (("interest paid", "interest expense", "finance cost"),
     AccountGroup.FINANCE_COST, CashFlowCategory.FINANCING),
    (("machinery", "equipment", "vehicle", "plant", "fixed asset", "property"),
     AccountGroup.ASSET, CashFlowCategory.INVESTING),
    (("dividend paid",),
     AccountGroup.EQUITY, CashFlowCategory.FINANCING),
    (("rent", "electricity", "utility", "salary", "salaries", "wages",
      "marketing", "advertising", "insurance", "office"),
     AccountGroup.OPERATING_EXPENSE, CashFlowCategory.OPERATING),
    (("purchase of goods", "inventory purchase", "raw material", "cogs",
      "cost of goods"),
     AccountGroup.COGS, CashFlowCategory.OPERATING),
    (("sale", "sales", "revenue", "invoice issued", "service income"),
     AccountGroup.REVENUE, CashFlowCategory.OPERATING),
    (("income tax", "tax paid"),
     AccountGroup.TAX, CashFlowCategory.OPERATING),
]


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

    Unmatched descriptions return a low-confidence result flagged for review
    rather than a guessed category — the report requires abstaining when
    uncertain (§8.3, §11.1).
    """
    text = (description or "").lower()
    for keywords, group, cash_flow in _RULES:
        for kw in keywords:
            if kw in text:
                return Classification(
                    group=group,
                    cash_flow=cash_flow,
                    confidence="high",
                    matched_rule=kw,
                    needs_review=False,
                )
    return Classification(
        group=AccountGroup.OPERATING_EXPENSE,  # placeholder, do not trust
        cash_flow=CashFlowCategory.NONE,
        confidence="low",
        matched_rule="",
        needs_review=True,
    )
