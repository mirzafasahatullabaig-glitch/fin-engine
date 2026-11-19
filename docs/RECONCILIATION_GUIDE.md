# Reconciliation Guide (v1.5.0)

`src/fin_engine/reconciliation.py`. `reconcile(journal, chart, as_of)` runs the
accounting invariants and returns a `ReconciliationReport`. A failed check is
recorded as failed — never silently passed.

## Checks

| ID | Check |
|---|---|
| `J1:entry_balances:<id>` | each statement-affecting entry's postings sum to zero |
| `J2:valid_account:<id>:<acct>` | each posting references a known, active account |
| `T1:trial_balance` | total debits == total credits |
| `B1:accounting_identity` | assets == liabilities + equity |
| `B2:working_capital` | working capital == current assets − current liabilities |
| `B3:current_ratio` | current ratio == CA / CL (or both undefined) |

## Report shape

```python
rep = reconcile(journal, chart, as_of="2026-11-30")
rep.passed          # True iff every check passed
rep.failures        # list[Check] that failed (name, passed, detail)
rep.checks          # all checks run
rep.entity, rep.as_of, rep.formula_version
```

## Usage

Run reconciliation before trusting any statement for an external purpose. DRAFT
entries are excluded (they do not affect statements). A reversed entry stays in
the journal (append-only) and is offset by its posted reversing entry, so the
pair nets to zero and reconciliation still passes.
