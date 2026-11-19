"""Balance sheet and liquidity ratios (report §2.C items 2, 4, 5, 6).

Profit margins (gross/operating/net) already live on :meth:`PnL.margins` and are
not duplicated here. This module covers the balance-sheet side: the accounting
identity (Assets = Liabilities + Equity) and the liquidity ratios computed from
current assets/liabilities.

All arithmetic is exact Decimal. Ratios return ``None`` when the denominator is
zero rather than inventing a number or raising — a report can then say "n/a
(no current liabilities)" instead of showing a fabricated or crashing value.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .models import FORMULA_VERSION, money


@dataclass(frozen=True)
class BalanceSheet:
    """A balance sheet at a point in time. Amounts are Decimal magnitudes.

    ``current_*`` are the liquid subset used for liquidity ratios; they must not
    exceed their totals. ``inventory`` is the illiquid part of current assets,
    excluded from the quick ratio.
    """

    entity: str
    as_of: str
    current_assets: Decimal
    non_current_assets: Decimal
    current_liabilities: Decimal
    non_current_liabilities: Decimal
    equity: Decimal
    inventory: Decimal = Decimal(0)
    formula_version: str = FORMULA_VERSION

    def __post_init__(self) -> None:
        for name in ("current_assets", "non_current_assets",
                     "current_liabilities", "non_current_liabilities",
                     "equity", "inventory"):
            object.__setattr__(self, name, money(getattr(self, name)))
        if self.inventory > self.current_assets:
            raise ValueError(
                f"inventory {self.inventory} exceeds current assets "
                f"{self.current_assets}"
            )

    @property
    def total_assets(self) -> Decimal:
        return self.current_assets + self.non_current_assets

    @property
    def total_liabilities(self) -> Decimal:
        return self.current_liabilities + self.non_current_liabilities

    @property
    def working_capital(self) -> Decimal:
        """Current assets - current liabilities (report §2.C)."""
        return self.current_assets - self.current_liabilities

    @property
    def current_ratio(self) -> Optional[Decimal]:
        """Current assets / current liabilities; None if no liabilities."""
        if self.current_liabilities == 0:
            return None
        return self.current_assets / self.current_liabilities

    @property
    def quick_ratio(self) -> Optional[Decimal]:
        """(Current assets - inventory) / current liabilities; None if no liab."""
        if self.current_liabilities == 0:
            return None
        return (self.current_assets - self.inventory) / self.current_liabilities

    def validation_warnings(self) -> list[str]:
        """Accounting checks surfaced to every report (report §2.D).

        The balance-sheet identity Assets = Liabilities + Equity must hold.
        Returns a (possibly empty) list; callers show it, never hide it.
        """
        warnings: list[str] = []
        identity_gap = self.total_assets - (self.total_liabilities + self.equity)
        if identity_gap != 0:
            warnings.append(
                f"balance sheet does not balance: assets {self.total_assets} "
                f"!= liabilities + equity {self.total_liabilities + self.equity} "
                f"(off by {identity_gap})"
            )
        if self.working_capital < 0:
            warnings.append(
                f"negative working capital ({self.working_capital}): current "
                f"liabilities exceed current assets"
            )
        return warnings
