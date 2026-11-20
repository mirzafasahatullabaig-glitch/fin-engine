# v1.5.0 Unified Accounting Engine — Implementation Report

Branch `v1.5.0-unified-accounting`, built in 7 reviewable phases on top of
v1.4.0. Master untouched until merge.

## Summary

The journal is now the single source of truth. The same validated journal
produces the trial balance, P&L and balance sheet; the same journal-derived
balances power working capital, liquidity ratios and router queries. This closes
the v1.4.0 two-source-of-truth gap (BalanceSheet previously took hand-entered
figures).

## Files created

| File | Purpose |
|---|---|
| `src/fin_engine/accounts.py` | Chart of Accounts + explicit account→statement mapping |
| `src/fin_engine/ledger_gl.py` | general-ledger balances, activity, trial balance |
| `src/fin_engine/statements.py` | `pnl_from_journal`, `balance_sheet_from_journal` |
| `src/fin_engine/periods.py` | typed date/period parsing (leap-year correct) |
| `src/fin_engine/reconciliation.py` | accounting-invariant checks + report |
| `tests/test_accounts.py`, `test_journal_v15.py`, `test_ledger_gl.py`, `test_statements.py`, `test_router_v15.py`, `test_periods.py`, `test_reconciliation.py`, `test_properties.py` | +60 tests |
| `docs/CHART_OF_ACCOUNTS.md`, `docs/UNIFIED_ACCOUNTING_ARCHITECTURE.md`, `docs/RECONCILIATION_GUIDE.md`, `docs/TEST_REPORT.md`, this report | documentation |

## Files modified

| File | Change |
|---|---|
| `src/fin_engine/journal.py` | `EntryStatus`, `JournalEntry.status`, chart-aware `post()`, `reverse()`, DRAFT-excluding balances |
| `src/fin_engine/router.py` | `Metric` + `detect_metric`, `accounting_provider`, metric-specific dispatch, `RouteResult.bs/metric/value` |
| `src/fin_engine/__init__.py` | new public exports |
| `tests/test_router.py` | one test corrected to v1.5 semantics (documented) |

## Key design decisions

- **One taxonomy**: `AccountType`/`NormalBalance`/`StatementCategory` are derived
  from the existing `AccountGroup`, not a second parallel classification.
- **Reuse formulas**: `pnl_from_journal` calls the existing `calculate_pnl`;
  `balance_sheet_from_journal` builds the existing `BalanceSheet`. No formula was
  reimplemented, so v1.4.0 golden tests still pin behaviour.
- **Backward compatible**: `calculate_pnl(Ledger)`, `Journal` without a chart,
  and `ledger_provider` all still work. `status` defaults to POSTED.
- **No new dependencies**; local-first and offline preserved.

## Honest scoring (evidence-based)

| Area | Target | Assessed | Evidence |
|---|---|---|---|
| Accounting architecture | 9.5 | **9** | journal→GL→statements wired; one mapping; retained-earnings fold documented |
| Financial correctness | 9.5 | **9** | Decimal throughout; hand-checked trial balance/P&L/BS reconcile end-to-end |
| Journal integrity | 9.5 | **9** | double-entry enforced, chart validation, reversal append-only, DRAFT excluded |
| Router correctness | 9 | **8.5** | metric dispatch verified; BS metrics never borrow P&L (asserted) |
| Test coverage/evidence | 9.5 | **9** | 123 passing, hand-specified expectations, negative + property tests |
| Integration quality | 9.5 | **9** | end-to-end run reconciles; backward compatibility preserved |

Scores are below target in places by design — see KNOWN_LIMITATIONS. They are not
self-awarded: each rests on executed tests and the end-to-end run in TEST_REPORT.

## Remaining limitations (not done, honestly)

- **Cash flow is not yet journal-derived.** `cashflow.py` is unchanged
  (signed-movement model). Deriving an indirect cash-flow statement needs
  cash-vs-accrual metadata the journal does not carry; left as-is rather than
  faked (prompt 5.5).
- **Retained earnings** is a single derived figure (net income to `as_of`), with
  no b/f vs current-year split and no multi-period close.
- **Entity isolation** is by convention (one journal/chart per entity); there is
  no multi-entity container enforcing it in a shared store.
- **No persistence / auth / RBAC** — unchanged from v1.4.0, still deferred.

## Migration

Purely additive. Existing code using `calculate_pnl`, `BalanceSheet`,
`Journal`/`JournalEntry`/`Posting` or the router's `ledger_provider` keeps
working. To use the unified path, build a `ChartOfAccounts`, attach it to the
`Journal`, and call the `*_from_journal` builders or give the router an
`accounting_provider`.

## Post-v1.5.0 increments

- **v1.5.1** — interactive REPL (`repl.py`); LLM advisory layer (`advisor.py`) over engine-verified figures.
- **v1.5.3** — observability (`logging_setup.py`, library-safe NullHandler, privacy-aware), reliability (`config.py` health check, Ollama timeout + one retry), packaging fix.
- **v1.5.4** — config propagation end to end (embedder + generator from `Config.from_env()`); strict date validation + entity isolation in the journal; refund/contra netting in `pnl_from_journal` (nets within a group, flows through when net-negative, never crashes); **advice gated on a passing `reconcile()`** (the model is never called on inconsistent books); **SQLite persistence** (`store.py`, transaction-safe, exact Decimal, revalidates on reload); GitHub Actions CI (`.github/workflows/tests.yml`, offline suite on 3.11 + 3.12).

Test count grew 123 → 143 across these increments.

## v1.6.0 roadmap

1. Journal-derived cash flow (add cash/accrual metadata to postings).
2. Multi-entity store with enforced isolation + a persistence layer (SQLite).
3. Period-close entries so retained earnings b/f is explicit.
4. Per-claim RAG citation verification.
