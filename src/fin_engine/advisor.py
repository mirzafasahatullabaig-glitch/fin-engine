"""Advisory layer: LLM judgement over ENGINE-VERIFIED figures (v1.5.1).

The division of labour that makes advice trustworthy:
  1. The engine computes every number deterministically (never the LLM).
  2. RAG retrieves relevant guidance from the user's ingested decision docs.
  3. The LLM reasons over (verified numbers + retrieved guidance) to recommend
     an action — it may interpret, never recompute or invent figures.

The verified numbers are passed as facts the model is told NOT to change, and
the caller shows them separately, so the user always sees fact vs. opinion
(prompt rule: no LLM performs authoritative arithmetic).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

from .accounts import ChartOfAccounts
from .balance_sheet import BalanceSheet
from .journal import Journal
from .pnl import PnL
from .statements import balance_sheet_from_journal, pnl_from_journal

Generator = Callable[[str], str]


def _snapshot(pnl: PnL, bs: BalanceSheet) -> dict[str, object]:
    """The verified figures the advice must be grounded in."""
    cr = bs.current_ratio
    qr = bs.quick_ratio
    return {
        "revenue": pnl.revenue,
        "gross_profit": pnl.gross_profit,
        "ebit": pnl.ebit,
        "pbt": pnl.pbt,
        "net_profit": pnl.net_profit,
        "total_assets": bs.total_assets,
        "total_liabilities": bs.total_liabilities,
        "equity": bs.equity,
        "working_capital": bs.working_capital,
        "current_ratio": "n/a" if cr is None else round(cr, 2),
        "quick_ratio": "n/a" if qr is None else round(qr, 2),
    }


def _build_prompt(question: str, figures: dict, guidance: str) -> str:
    facts = "\n".join(f"  - {k}: {v}" for k, v in figures.items())
    guidance_block = guidance.strip() or "(no specific guidance retrieved)"
    return (
        "You are a cautious finance advisor. Use ONLY the verified figures and "
        "the guidance below. Do NOT recompute, change, or invent any number; "
        "treat every figure as fixed fact. If the figures are insufficient to "
        "answer, say so.\n\n"
        f"VERIFIED FIGURES (computed by the finance engine, authoritative):\n{facts}\n\n"
        f"RELEVANT GUIDANCE (from the company's own decision notes):\n{guidance_block}\n\n"
        f"QUESTION: {question}\n\n"
        "Give a short, concrete recommendation grounded in the figures above. "
        "Reference the specific figures that drive your advice."
    )


@dataclass(frozen=True)
class Advice:
    """An advisory result: the model's recommendation plus the facts behind it."""

    question: str
    figures: dict
    recommendation: str
    citations: list[str] = field(default_factory=list)
    grounded: bool = True  # False when no engine data was available


def advise(question: str, journal: Journal, chart: ChartOfAccounts,
           period: str, as_of: str, kb_a, generate: Generator,
           k: int = 3) -> Advice:
    """Produce grounded business advice (prompt-style separation of fact/opinion).

    ``kb_a`` is a KnowledgeBaseA (for retrieval); ``generate`` turns a prompt
    into text (e.g. the project's granite4.2:8b caller). Numbers come from the
    engine, so the model cannot fabricate them.
    """
    pnl = pnl_from_journal(journal, chart, period=period)
    bs = balance_sheet_from_journal(journal, chart, as_of=as_of)
    figures = _snapshot(pnl, bs)

    # Retrieve guidance from the user's ingested decision docs (may be empty).
    retrieved = kb_a.retrieve(question, k=k)
    guidance = "\n".join(f"- {r.chunk.text}" for r in retrieved)
    citations: list[str] = []
    for r in retrieved:
        if r.chunk.source not in citations:
            citations.append(r.chunk.source)

    recommendation = generate(_build_prompt(question, figures, guidance))
    return Advice(question, figures, recommendation.strip(), citations)
