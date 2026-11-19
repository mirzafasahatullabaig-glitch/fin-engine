# Test Report — v1.5.0

Executed 2026-11-20 via the Py3.11 venv:
`.\.venv\Scripts\python.exe -m pytest tests/ -q`

**Result: 123 passed, 0 failed, 0 warnings** (offline; RAG tests use fake
embedder + generator — no Ollama needed).

## Per-file breakdown

| File | Tests | Covers |
|---|---:|---|
| test_pnl_golden.py | 6 | P&L formula, report §7.3 golden values (unchanged) |
| test_cashflow.py | 3 | cash-flow by category (unchanged) |
| test_classify.py | 12 | rule-based classification + abstention (unchanged) |
| test_rag.py | 15 | RAG retrieval, abstention, injection defence (unchanged) |
| test_balance_sheet.py | 7 | BalanceSheet ratios/identity (v1.4.0) |
| test_journal.py | 9 | double-entry journal (v1.4.0) |
| **test_accounts.py** | 10 | Chart of Accounts, derivations, validation (Phase 1) |
| **test_journal_v15.py** | 8 | chart integration, lifecycle, reversal (Phase 2) |
| **test_ledger_gl.py** | 7 | GL balances, trial balance (Phase 3) |
| **test_statements.py** | 4 | journal-derived P&L + balance sheet (Phase 4) |
| **test_router_v15.py** | 8 | metric-specific routing (Phase 5) |
| test_router.py | 11 | router (1 corrected for v1.5 semantics) |
| **test_periods.py** | 15 | date/period parsing, leap years (Phase 6) |
| **test_reconciliation.py** | 4 | invariants + negative tests (Phase 7) |
| **test_properties.py** | 4 | property-style invariants, seeded (Phase 7) |

## Expected-value independence

Financial test expectations are hand-calculated in each test's docstring/comments
(trial balances, P&L chains, balance-sheet identities), not read back from the
code under test — per prompt Part 9 / rule 16.

## End-to-end check

A full sample company run through the public API (`trial_balance`,
`pnl_from_journal`, `balance_sheet_from_journal`, `reconcile`) produced a
balanced trial balance (33000/33000), consistent P&L (net profit 5300) and
balance sheet (29300 = 4000 + 25300, no identity warnings), and reconciliation
passed all 19 checks. The same journal drives all three statements.

## Not executed

- Live tests (`test_e2e.py`, `bench_granite_accounting.py`) require Ollama +
  models and were not run in this session; they are unchanged by v1.5.0.
- No Hypothesis: property tests use seeded stdlib `random` (no new dependency).
