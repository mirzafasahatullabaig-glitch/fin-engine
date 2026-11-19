# fin-engine — Architecture Audit

_As of 2026-11-20. Audit performed by reading every source and test file._

## What this project is

A **local-first** finance assistant: deterministic Python does all authoritative
arithmetic; a local Ollama model is a language/orchestration layer only. It is a
**single-user prototype**, not a multi-tenant service.

## Module map

| Layer | File | Responsibility |
|---|---|---|
| Money primitive | `models.py` | `money()` Decimal coercion (rejects float), `AccountGroup`/`CashFlowCategory` enums, `Ledger`/`LedgerLine`, `FORMULA_VERSION` |
| Posting | `journal.py` | **(new v1.4.0)** double-entry `Posting`/`JournalEntry`/`Journal`; balance enforcement, duplicate detection |
| Statements | `pnl.py`, `cashflow.py`, `balance_sheet.py` | P&L (PBT corrected), cash-flow by category, balance sheet + liquidity ratios **(new)** |
| Classification | `classify.py` | rule-based dual-dimension classify with confidence + review flag |
| Routing | `router.py` | deterministic intent classifier → engine / RAG / both |
| RAG | `rag/*` | chunk → embed (`nomic-embed-text`) → NumPy store → answer (`granite4.2:8b`) |

## Strengths (verified in code, not claimed)

- **No float ever touches money.** `money()` rejects `float` and `bool`; every monetary dataclass coerces through it in `__post_init__`.
- **PBT bug fixed and golden-tested.** `pnl.py` computes `PBT = EBIT + other_income − finance_costs − other_expenses`; `test_pnl_golden.py` pins the exact report §7.3 values the LLM got wrong.
- **Classification abstains.** Ambiguous / inflow-conflict / no-match → `needs_review=True`, confidence `"low"`. The model never sets the authoritative label.
- **Router never invents figures.** `ledger_provider` returning `None` yields an explicit "no records available" answer, not a fabricated number.
- **Formulas are versioned.** `FORMULA_VERSION` is stamped on every result for reproducibility.

## Weaknesses / gaps (this session's targets in **bold**)

- **No double-entry posting layer** — `Ledger` was pre-classified magnitudes with no balance check. → **built: `journal.py`.**
- **No balance sheet or liquidity ratios** — only P&L margins existed. → **built: `balance_sheet.py`.**
- **v1.5.0 update:** the two-source-of-truth gap below is now resolved — P&L and balance sheet derive from the journal via the Chart of Accounts (`accounts.py`, `ledger_gl.py`, `statements.py`); the router dispatches per-metric (`router.py`); periods are typed (`periods.py`); reconciliation checks invariants (`reconciliation.py`). See docs/UNIFIED_ACCOUNTING_ARCHITECTURE.md and docs/V1_5_IMPLEMENTATION_REPORT.md.
- No persistence: everything is in-memory; `ledger_provider`/`accounting_provider` are caller-supplied. See KNOWN_LIMITATIONS.
- No auth / RBAC / audit trail — single-user tool, deliberately deferred. See KNOWN_LIMITATIONS.
- RAG citation verification is answer-level (abstention threshold), not per-claim.

## Deliberately NOT built (and why)

PostgreSQL, authentication, role-based access control, and a web UI are on the
report roadmap but are **not justified for a single-user local prototype**.
Adding them now is infrastructure without a user. They become worthwhile only
if/when the tool goes multi-user — that is the trigger, documented in
KNOWN_LIMITATIONS.md, not a silent omission.
