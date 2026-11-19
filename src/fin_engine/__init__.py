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
from .router import (
    QueryRouter, RouteResult, Intent, Metric, classify_intent, detect_metric,
)
from .journal import Journal, JournalEntry, Posting, EntryStatus
from .balance_sheet import BalanceSheet
from .accounts import (
    Account, AccountType, ChartOfAccounts, NormalBalance, StatementCategory,
    starter_chart,
)
from .ledger_gl import (
    account_activity, account_balance, trial_balance, TrialBalance,
)
from .statements import balance_sheet_from_journal, pnl_from_journal
from .periods import PeriodRange, parse_date, resolve_period, date_in_period
from .reconciliation import reconcile, ReconciliationReport
from .advisor import advise, Advice
from .config import Config, Health, health_check
from .logging_setup import configure_logging, get_logger

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
    "QueryRouter",
    "RouteResult",
    "Intent",
    "Metric",
    "classify_intent",
    "detect_metric",
    "Journal",
    "JournalEntry",
    "Posting",
    "EntryStatus",
    "BalanceSheet",
    "Account",
    "AccountType",
    "ChartOfAccounts",
    "NormalBalance",
    "StatementCategory",
    "starter_chart",
    "account_activity",
    "account_balance",
    "trial_balance",
    "TrialBalance",
    "balance_sheet_from_journal",
    "pnl_from_journal",
    "PeriodRange",
    "parse_date",
    "resolve_period",
    "date_in_period",
    "reconcile",
    "ReconciliationReport",
    "advise",
    "Advice",
    "Config",
    "Health",
    "health_check",
    "configure_logging",
    "get_logger",
]
