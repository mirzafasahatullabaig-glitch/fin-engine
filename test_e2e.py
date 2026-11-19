"""End-to-end test: the whole stack against the REAL local models.

    python test_e2e.py

Unlike the pytest suite (which uses fake embedder/generator and runs offline),
this exercises the full pipeline live:
  - nomic-embed-text for embeddings
  - granite4.2:8b for generation
  - finance engine, KB-A RAG, A/B router, and the personal reading-list index

It asserts on real outcomes and prints a PASS/FAIL summary with an exit code,
so it can gate a release. Requires Ollama running with both models pulled.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))


def _exit(status: int) -> None:
    """Exit with a deterministic status.

    On Windows + Python 3.14 the normal interpreter shutdown occasionally
    crashes (exit 255) while tearing down GC'd objects / lingering HTTP
    connections, even when the test logic succeeded. Flushing the streams and
    using os._exit bypasses that finalizer phase so the exit code always
    reflects the test result, not a teardown race.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)

from fin_engine import QueryRouter, Intent, calculate_pnl, classify_transaction
from fin_engine.models import AccountGroup, Ledger, LedgerLine
from fin_engine.cashflow import calculate_cash_flow, CashMovement
from fin_engine.models import CashFlowCategory
from fin_engine.rag import KnowledgeBaseA, OllamaEmbedder, VectorStore

ROOT = Path(__file__).resolve().parent
KB_A_DIR = ROOT / "data" / "kb_a_sample"
READING_INDEX = ROOT / "data" / "reading_list.index.json"

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    mark = "PASS" if condition else "FAIL"
    if condition:
        _passed += 1
    else:
        _failed += 1
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  ({detail})"
    print(line)


def require_ollama() -> None:
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
    except Exception as exc:  # noqa: BLE001
        print(f"Ollama not reachable: {exc}\nStart it and pull the models first.")
        _exit(2)


def acme_ledger() -> Ledger:
    """Report Example A — correct PBT is 115,000."""
    return Ledger("Acme Ltd", "2026-11", [
        LedgerLine(AccountGroup.REVENUE, "500000"),
        LedgerLine(AccountGroup.COGS, "280000"),
        LedgerLine(AccountGroup.OPERATING_EXPENSE, "100000"),
        LedgerLine(AccountGroup.FINANCE_COST, "5000"),
    ])


def main() -> None:
    require_ollama()
    embedder = OllamaEmbedder()

    print("\n== 1. Finance engine (deterministic, no model) ==")
    pnl = calculate_pnl(acme_ledger())
    check("PBT subtracts interest (115,000)", pnl.pbt == Decimal("115000"),
          f"got {pnl.pbt}")
    check("EBIT correct (120,000)", pnl.ebit == Decimal("120000"))

    cf = calculate_cash_flow("Acme Ltd", "2026-11", [
        CashMovement(CashFlowCategory.OPERATING, "400000"),
        CashMovement(CashFlowCategory.FINANCING, "300000"),
    ])
    check("Cash flow nets correctly (700,000)", cf.net_change == Decimal("700000"))

    c = classify_transaction("Bank loan received")
    check("Loan = liability + financing",
          c.group is AccountGroup.LIABILITY and c.cash_flow is CashFlowCategory.FINANCING)

    print("\n== 2. KB-A ingest + embedding (real nomic-embed-text) ==")
    kb = KnowledgeBaseA(embedder=embedder)
    n = sum(kb.ingest_file(md) for md in sorted(KB_A_DIR.glob("*.md")))
    check("Ingested reference chunks", n >= 5, f"{n} chunks")
    check("Vector store populated", len(kb.store) == n)

    print("\n== 3. KB-A retrieval (real embeddings) ==")
    hits = kb.retrieve("What is working capital?", k=2)
    check("Top hit is the working-capital section",
          bool(hits) and "working capital" in hits[0].chunk.text.lower(),
          f"score {hits[0].score:.3f}" if hits else "no hits")

    print("\n== 4. KB-A grounded answer (real granite4.2:8b) ==")
    ans = kb.answer("Why is PBT not the same as EBIT?", k=3)
    check("Answer is grounded", ans.grounded)
    check("Answer mentions finance/interest cost",
          any(w in ans.text.lower() for w in ("finance cost", "interest")))
    check("Answer carries a citation", bool(ans.citations()))
    check("No <think> leakage", "<think>" not in ans.text and "</think>" not in ans.text)
    check("No [Source N] placeholder", "[Source N]" not in ans.text)

    print("\n== 5. Abstention on out-of-scope question ==")
    off = kb.answer("What is the capital of France?")
    check("Abstains when nothing relevant", not off.grounded)

    print("\n== 6. A/B router (real models) ==")
    router = QueryRouter(kb_a=kb, ledger_provider=acme_ledger)

    r_gen = router.ask("Explain working capital")
    check("General -> RAG only", r_gen.intent is Intent.GENERAL and r_gen.pnl is None)

    r_bus = router.ask("What is our PBT this month?")
    check("Business -> engine figures", r_bus.intent is Intent.BUSINESS)
    check("Business answer has exact 115,000", "115,000" in r_bus.answer)
    check("Business did not call RAG", r_bus.rag is None)

    r_comb = router.ask("Is our gross profit margin healthy?")
    check("Combined -> both engine + RAG",
          r_comb.intent is Intent.COMBINED and r_comb.pnl is not None)

    r_gap = QueryRouter(kb_a=kb, ledger_provider=lambda: None).ask("What is our revenue?")
    check("Business with no data reports the gap",
          r_gap.pnl is None and "No business records" in r_gap.answer)

    print("\n== 7. Personal reading-list index (private, persisted) ==")
    if READING_INDEX.exists():
        store = VectorStore.load(READING_INDEX)
        kb_books = KnowledgeBaseA(embedder=embedder, store=store)
        check("Reading-list index loaded (5 books)", len(store) == 5, f"{len(store)} entries")
        hits = kb_books.retrieve("decisions under uncertainty", k=1)
        top = hits[0].chunk.metadata.get("book", "") if hits else ""
        check("Top book = Thinking in Bets", top == "Thinking in Bets", f"got {top!r}")
    else:
        check("Reading-list index present", False,
              "run ingest_reading_list.py first")

    print(f"\n==== RESULT: {_passed} passed, {_failed} failed ====")
    _exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
