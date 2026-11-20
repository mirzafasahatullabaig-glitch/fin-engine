# API Reference (v1.5.7)

Everything below is importable from the top-level package: `from fin_engine import ...`.
Money is always `Decimal` — pass amounts as strings or ints, never floats.

## Accounts — `accounts.py`

### `Account(code, name, group, current=True, parent_code=None, is_active=True, description="", is_cash=False)`
One account. `account_type`, `normal_balance`, `statement_category` are derived
properties (not stored). `is_cash` marks cash/bank accounts for cash-flow.

### `ChartOfAccounts(entity)`
Registry. `.add(account)` (validates unique code, known parent, no cycles),
`.get(code)`, `.validate_postable(code)` (rejects unknown/inactive), `.accounts()`.

### `starter_chart(entity) -> ChartOfAccounts`
The 18-account starter chart (Cash/Bank flagged `is_cash`).

```python
coa = starter_chart("acme")
coa.get("1000").statement_category   # StatementCategory.CURRENT_ASSET
```

## Journal — `journal.py`

### `Posting(account, amount, description="")`
One leg. `amount` is **signed**: debit +, credit −. Rejects zero amount and float.

### `JournalEntry(entry_id, date, description, postings, ref="", status=EntryStatus.POSTED, created_by="", created_at="")`
A balanced entry. **Raises `ValueError`** if postings don't sum to zero, if there
are < 2 postings, or if `date` isn't a real ISO date. `created_by`/`created_at`
auto-stamp when blank (audit trail).

### `Journal(entity, entries=[], warnings=[], chart=None)`
- `.post(entry)` — appends; **raises** on duplicate `entry_id`, or (with a chart)
  on a posting to an unknown/inactive account. Flags duplicate `ref` in `.warnings`.
- `.reverse(entry_id, reversal_id, date)` — marks the original REVERSED, posts a
  negated reversing entry (append-only; nothing deleted).
- `.balance(account)` — signed net over POSTED+REVERSED entries (DRAFT excluded).

```python
j = Journal("acme", chart=starter_chart("acme"))
j.post(JournalEntry("E1", "2026-11-01", "cash sale",
                    [Posting("1000", "1000"), Posting("4000", "-1000")]))
j.balance("1000")        # Decimal("1000")
```

## General ledger — `ledger_gl.py`

| Function | Returns |
|---|---|
| `account_balance(journal, chart, code, as_of=None)` | normal-balance-positive `Decimal` |
| `account_activity(journal, chart, code, start, end)` | `AccountActivity(opening, period_debits, period_credits, closing)` |
| `trial_balance(journal, chart, as_of=None)` | `TrialBalance(lines, total_debits, total_credits, .balanced, .difference)` |

## Statements — `statements.py`

| Function | Returns |
|---|---|
| `pnl_from_journal(journal, chart, period, start=None, end=None)` | `PnL` |
| `balance_sheet_from_journal(journal, chart, as_of)` | `BalanceSheet` |
| `cash_flow_from_journal(journal, chart, period, start=None, end=None)` | `CashFlow` (direct method) |

`PnL` fields: `revenue, cogs, gross_profit, operating_expenses, ebit, other_income,
finance_costs, other_expenses, pbt, tax, net_profit`; `.margins()` → dict.
`BalanceSheet`: `.total_assets, .total_liabilities, .working_capital,
.current_ratio, .quick_ratio` (ratios return `None`, not ∞, when no current
liabilities), `.validation_warnings()`.

```python
pnl = pnl_from_journal(j, coa, "2026-11")      # period label resolves to a date range
bs  = balance_sheet_from_journal(j, coa, "2026-11-30")
cf  = cash_flow_from_journal(j, coa, "2026-11")
```

## Router — `router.py`

### `QueryRouter(kb_a, ledger_provider=..., accounting_provider=...)`
`.ask(question) -> RouteResult(intent, answer, pnl, bs, rag, metric, value, citations)`.
`detect_metric(question) -> Metric | None`. Balance-sheet metrics are computed
from the balance sheet, **never** substituted from P&L.

## Reconciliation — `reconciliation.py`

### `reconcile(journal, chart, as_of) -> ReconciliationReport`
`.passed`, `.failures` (list of `Check(name, passed, detail)`), `.checks`.
Checks: every entry balances, valid accounts, trial balance, accounting identity,
working capital, current ratio.

## Advisor — `advisor.py`

### `advise(question, journal, chart, period, as_of, kb_a, generate, k=3) -> Advice`
Computes figures deterministically, retrieves guidance, asks the LLM to recommend.
**Refuses (returns `grounded=False`) if the books don't reconcile.** `Advice` has
`figures` (engine truth), `recommendation` (model text), `citations`.

## Persistence — `store.py`

### `JournalStore(path=":memory:")`
`.save_journal(j)` / `.save_entry(entity, entry)` (transaction-safe, rejects
duplicates) / `.load_journal(entity)` (revalidates on load) / `.save_chart` /
`.load_chart` / `.close()`. Context-manager friendly.

## Config & ops — `config.py`, `logging_setup.py`

`Config.from_env()` (host/models from env), `health_check(config=None) -> Health`
(never raises), `configure_logging(level=None)`, `get_logger(name)`.

Env: `FIN_ENGINE_OLLAMA_HOST`, `FIN_ENGINE_GEN_MODEL`, `FIN_ENGINE_EMBED_MODEL`,
`FIN_ENGINE_LOG_LEVEL`, `FIN_ENGINE_DB`.
