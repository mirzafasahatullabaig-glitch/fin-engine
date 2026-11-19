"""Core data structures and shared constants.

Money is represented with :class:`decimal.Decimal`, never float, so that
sums and comparisons are exact. The engine never does binary-float arithmetic
on monetary values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

# Bump when any formula in this package changes. Stored alongside results so a
# report can state which formula version produced it (report §8.2).
FORMULA_VERSION = "1.0.0"


class AccountGroup(str, Enum):
    """P&L / balance-sheet group a ledger line belongs to."""

    REVENUE = "revenue"
    COGS = "cogs"
    OPERATING_EXPENSE = "operating_expense"
    OTHER_INCOME = "other_income"          # non-operating income
    FINANCE_COST = "finance_cost"          # interest and other finance costs
    OTHER_EXPENSE = "other_expense"        # non-operating, non-finance
    TAX = "tax"                            # income tax expense
    # Balance-sheet groups (not used by the P&L sum, kept for classification)
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"


class CashFlowCategory(str, Enum):
    """Statement-of-cash-flows section."""

    OPERATING = "operating"
    INVESTING = "investing"
    FINANCING = "financing"
    NONE = "none"  # no cash movement (e.g. an accrual-only entry)


def money(value) -> Decimal:
    """Coerce a value to a Decimal money amount.

    Accepts int, str or Decimal. Rejects float to avoid silent binary-rounding
    error — pass money as a string (``"5000.00"``) or Decimal.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise TypeError("money value must be a number, not bool")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(
        f"money value must be int, str or Decimal, not {type(value).__name__}; "
        "pass floats as strings to keep amounts exact"
    )


@dataclass(frozen=True)
class LedgerLine:
    """One classified amount in a period's ledger.

    ``amount`` is always a positive magnitude; the account group determines
    whether it adds to income or expense. This keeps inputs unambiguous.
    """

    group: AccountGroup
    amount: Decimal
    description: str = ""
    account_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", money(self.amount))
        if self.amount < 0:
            raise ValueError(
                f"ledger line amounts are magnitudes and must be >= 0, "
                f"got {self.amount} for {self.group.value!r}"
            )


@dataclass
class Ledger:
    """A set of ledger lines for one entity and reporting period."""

    entity: str
    period: str  # e.g. "2026-11" or "2026-Q4" — opaque label, used for reporting
    lines: list[LedgerLine] = field(default_factory=list)

    def total(self, group: AccountGroup) -> Decimal:
        return sum((l.amount for l in self.lines if l.group is group), Decimal(0))
