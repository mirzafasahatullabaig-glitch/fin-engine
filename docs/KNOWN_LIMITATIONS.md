# fin-engine — Known Limitations

_As of 2026-11-20. Honest list of what the system does NOT do. Nothing here is
hidden behind a complete-looking feature._

## Not production-ready

This is a **single-user local prototype**. The items below are the gap between
it and a production financial system. They are deferred on purpose, not faked.

| Limitation | Impact | Upgrade trigger |
|---|---|---|
| ~~No persistence.~~ **PARTLY RESOLVED in v1.5.4.** `store.py` (`JournalStore`) persists accounts + entries + postings to SQLite, transaction-safe, exact Decimal, revalidating on reload. | Durable storage exists; the REPL does not yet auto-load/save it, and the router's `ledger_provider` is still caller-supplied. | Wire the REPL and router to a `JournalStore` by default. PostgreSQL only if concurrent writers appear. |
| **No authentication / RBAC.** Any caller can read/post anything. | Fine for one local user; unsafe if shared. | First additional user. Add a permission check inside `ledger_provider` (the router already calls it per-request for exactly this reason). |
| ~~No audit trail.~~ **RESOLVED in v1.5.6.** Each entry records `created_by` + `created_at` (auto-stamped, persisted, preserved across reloads); the journal is append-only and reversals keep the original (before/after). The REPL `history` command shows it. | — | Future: a mutation log of edits/corrections if posted entries ever become editable (they are not — corrections are reversing entries). |
| **Classification is keyword rules, not learned.** | Misses phrasings outside the rule list; those become `needs_review`. | Acceptable by design — review beats a wrong auto-post. Revisit only if review volume is painful. |
| **RAG citation check is answer-level.** Abstains when retrieval is weak, but does not verify each claim against its cited chunk. | A grounded answer may still over-claim relative to its source. | If answers are used unreviewed. Add per-claim span-matching then. |
| ~~Balance sheet is entered, not derived from the journal.~~ **RESOLVED in v1.5.0.** | — | `balance_sheet_from_journal` (and `pnl_from_journal`) now derive statements from journal balances via the Chart of Accounts mapping. See docs/UNIFIED_ACCOUNTING_ARCHITECTURE.md. |
| ~~Cash flow is not journal-derived.~~ **RESOLVED in v1.5.7.** `cash_flow_from_journal` derives a direct-method statement from the journal; net change reconciles exactly to the change in cash-account balances (`Account.is_cash`). | It is a *direct*-method statement, not indirect — no working-capital reconciliation from net income. `cashflow.py`'s standalone `calculate_cash_flow` remains for pre-classified movements. | If an indirect statement is needed, add it alongside. |
| **Retained earnings is a single derived figure.** Net income to `as_of` is folded into equity; no b/f vs current-year split, no multi-period close. | Fine for single-period reporting; not a multi-year ledger. | v1.6.0: explicit period-close entries. |
| **Entity isolation is by convention.** One journal/chart per entity; no shared multi-entity store enforcing it. | Cross-entity mixing is prevented by construction, not by a guard in a shared store. | When persistence lands. |

## What IS trustworthy

- Every monetary calculation (P&L, cash-flow, working capital, current/quick
  ratio) is exact Decimal, versioned, and covered by tests with hand-specified
  expected values.
- Unbalanced journal entries and duplicate entry ids are **rejected**, not
  silently accepted. Balance-sheet imbalance and negative working capital are
  **surfaced as warnings**, never hidden.
- No number shown to a user is produced by the LLM.
