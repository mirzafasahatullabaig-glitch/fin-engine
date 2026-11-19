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
from enum import Enum
from typing import Callable, Optional

from .pnl import PnL, calculate_pnl
from .models import Ledger
from .rag.pipeline import Answer, KnowledgeBaseA


class Intent(str, Enum):
    GENERAL = "general"     # reference knowledge only
    BUSINESS = "business"   # org's own figures only
    COMBINED = "combined"   # both; compare verified figures to reference


# Words that signal the question is about THIS organisation's own figures.
_POSSESSIVE = ("our ", "my ", "we ", "us ", "the company's", "this business")
# Words that signal a qualitative judgement needing both figure + reference.
_JUDGEMENT = ("healthy", "good", "bad", "normal", "reasonable", "should we",
              "too high", "too low", "concern", "worrying")
# Words that signal a concrete business metric is being asked for.
_METRIC = ("pbt", "profit before tax", "ebit", "operating profit", "gross profit",
           "net profit", "revenue", "cash flow", "cash-flow", "working capital",
           "margin")


def classify_intent(question: str) -> Intent:
    """Decide where a question should be routed (deterministic)."""
    q = f" {question.lower().strip()} "
    about_us = any(p in q for p in _POSSESSIVE)
    judgemental = any(j in q for j in _JUDGEMENT)
    mentions_metric = any(m in q for m in _METRIC)

    if judgemental and (about_us or mentions_metric):
        return Intent.COMBINED
    if about_us:
        return Intent.BUSINESS
    return Intent.GENERAL


@dataclass(frozen=True)
class RouteResult:
    """The outcome of routing one question."""

    intent: Intent
    answer: str
    pnl: Optional[PnL] = None           # present for BUSINESS/COMBINED
    rag: Optional[Answer] = None        # present for GENERAL/COMBINED
    citations: list[str] = field(default_factory=list)


@dataclass
class QueryRouter:
    """Routes questions to the finance engine and/or Knowledge Base A.

    ``ledger_provider`` returns the Ledger for the current entity/period. It is
    a callable (not a fixed Ledger) so access control / period selection can be
    enforced at call time, per the report's "check permission before retrieval"
    rule. Returning ``None`` means "no business data available" and the router
    reports the gap instead of inventing figures.
    """

    kb_a: KnowledgeBaseA
    ledger_provider: Callable[[], Optional[Ledger]] = lambda: None

    def ask(self, question: str) -> RouteResult:
        intent = classify_intent(question)

        if intent is Intent.GENERAL:
            ans = self.kb_a.answer(question)
            return RouteResult(intent, ans.text, rag=ans,
                               citations=ans.citations())

        # BUSINESS or COMBINED need the org's figures.
        ledger = self.ledger_provider()
        if ledger is None:
            return RouteResult(
                intent,
                "No business records are available to answer that. Load a "
                "ledger for the entity and period first.",
            )
        pnl = calculate_pnl(ledger)

        if intent is Intent.BUSINESS:
            return RouteResult(intent, _summarise_pnl(pnl), pnl=pnl)

        # COMBINED: verified figures + reference context from KB-A.
        rag = self.kb_a.answer(question)
        text = (
            f"{_summarise_pnl(pnl)}\n\n"
            f"Reference context: {rag.text}" if rag.grounded
            else _summarise_pnl(pnl)
        )
        return RouteResult(intent, text, pnl=pnl, rag=rag,
                           citations=rag.citations())


def _summarise_pnl(p: PnL) -> str:
    """Plain-text summary of verified figures (no LLM; exact numbers)."""
    return (
        f"For {p.entity} {p.period} (verified by the finance engine, formula "
        f"v{p.formula_version}): revenue {p.revenue:,}, gross profit "
        f"{p.gross_profit:,}, EBIT {p.ebit:,}, PBT {p.pbt:,}, net profit "
        f"{p.net_profit:,}."
    )
