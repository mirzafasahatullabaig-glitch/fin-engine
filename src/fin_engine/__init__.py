"""fin-engine: deterministic financial calculation and verification engine.

The LLM is a language/orchestration layer only. Every authoritative number
(totals, balances, P&L, cash-flow classification) is computed here, in code,
with versioned formulas and golden tests — never by the model.

See the project report, sections 8 and 12.3.
"""

from .pnl import calculate_pnl, PnL
from .cashflow import calculate_cash_flow, CashFlow
from .classify import classify_transaction, Classification
from .models import Ledger, LedgerLine, FORMULA_VERSION

__all__ = [
    "calculate_pnl",
    "PnL",
    "calculate_cash_flow",
    "CashFlow",
    "classify_transaction",
    "Classification",
    "Ledger",
    "LedgerLine",
    "FORMULA_VERSION",
]
