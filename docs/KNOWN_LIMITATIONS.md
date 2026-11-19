# fin-engine — Known Limitations

_As of 2026-11-20. Honest list of what the system does NOT do. Nothing here is
hidden behind a complete-looking feature._

## Not production-ready

This is a **single-user local prototype**. The items below are the gap between
it and a production financial system. They are deferred on purpose, not faked.

| Limitation | Impact | Upgrade trigger |
|---|---|---|
| **No persistence.** `Journal`/`Ledger` are in-memory; `router.ledger_provider` is a stub returning `None`. | Nothing survives a restart; the router answers business questions with "no records available". | When real records exist, back `ledger_provider` with a store. SQLite is the simplest reliable choice; PostgreSQL only if concurrent writers appear. Put it behind a repository interface so callers don't change. |
| **No authentication / RBAC.** Any caller can read/post anything. | Fine for one local user; unsafe if shared. | First additional user. Add a permission check inside `ledger_provider` (the router already calls it per-request for exactly this reason). |
| **No audit trail.** `Journal` is append-only in memory but records no who/when/before/after. | Can't answer "who changed this". | Same trigger as persistence — the audit log lives in the store, not in code. |
| **Classification is keyword rules, not learned.** | Misses phrasings outside the rule list; those become `needs_review`. | Acceptable by design — review beats a wrong auto-post. Revisit only if review volume is painful. |
| **RAG citation check is answer-level.** Abstains when retrieval is weak, but does not verify each claim against its cited chunk. | A grounded answer may still over-claim relative to its source. | If answers are used unreviewed. Add per-claim span-matching then. |
| **Balance sheet is entered, not derived from the journal.** `BalanceSheet` takes figures directly; it is not yet posted from `Journal` account balances. | Two sources of truth until wired. | Next session: derive `BalanceSheet` from `Journal.balance(account)` via an account→group map. The pieces exist; only the mapping is missing. |

## What IS trustworthy

- Every monetary calculation (P&L, cash-flow, working capital, current/quick
  ratio) is exact Decimal, versioned, and covered by tests with hand-specified
  expected values.
- Unbalanced journal entries and duplicate entry ids are **rejected**, not
  silently accepted. Balance-sheet imbalance and negative working capital are
  **surfaced as warnings**, never hidden.
- No number shown to a user is produced by the LLM.
