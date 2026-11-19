# fin-engine

Deterministic financial calculation and verification engine for the local-first
AI Business & Financial Intelligence system.

This is the first concrete build step from the project report
(`Local_AI_Business_Finance_Project_Report`, §8 and §12.3): the **financial
rules engine, with golden tests, built before any RAG or LLM integration**.

## Why it exists

The report's core design principle is that the LLM is a language and
orchestration layer — **not** the accounting system of record. Benchmark
testing (report §7.1) exposed a repeatable failure: IBM Granite 4.2 8B computed
gross and operating profit correctly but returned **PBT = EBIT**, ignoring
interest expense. Authoritative numbers must be computed in code.

This engine does that. Every total is an exact `Decimal` (never float), formulas
are versioned (`FORMULA_VERSION`), and the two P&L examples the model got wrong
are locked in as regression tests.

## What it does

### Deterministic finance engine (`fin_engine`)

| Function | Purpose |
|---|---|
| `calculate_pnl(ledger)` | Revenue → COGS → gross → EBIT → **PBT (minus finance costs)** → net |
| `calculate_cash_flow(entity, period, movements)` | Operating / investing / financing split |
| `classify_transaction(description)` | Dual label: P&L/balance-sheet group **and** cash-flow category, with a review flag for low-confidence matches |

### Knowledge Base A — general-docs RAG (`fin_engine.rag`)

Local-first retrieval over general business reference material (report §3.1).
NumPy vector store (no Qdrant/Postgres), `nomic-embed-text` embeddings and
`granite4.2:8b` generation, both via local Ollama.

| Piece | Purpose |
|---|---|
| `KnowledgeBaseA.ingest_text / ingest_file` | Chunk → embed → store a document |
| `.retrieve(q, k)` | Top-k chunks by cosine similarity (no LLM needed) |
| `.answer(q)` | Grounded, **source-cited** answer; **abstains** when nothing relevant is retrieved (report §4.4 / §8.4) |
| `VectorStore.save / load` | Persist the index to JSON |

The LLM only *explains* retrieved passages — it is never the source of truth,
and it is swapped out for a fake generator in tests so the suite runs offline.

**To run the RAG demo you need Ollama:**

```powershell
ollama pull nomic-embed-text
ollama pull granite4.2:8b
python rag_demo.py
```

## Run

```powershell
# optional: create a venv
py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"   # optional; demo.py and pytest work without it
python demo.py            # worked examples from the report
pytest                    # golden tests (includes the §7.3 PBT regressions)
```

The finance engine is stdlib-only (`decimal`, `dataclasses`, `enum`). The RAG
module adds one runtime dependency, **NumPy**, for the vector store. `pytest` is
dev-only. The RAG tests use a deterministic fake embedder, so `pytest` needs
**no Ollama** — only `rag_demo.py` does.

## Design rules (from the report)

- The LLM may *propose* an interpretation; the engine *calculates and validates*.
- When source records or mappings are missing, report the gap — never invent a value.
- Confidential business data (report §3.2) is gitignored; only code is committed.

## Status

Finance engine + golden tests complete (v1.0.x). Knowledge Base A general-docs
RAG complete with offline tests (v1.1.0). Not yet built: KB-B RAG over private
records, the A/B query router with permission checks, a database, and the UI —
those remain proposed work per the report roadmap.
