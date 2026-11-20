# Changelog

All notable changes to fin-engine. Versions are git tags; dates are UTC.

## v1.5.7 — journal-derived cash flow
- `cash_flow_from_journal`: direct-method cash-flow statement derived from the
  journal. Net change reconciles exactly to the change in cash-account balances.
  `Account.is_cash` flags cash/bank accounts; REPL `cashflow` command.

## v1.5.6 — audit trail
- Every entry records `created_by` + `created_at` (auto-stamped, persisted,
  preserved across reloads). REPL `history` command. SQLite migration for old DBs.

## v1.5.5 — REPL persistence
- REPL opens a SQLite file (`FIN_ENGINE_DB`, default `./fin-engine.db`), loads on
  startup, saves after each entry. DB gitignored.

## v1.5.4 — config, validation, refunds, advice gating, persistence, CI
- Config propagates to embedder + generator. Strict date + entity validation.
  Refund/contra netting in the P&L. Advice gated on a passing reconciliation.
  `JournalStore` SQLite persistence (transaction-safe). GitHub Actions CI.

## v1.5.3 — observability & reliability
- Structured logging (privacy-aware). `health_check`, Ollama timeout + retry,
  env-driven config.

## v1.5.1 — REPL & advisor
- Interactive console (`repl.py`). LLM advisory layer over engine-verified
  figures (`advisor.py`).

## v1.5.0 — unified accounting engine
- Journal as single source of truth: Chart of Accounts, general ledger,
  journal-derived P&L + balance sheet, metric-specific router, typed periods,
  reconciliation.

## v1.4.0 — double-entry journal + balance sheet
- `Journal`/`JournalEntry`/`Posting`, balance sheet + liquidity ratios.

## v1.0.0 – v1.3.0 — finance engine, RAG, router
- Deterministic P&L/cash-flow/classification (golden tests), Knowledge Base A
  RAG, A/B query router, audit fixes.
