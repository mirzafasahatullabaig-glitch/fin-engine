# Chart of Accounts (v1.5.0)

`src/fin_engine/accounts.py`. One account taxonomy, not two: each `Account`
carries an `AccountGroup` (the existing fine-grained classification); its coarse
`AccountType` (asset/liability/equity/revenue/expense), `NormalBalance`
(debit/credit) and `StatementCategory` are **derived** from the group.

## Account fields

| Field | Meaning |
|---|---|
| `code` | unique within an entity's chart |
| `name` | display name |
| `group` | `AccountGroup` — authoritative classification |
| `current` | current vs non-current (assets/liabilities only) |
| `parent_code` | optional parent; no cycles, parent must exist |
| `is_active` | inactive accounts cannot be posted to |
| `description` | free text |

Derived (properties, not stored): `account_type`, `normal_balance`,
`statement_category`.

## Validation (`ChartOfAccounts`)

- unique codes
- parent must exist; no circular parent chains
- `validate_postable(code)` rejects unknown or inactive accounts before posting

## Starter chart

`starter_chart(entity)` returns the 18-account configuration below (prompt 3.2).
It is a starter, not a statutory CoA — callers add their own accounts.

| Code | Account | Group | Current |
|---|---|---|---|
| 1000 | Cash | asset | yes |
| 1010 | Bank | asset | yes |
| 1100 | Accounts Receivable | asset | yes |
| 1200 | Inventory | asset | yes |
| 1500 | Equipment | asset | no |
| 2000 | Accounts Payable | liability | yes |
| 2100 | Short-term Loans | liability | yes |
| 2200 | Long-term Loans | liability | no |
| 3000 | Owner's Equity | equity | — |
| 3100 | Retained Earnings | equity | — |
| 4000 | Sales Revenue | revenue | — |
| 5000 | Cost of Goods Sold | cogs | — |
| 6000–6300 | Salaries / Rent / Utilities / Marketing | operating_expense | — |
| 7000 | Finance Costs | finance_cost | — |
| 7100 | Tax Expense | tax | — |

## Account → statement mapping

Explicit and table-driven (`_GROUP_STATEMENT` + the current/non-current split
for assets/liabilities). Balance-sheet classification is **never** inferred from
account names.
