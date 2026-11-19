"""A/B query router demo (report §4.3).

    python router_demo.py

Shows one router sending each question to the right place:
  - general knowledge  -> Knowledge Base A (RAG, granite4.2:8b)
  - our own figures     -> the deterministic finance engine
  - "healthy?"          -> both

Requires Ollama with nomic-embed-text and granite4.2:8b (see rag_demo.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fin_engine import QueryRouter
from fin_engine.models import AccountGroup, Ledger, LedgerLine
from fin_engine.rag import KnowledgeBaseA, OllamaEmbedder

SAMPLE = Path(__file__).resolve().parent / "data" / "kb_a_sample"


def current_ledger() -> Ledger:
    """Stand-in for KB-B: the org's own figures (report Example A)."""
    return Ledger("Acme Ltd", "2026-11", [
        LedgerLine(AccountGroup.REVENUE, "500000"),
        LedgerLine(AccountGroup.COGS, "280000"),
        LedgerLine(AccountGroup.OPERATING_EXPENSE, "100000"),
        LedgerLine(AccountGroup.FINANCE_COST, "5000"),
    ])


def main() -> None:
    kb = KnowledgeBaseA(embedder=OllamaEmbedder())
    for md in sorted(SAMPLE.glob("*.md")):
        kb.ingest_file(md)

    router = QueryRouter(kb_a=kb, ledger_provider=current_ledger)

    for q in [
        "Explain working capital",          # -> GENERAL (RAG)
        "What is our PBT this month?",       # -> BUSINESS (engine)
        "Is our gross profit margin healthy?",  # -> COMBINED (both)
    ]:
        r = router.ask(q)
        print(f"Q: {q}")
        print(f"   intent: {r.intent.value}")
        print(f"A: {r.answer.strip()}")
        if r.citations:
            print(f"   sources: {', '.join(r.citations)}")
        print()


if __name__ == "__main__":
    main()
