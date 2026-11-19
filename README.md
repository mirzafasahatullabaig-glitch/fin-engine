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

| Function | Purpose |
|---|---|
| `calculate_pnl(ledger)` | Revenue → COGS → gross → EBIT → **PBT (minus finance costs)** → net |
| `calculate_cash_flow(entity, period, movements)` | Operating / investing / financing split |
| `classify_transaction(description)` | Dual label: P&L/balance-sheet group **and** cash-flow category, with a review flag for low-confidence matches |

## Run

```powershell
# optional: create a venv
py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"   # optional; demo.py and pytest work without it
python demo.py            # worked examples from the report
pytest                    # golden tests (includes the §7.3 PBT regressions)
```

No third-party runtime dependencies — the engine is stdlib-only
(`decimal`, `dataclasses`, `enum`). `pytest` is dev-only.

## Design rules (from the report)

- The LLM may *propose* an interpretation; the engine *calculates and validates*.
- When source records or mappings are missing, report the gap — never invent a value.
- Confidential business data (report §3.2) is gitignored; only code is committed.

## Status

Engine + golden tests complete. Not yet wired to a database, RAG router or the
Granite explanation layer — those remain proposed work per the report roadmap.
