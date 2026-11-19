"""A/B query router (report §4.2 / §4.3).

Classifies a question's intent and routes it to the right handler:

- GENERAL  -> Knowledge Base A (RAG over reference docs): "explain working capital"
- BUSINESS -> the deterministic finance engine over the org's own records:
              "what is our PBT?"
- COMBINED -> both: "is our working capital healthy?" (verified metric compared
              against a reference concept — report §4.3)

The intent classification here is a deterministic keyword rule. The report is
explicit that the router must verify access and pick sources with code; an LLM
may later *propose* an intent, but the authoritative route is decided here, and
business figures always come from the engine, never the model (report §4.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Callable, Optional, Tuple

from .pnl import PnL, calculate_pnl
from .models import Ledger
from .accounts import ChartOfAccounts
from .balance_sheet import BalanceSheet
from .journal import Journal
from .statements import balance_sheet_from_journal, pnl_from_journal
from .rag.pipeline import Answer, KnowledgeBaseA


class Metric(str, Enum):
    """The specific financial metric a business question asks for.

    P&L metrics are served by the P&L; balance-sheet metrics by the balance
    sheet. The router must never answer a BS metric from the P&L (prompt 6.3).
    """

    # P&L
    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"
    EBIT = "ebit"
    PBT = "pbt"
    NET_PROFIT = "net_profit"
    MARGIN = "margin"
    # Balance sheet
    TOTAL_ASSETS = "total_assets"
    TOTAL_LIABILITIES = "total_liabilities"
    EQUITY = "equity"
    WORKING_CAPITAL = "working_capital"
    CURRENT_RATIO = "current_ratio"
    QUICK_RATIO = "quick_ratio"


# Longest/most-specific phrases first so "gross profit" wins over "profit".
_METRIC_PHRASES: list[tuple[str, Metric]] = [
    ("working capital", Metric.WORKING_CAPITAL),
    ("current ratio", Metric.CURRENT_RATIO),
    ("quick ratio", Metric.QUICK_RATIO),
    ("acid test", Metric.QUICK_RATIO),
    ("total assets", Metric.TOTAL_ASSETS),
    ("total liabilities", Metric.TOTAL_LIABILITIES),
    ("gross profit", Metric.GROSS_PROFIT),
    ("profit before tax", Metric.PBT),
    ("pbt", Metric.PBT),
    ("operating profit", Metric.EBIT),
    ("ebit", Metric.EBIT),
    ("net profit", Metric.NET_PROFIT),
    ("margin", Metric.MARGIN),
    ("revenue", Metric.REVENUE),
    ("sales", Metric.REVENUE),
    ("equity", Metric.EQUITY),
    ("assets", Metric.TOTAL_ASSETS),
    ("liabilities", Metric.TOTAL_LIABILITIES),
]

_BALANCE_SHEET_METRICS = {
    Metric.TOTAL_ASSETS, Metric.TOTAL_LIABILITIES, Metric.EQUITY,
    Metric.WORKING_CAPITAL, Metric.CURRENT_RATIO, Metric.QUICK_RATIO,
}


def detect_metric(question: str) -> Optional[Metric]:
    """Return the specific metric a question asks for, or None if unclear."""
    q = question.lower()
    for phrase, metric in _METRIC_PHRASES:
        if phrase in q:
            return metric
    return None


class Intent(str, Enum):
    GENERAL = "general"     # reference knowledge only
    BUSINESS = "business"   # org's own figures only
    COMBINED = "combined"   # both; compare verified figures to reference


# Words that signal the question is about THIS organisation's own figures.
_POSSESSIVE = ("our ", "my ", "we ", "us ", "the company's", "this business")
# Possessive phrases that actually point OUTWARD at general/reference topics,
# not the org's own ledger ("our industry's average margin" is a general Q).
_GENERAL_POSSESSIVE = ("our industry", "our sector", "our market",
                       "our competitors", "my industry", "my sector")
# Words that signal a qualitative judgement needing both figure + reference.
_JUDGEMENT = ("healthy", "good", "bad", "normal", "reasonable", "should we",
              "too high", "too low", "concern", "worrying")
# Words that signal a concrete business metric is being asked for. Kept in step
# with _METRIC_PHRASES (every routable metric phrase) plus cash-flow, so
# classify_intent and detect_metric share one vocabulary.
_METRIC = tuple({p for p, _ in _METRIC_PHRASES} | {
    "profit before tax", "cash flow", "cash-flow",
})


def classify_intent(question: str) -> Intent:
    """Decide where a question should be routed (deterministic).

    BUSINESS (our own figures) requires BOTH a possessive AND a concrete metric,
    so a general question that merely contains "our" (e.g. "our industry's
    average margin") is not misrouted to the private-data path. Outward-pointing
    possessives ("our industry/sector/market") are treated as general outright.
    """
    q = f" {question.lower().strip()} "
    outward = any(p in q for p in _GENERAL_POSSESSIVE)
    about_us = (not outward) and any(p in q for p in _POSSESSIVE)
    judgemental = any(j in q for j in _JUDGEMENT)
    mentions_metric = any(m in q for m in _METRIC)

    # Only our-own-figures questions (possessive + a metric) touch the ledger.
    business = about_us and mentions_metric

    if judgemental and business:
        return Intent.COMBINED
    if business:
        return Intent.BUSINESS
    return Intent.GENERAL


@dataclass(frozen=True)
class RouteResult:
    """The outcome of routing one question.

    ``metric`` and ``value`` record WHICH metric was computed and its exact
    value, so a caller (and a test) can confirm the router ran the right
    calculation rather than substituting P&L (prompt 6.3). ``value`` is None for
    ratios with no denominator and for non-numeric answers.
    """

    intent: Intent
    answer: str
    pnl: Optional[PnL] = None           # present for P&L-metric answers
    bs: Optional[BalanceSheet] = None   # present for balance-sheet-metric answers
    rag: Optional[Answer] = None        # present for GENERAL/COMBINED
    metric: Optional[Metric] = None
    value: Optional[Decimal] = None
    citations: list[str] = field(default_factory=list)


# Accounting data for the current entity: (journal, chart, period_label,
# as_of_date). A P&L uses period+the journal's date span; a balance sheet uses
# as_of. Returning None means no business data (router reports the gap).
AccountingProvider = Callable[[], Optional[Tuple[Journal, ChartOfAccounts, str, str]]]


@dataclass
class QueryRouter:
    """Routes questions to the finance engine and/or Knowledge Base A.

    Two providers, both call-time callables so access/period checks happen per
    request (report's "check permission before retrieval"):

    - ``accounting_provider`` (v1.5.0, preferred): returns
      ``(journal, chart, period_label, as_of_date)`` so the router can derive
      ANY metric from journal balances and dispatch to the correct calculation.
    - ``ledger_provider`` (legacy): returns a pre-built P&L ``Ledger``. Used
      only when no accounting_provider is set, and only serves P&L metrics.

    Either returning ``None`` means "no business data" and the router reports
    the gap instead of inventing figures.
    """

    kb_a: KnowledgeBaseA
    ledger_provider: Callable[[], Optional[Ledger]] = lambda: None
    accounting_provider: AccountingProvider = lambda: None

    def ask(self, question: str) -> RouteResult:
        intent = classify_intent(question)

        if intent is Intent.GENERAL:
            ans = self.kb_a.answer(question)
            return RouteResult(intent, ans.text, rag=ans,
                               citations=ans.citations())

        metric = detect_metric(question)
        core = self._answer_metric(intent, metric, question)
        if intent is not Intent.COMBINED or core.pnl is core.bs is None:
            return core

        # COMBINED: append reference context from KB-A to the verified figures.
        rag = self.kb_a.answer(question)
        text = (f"{core.answer}\n\nReference context: {rag.text}"
                if rag.grounded else core.answer)
        return RouteResult(intent, text, pnl=core.pnl, bs=core.bs, rag=rag,
                           metric=core.metric, value=core.value,
                           citations=rag.citations())

    def _answer_metric(self, intent: Intent, metric: Optional[Metric],
                       question: str) -> RouteResult:
        """Dispatch to the balance sheet or P&L for the detected metric."""
        acct = self.accounting_provider()

        # Balance-sheet metrics require the accounting provider (journal+chart).
        if metric in _BALANCE_SHEET_METRICS:
            if acct is None:
                return RouteResult(intent, _no_data_msg("balance sheet"),
                                   metric=metric)
            journal, chart, _period, as_of = acct
            bs = balance_sheet_from_journal(journal, chart, as_of=as_of)
            text, value = _summarise_bs_metric(bs, metric, as_of)
            return RouteResult(intent, text, bs=bs, metric=metric, value=value)

        # Otherwise a P&L metric (or an unclassified business question -> full
        # P&L summary, never a balance-sheet figure).
        if acct is not None:
            journal, chart, period, _as_of = acct
            pnl = pnl_from_journal(journal, chart, period=period)
        else:
            ledger = self.ledger_provider()
            if ledger is None:
                return RouteResult(intent, _no_data_msg("ledger"), metric=metric)
            pnl = calculate_pnl(ledger)

        text, value = _summarise_pnl_metric(pnl, metric)
        return RouteResult(intent, text, pnl=pnl, metric=metric, value=value)


def _no_data_msg(what: str) -> str:
    return (f"No business records are available to answer that. Load a "
            f"{what} for the entity and period first.")


def _summarise_pnl_metric(p: PnL, metric: Optional[Metric]) -> Tuple[str, Optional[Decimal]]:
    """Text + exact value for a P&L metric (no LLM)."""
    pref = (f"For {p.entity} {p.period} (verified, formula v{p.formula_version}): ")
    singles = {
        Metric.REVENUE: ("revenue", p.revenue),
        Metric.GROSS_PROFIT: ("gross profit", p.gross_profit),
        Metric.EBIT: ("EBIT (operating profit)", p.ebit),
        Metric.PBT: ("PBT", p.pbt),
        Metric.NET_PROFIT: ("net profit", p.net_profit),
    }
    if metric in singles:
        label, val = singles[metric]
        return f"{pref}{label} {val:,}.", val
    if metric is Metric.MARGIN:
        m = p.margins()
        return (f"{pref}gross margin {m['gross']:.2%}, operating {m['operating']:.2%}, "
                f"net {m['net']:.2%}."), None
    # Unclassified business question: full summary, no single value.
    return (f"{pref}revenue {p.revenue:,}, gross profit {p.gross_profit:,}, "
            f"EBIT {p.ebit:,}, PBT {p.pbt:,}, net profit {p.net_profit:,}."), None


def _summarise_bs_metric(bs: BalanceSheet, metric: Metric,
                         as_of: str) -> Tuple[str, Optional[Decimal]]:
    """Text + exact value for a balance-sheet metric (no LLM)."""
    pref = f"For {bs.entity} as of {as_of} (verified, formula v{bs.formula_version}): "
    warn = ""
    w = bs.validation_warnings()
    if w:
        warn = " [validation: " + "; ".join(w) + "]"
    if metric is Metric.TOTAL_ASSETS:
        return f"{pref}total assets {bs.total_assets:,}.{warn}", bs.total_assets
    if metric is Metric.TOTAL_LIABILITIES:
        return f"{pref}total liabilities {bs.total_liabilities:,}.{warn}", bs.total_liabilities
    if metric is Metric.EQUITY:
        return f"{pref}equity {bs.equity:,}.{warn}", bs.equity
    if metric is Metric.WORKING_CAPITAL:
        return f"{pref}working capital {bs.working_capital:,}.{warn}", bs.working_capital
    if metric is Metric.CURRENT_RATIO:
        r = bs.current_ratio
        if r is None:
            return f"{pref}current ratio is undefined (no current liabilities).{warn}", None
        return f"{pref}current ratio {r:.2f}.{warn}", r
    if metric is Metric.QUICK_RATIO:
        r = bs.quick_ratio
        if r is None:
            return f"{pref}quick ratio is undefined (no current liabilities).{warn}", None
        return f"{pref}quick ratio {r:.2f}.{warn}", r
    return f"{pref}(metric not computed).{warn}", None


def _summarise_pnl(p: PnL) -> str:
    """Plain-text summary of verified figures (no LLM; exact numbers)."""
    return (
        f"For {p.entity} {p.period} (verified by the finance engine, formula "
        f"v{p.formula_version}): revenue {p.revenue:,}, gross profit "
        f"{p.gross_profit:,}, EBIT {p.ebit:,}, PBT {p.pbt:,}, net profit "
        f"{p.net_profit:,}."
    )
