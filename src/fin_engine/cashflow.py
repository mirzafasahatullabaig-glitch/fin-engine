"""Cash-flow summary (report §8.3 ``calculate_cash_flow``).

Splits cash movements into operating / investing / financing, which is the
dual-classification dimension the report calls out (§7.4): a bank loan is a
*financing inflow* even though on the P&L/balance-sheet side it is a liability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import CashFlowCategory, FORMULA_VERSION, money


@dataclass(frozen=True)
class CashMovement:
    """A single cash movement. ``amount`` is signed: + inflow, - outflow."""

    category: CashFlowCategory
    amount: Decimal
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", money(self.amount))


@dataclass(frozen=True)
class CashFlow:
    """Computed cash-flow summary. Net = operating + investing + financing."""

    entity: str
    period: str
    operating: Decimal
    investing: Decimal
    financing: Decimal
    net_change: Decimal
    formula_version: str = FORMULA_VERSION


def calculate_cash_flow(
    entity: str, period: str, movements: list[CashMovement]
) -> CashFlow:
    """Sum signed cash movements by category and return the net change."""
    totals = {c: Decimal(0) for c in CashFlowCategory}
    for m in movements:
        totals[m.category] += m.amount

    operating = totals[CashFlowCategory.OPERATING]
    investing = totals[CashFlowCategory.INVESTING]
    financing = totals[CashFlowCategory.FINANCING]

    return CashFlow(
        entity=entity,
        period=period,
        operating=operating,
        investing=investing,
        financing=financing,
        net_change=operating + investing + financing,
    )
