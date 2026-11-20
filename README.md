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
Markdown is chunked by heading (each `##` section is its own chunk), and model
answers are cleaned of `<think>…</think>` blocks and placeholder `[Source N]`
citation artifacts deterministically.

### A/B query router (`fin_engine.router`)

One entry point that classifies a question's intent (report §4.3) and routes it:

| Question | Intent | Handled by |
|---|---|---|
| "Explain working capital" | `general` | Knowledge Base A (RAG) |
| "What is our PBT?" | `business` | the finance engine — **exact figures, never the LLM** |
| "Is our working capital healthy?" | `combined` | both: verified figures + reference context |

`QueryRouter` takes a `ledger_provider` callable so access control / period
selection happen at call time; if no records are available it reports the gap
instead of inventing figures.

**To run the demos you need Ollama:**

```powershell
ollama pull nomic-embed-text
ollama pull granite4.2:8b
python rag_demo.py      # Knowledge Base A retrieval + answers
python router_demo.py   # A/B routing across engine + RAG
```

### Unified accounting engine (v1.5.x)

The journal is the single source of truth: the same validated journal produces
the trial balance, P&L and balance sheet, and those verified balances power the
metrics and the advisor. See `docs/UNIFIED_ACCOUNTING_ARCHITECTURE.md`.

| Piece | Purpose |
|---|---|
| `accounts.py` | Chart of Accounts + explicit account→statement mapping (one taxonomy, derived from `AccountGroup`) |
| `journal.py` | double-entry `Journal`/`JournalEntry`/`Posting`; DRAFT/POSTED/REVERSED lifecycle, append-only reversal, strict date + entity validation |
| `ledger_gl.py` | `account_balance` / `account_activity` / `trial_balance` from posted entries |
| `statements.py` | `pnl_from_journal`, `balance_sheet_from_journal`, `cash_flow_from_journal` (direct-method, reconciles to cash-account balances) |
| `periods.py` | typed ISO date + period (`YYYY-MM`/`YYYY-Qn`/`YYYY`) parsing, leap-year correct |
| `reconciliation.py` | `reconcile()` → structured report of accounting invariants |
| `store.py` | SQLite persistence with transaction-safe entry writes (exact Decimal, no float) |
| `config.py` / `logging_setup.py` | env-driven Ollama config, `health_check()`, structured logging |
| `advisor.py` | LLM business advice over engine-verified figures — gated on a passing reconciliation |

### Interactive console (`repl.py`)

```
python repl.py
```
Post journal entries and query live: `seed`, `post`, `ask`, `advise`, `bs`,
`pnl`, `cashflow`, `trial`, `check`, `history`, `health`, `help`, `quit`. Metric
answers are deterministic (no Ollama); `advise` uses the local model over
verified figures. Entries persist to SQLite and reload on the next launch.

## Run

```powershell
# optional: create a venv
py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"   # optional; demo.py and pytest work without it
python demo.py            # worked examples from the report
python repl.py            # interactive accounting console
pytest                    # 143 offline tests (no Ollama needed)
```

The finance engine is stdlib-only (`decimal`, `dataclasses`, `enum`, `sqlite3`).
The RAG module adds one runtime dependency, **NumPy**, for the vector store.
`pytest` is dev-only and uses a deterministic fake embedder, so the offline
suite needs **no Ollama** — only `rag_demo.py`, `test_e2e.py` and the `advise`
command do. Config via `FIN_ENGINE_OLLAMA_HOST` / `FIN_ENGINE_GEN_MODEL` /
`FIN_ENGINE_EMBED_MODEL` / `FIN_ENGINE_LOG_LEVEL`. CI runs the offline suite on
Python 3.11 + 3.12 (`.github/workflows/tests.yml`).

## Design rules (from the report)

- The LLM may *propose* an interpretation; the engine *calculates and validates*.
- When source records or mappings are missing, report the gap — never invent a value.
- Confidential business data (report §3.2) is gitignored; only code is committed.

## Status

**v1.5.4** — 143 offline tests, all green. Delivered since the report's first
build step:

- v1.0.x finance engine + golden tests; v1.1.0 KB-A RAG; v1.2.0 A/B router; v1.3.0 audit fixes.
- v1.4.0 double-entry journal + balance sheet/ratios.
- **v1.5.0 unified accounting engine** — journal as single source of truth (Chart of Accounts, general ledger, journal-derived P&L/balance sheet, metric-specific router, periods, reconciliation).
- **v1.5.1** interactive REPL; **v1.5.1** LLM advisory layer over verified figures.
- **v1.5.3** observability (structured logging), reliability (health check, timeouts, retry), config.
- **v1.5.4** config propagation, strict date/entity validation, refund netting, advice gated on reconciliation, **SQLite persistence**, GitHub Actions CI.

Not yet built (documented with triggers in `docs/KNOWN_LIMITATIONS.md`): KB-B
RAG over private records, role-based permissions, journal-derived cash flow,
multi-entity shared store, a UI. Auth/RBAC/Postgres are deferred by design for a
single-user local tool.
