"""A/B query router tests (report §4.3). Offline — fake embedder + generator."""

from decimal import Decimal

import pytest

from fin_engine import QueryRouter, Intent, classify_intent
from fin_engine.models import AccountGroup, Ledger, LedgerLine
from fin_engine.rag import KnowledgeBaseA

from test_rag import HashEmbedder  # reuse the deterministic fake embedder


def _ledger():
    return Ledger("acme", "2026-11", [
        LedgerLine(AccountGroup.REVENUE, "500000"),
        LedgerLine(AccountGroup.COGS, "280000"),
        LedgerLine(AccountGroup.OPERATING_EXPENSE, "100000"),
        LedgerLine(AccountGroup.FINANCE_COST, "5000"),
    ])


def _kb():
    # The fake HashEmbedder's cosine scores are not on the same scale as the
    # production nomic-embed-text default (0.5); pin a low threshold so these
    # tests exercise routing, not embedding-score tuning.
    kb = KnowledgeBaseA(embedder=HashEmbedder(), min_score=0.05,
                        generator=lambda p: "Reference explanation [Source 1].")
    kb.ingest_text("Working capital is current assets minus current liabilities.",
                   source="glossary.md")
    return kb


# --- intent classification ------------------------------------------------
@pytest.mark.parametrize("q,expected", [
    ("Explain working capital", Intent.GENERAL),
    ("What is our PBT?", Intent.BUSINESS),
    ("What is our revenue this month?", Intent.BUSINESS),
    ("Is our working capital healthy?", Intent.COMBINED),
    ("Is gross profit margin too low?", Intent.COMBINED),
    ("Define EBIT", Intent.GENERAL),
])
def test_classify_intent(q, expected):
    assert classify_intent(q) is expected


# --- routing --------------------------------------------------------------
def test_general_routes_to_rag_only():
    r = QueryRouter(kb_a=_kb()).ask("Explain working capital")
    assert r.intent is Intent.GENERAL
    assert r.pnl is None
    assert "glossary.md" in r.citations


def test_business_uses_engine_figures_not_llm():
    r = QueryRouter(kb_a=_kb(), ledger_provider=_ledger).ask("What is our PBT?")
    assert r.intent is Intent.BUSINESS
    assert r.pnl is not None
    assert r.pnl.pbt == Decimal("115000")   # the corrected value, from code
    assert "115,000" in r.answer
    assert r.rag is None                      # no RAG call for a pure metric


def test_combined_merges_figures_and_reference():
    r = QueryRouter(kb_a=_kb(), ledger_provider=_ledger).ask(
        "Is our working capital healthy?")
    assert r.intent is Intent.COMBINED
    assert r.pnl is not None                  # verified figures present
    assert "Reference context" in r.answer    # plus RAG explanation
    assert "glossary.md" in r.citations


def test_business_without_data_reports_the_gap():
    """report §4.4/§8.4: report missing data, never invent figures."""
    r = QueryRouter(kb_a=_kb(), ledger_provider=lambda: None).ask(
        "What is our net profit?")
    assert r.intent is Intent.BUSINESS
    assert r.pnl is None
    assert "No business records" in r.answer
