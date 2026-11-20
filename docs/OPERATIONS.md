# Operations: Backup, Recovery, Concurrency

This is a **local-first, single-user** tool. This doc states plainly what it
does and does not support operationally — no overclaiming.

## Backup & recovery

The ledger lives in one SQLite file (`FIN_ENGINE_DB`, default `./fin-engine.db`).
`JournalStore` provides a first-class backup path (SQLite's online backup API),
so backups are consistent snapshots even while the store is open.

```python
from fin_engine import JournalStore

store = JournalStore("fin-engine.db")
store.backup("backups/2026-11-21.db")   # consistent snapshot, safe while open
assert store.integrity_check()           # PRAGMA integrity_check == "ok"
store.close()

# Recover: restore refuses a corrupt backup, so bad data can't go live.
restored = JournalStore.restore("backups/2026-11-21.db", "fin-engine.db")
```

**Recovery procedure**
1. Stop any running REPL (so the live file is quiescent).
2. `JournalStore.restore(<backup>, <live path>)` — it integrity-checks the
   backup first and raises if it fails.
3. Reopen; `load_journal` revalidates every entry on the way in (balance, known
   accounts), so a restored file that passed integrity is also accounting-valid.

**Automating it** — there is no built-in scheduler. Use the OS:
- Windows Task Scheduler / cron → a small script that calls `backup()` then
  `integrity_check()`, keeping dated copies. Keep backups off the same disk.

## Concurrency — what is and isn't supported

SQLite is **single-writer, multi-reader**. v1.5.9 opens the store in **WAL mode**,
so:

- **Multiple readers** (e.g. a dashboard reading while you post) work concurrently.
- **One writer at a time.** A second concurrent writer serialises behind the
  first, or gets `database is locked` if it waits past the timeout.

This is correct and safe for the tool's single-user design. It is **not**
validated for many concurrent writers, and this doc does not claim it is —
pretending otherwise would be dishonest. The transaction safety that *is*
guaranteed: each entry + its postings commit atomically (verified in
`test_store.py`), so an interrupted write never leaves a partial entry.

**When you genuinely need concurrent writers** (multiple users posting at once):
that is the trigger to move the repository layer to PostgreSQL. The
`JournalStore` interface is the seam — callers use `save_entry` / `load_journal`,
not SQL, so the backend can change without touching the engine.

## Access control

Authentication is the host application's job (OS login, SSO). Authorization is a
seam in `authz.py`: pass a `RoleBasedAuthorizer` to `advise()` (and, as the
pattern is extended, other entry points) to enforce per-principal permissions.
The default `AllowAll` keeps the single-user tool open. See
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
