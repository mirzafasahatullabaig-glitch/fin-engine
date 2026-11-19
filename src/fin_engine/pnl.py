"""Profit & Loss calculation (report §7.2 / §8.3 ``calculate_pnl``).

This module exists specifically to fix the recurring LLM error the report
documented: Granite returned PBT = EBIT, ignoring interest expense (§7.1).
Here PBT = EBIT + other income - finance costs - other expenses, always.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import AccountGroup, FORMULA_VERSION, Ledger


@dataclass(frozen=True)
class PnL:
    """A computed P&L statement. All values are exact Decimals."""

    entity: str
    period: str
    revenue: Decimal
    cogs: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    ebit: Decimal                # operating profit
    other_income: Decimal
    finance_costs: Decimal
    other_expenses: Decimal
    pbt: Decimal                 # profit before tax
    tax: Decimal
    net_profit: Decimal
    formula_version: str = FORMULA_VERSION

    def margins(self) -> dict[str, Decimal]:
        """Gross / operating / PBT / net margins as fractions of revenue.

        Returns zeros when revenue is zero rather than dividing by zero.
        """
        if self.revenue == 0:
            z = Decimal(0)
            return {"gross": z, "operating": z, "pbt": z, "net": z}
        return {
            "gross": self.gross_profit / self.revenue,
            "operating": self.ebit / self.revenue,
            "pbt": self.pbt / self.revenue,
            "net": self.net_profit / self.revenue,
        }


def calculate_pnl(ledger: Ledger) -> PnL:
    """Compute a P&L from a classified ledger using versioned formulas.

    Formula chain (report §7.2):
        gross_profit = revenue - COGS
        EBIT         = gross_profit - operating_expenses
        PBT          = EBIT + other_income - finance_costs - other_expenses
        net_profit   = PBT - tax
    """
    revenue = ledger.total(AccountGroup.REVENUE)
    cogs = ledger.total(AccountGroup.COGS)
    opex = ledger.total(AccountGroup.OPERATING_EXPENSE)
    other_income = ledger.total(AccountGroup.OTHER_INCOME)
    finance_costs = ledger.total(AccountGroup.FINANCE_COST)
    other_expenses = ledger.total(AccountGroup.OTHER_EXPENSE)
    tax = ledger.total(AccountGroup.TAX)

    gross_profit = revenue - cogs
    ebit = gross_profit - opex
    pbt = ebit + other_income - finance_costs - other_expenses
    net_profit = pbt - tax

    return PnL(
        entity=ledger.entity,
        period=ledger.period,
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        operating_expenses=opex,
        ebit=ebit,
        other_income=other_income,
        finance_costs=finance_costs,
        other_expenses=other_expenses,
        pbt=pbt,
        tax=tax,
        net_profit=net_profit,
    )
