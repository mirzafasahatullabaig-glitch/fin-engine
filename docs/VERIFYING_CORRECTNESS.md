# Verifying Financial Correctness

A finance engine must produce numbers that are *correct*, not merely plausible.
This guide shows how to verify that yourself — the checks the project relies on,
and how to run them.

## 1. The accounting invariants the engine enforces

| Invariant | Where enforced | How to see it |
|---|---|---|
| Every entry balances (Σ debits = Σ credits) | `JournalEntry.__post_init__` raises if not | `reconcile()` check `J1` |
| Postings hit known, active accounts | `Journal.post` with a chart | check `J2` |
| Trial balance: total debits = total credits | derived in `ledger_gl.trial_balance` | check `T1` |
| Accounting identity: Assets = Liabilities + Equity | `balance_sheet_from_journal` folds retained earnings | check `B1` |
| Working capital = current assets − current liabilities | `BalanceSheet.working_capital` | check `B2` |
| Current ratio = CA / CL | `BalanceSheet.current_ratio` | check `B3` |
| Cash-flow net = actual change in cash balances | `cash_flow_from_journal` | test in `test_cashflow_journal.py` |

`reconcile(journal, chart, as_of)` runs all of these and returns a structured
report; a failed check is never silently passed.

## 2. Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

151 offline tests, no Ollama needed. They are not "does it return something"
tests — expected values are **hand-calculated in each test's docstring** and
asserted literally, independent of the implementation. See:

- `test_pnl_golden.py` — the report §7.3 examples the LLM got wrong (PBT 115,000 / 190,000)
- `test_statements.py` — one sample company whose trial balance, P&L and balance sheet are all hand-derived and must agree
- `test_ledger_gl.py` — a hand-checked trial balance (3,500 / 3,500)
- `test_cashflow_journal.py` — net cash flow proven equal to the change in cash balances
- `test_reconciliation.py`, `test_properties.py` — deliberately corrupted journals must be *caught*

## 3. Verify it end-to-end yourself

```python
from fin_engine import (Account, ChartOfAccounts, Journal, JournalEntry, Posting,
    starter_chart, trial_balance, pnl_from_journal, balance_sheet_from_journal,
    cash_flow_from_journal, reconcile)

coa = starter_chart("demo")
j = Journal("demo", chart=coa)
j.post(JournalEntry("E0","2026-11-01","capital",[Posting("1000","20000"),Posting("3000","-20000")]))
j.post(JournalEntry("E1","2026-11-05","sale",   [Posting("1000","9000"), Posting("4000","-9000")]))
j.post(JournalEntry("E2","2026-11-06","inv/credit",[Posting("1200","4000"),Posting("2000","-4000")]))
j.post(JournalEntry("E3","2026-11-10","cogs",   [Posting("5000","2500"), Posting("1200","-2500")]))
j.post(JournalEntry("E4","2026-11-15","rent",   [Posting("6100","1200"),Posting("1000","-1200")]))

assert trial_balance(j, coa, as_of="2026-11-30").balanced          # debits = credits
pnl = pnl_from_journal(j, coa, "2026-11")
assert pnl.net_profit == pnl.revenue - pnl.cogs - pnl.operating_expenses  # 9000-2500-1200 = 5300
bs = balance_sheet_from_journal(j, coa, "2026-11-30")
assert bs.total_assets == bs.total_liabilities + bs.equity          # accounting identity
assert reconcile(j, coa, "2026-11-30").passed                       # all invariants
```

If any `assert` fails, the engine is wrong — that is the point of the guide.

## 4. Why the LLM can't corrupt the numbers

Every figure is computed in deterministic Python with exact `Decimal`
arithmetic and a versioned formula (`FORMULA_VERSION`). The LLM (advisor /
router) only *interprets* verified figures — `Advice.figures` always holds
engine truth regardless of what the model says, and `advise()` refuses to run
at all if `reconcile()` fails. See `test_advisor.py::test_advice_figures_match_engine_not_model`.

## 5. The float ban

`money()` (in `models.py`) rejects `float` and `bool` outright — amounts must be
`int`, `str` or `Decimal`. This prevents binary-rounding error from ever
entering a monetary calculation. Verify: `Posting("1000", 10.5)` raises `TypeError`.
