# Error Reference

fin-engine fails loud and early at trust boundaries — invalid data raises rather
than being silently accepted or "repaired". Every raise below is intentional.

## Money / posting errors

| Exception & message | Cause | Resolution |
|---|---|---|
| `TypeError: money value must be int, str or Decimal, not float` | A monetary amount was passed as a `float` | Pass amounts as strings (`"10.50"`) or `Decimal` — never float, to keep them exact |
| `TypeError: money value must be a number, not bool` | A `bool` was passed as an amount | Pass a number |
| `ValueError: posting to '…' has zero amount` | A `Posting` amount is 0 | A posting must move a non-zero amount |
| `ValueError: posting account must be non-empty` | Empty account code on a posting | Supply an account code |

## Journal entry errors

| Exception & message | Cause | Resolution |
|---|---|---|
| `ValueError: entry '…' is unbalanced: debits - credits = N` | Postings don't sum to zero | Make debits equal credits (signed amounts sum to 0) |
| `ValueError: entry '…' needs >= 2 postings` | Fewer than two legs | A double-entry needs at least a debit and a credit |
| `ValueError: entry '…': date must be ISO YYYY-MM-DD` | Bad/empty date, or an impossible date (`2026-02-30`) | Use a real ISO date |
| `ValueError: duplicate entry_id '…'; ids must be unique` | Re-posting an existing id | Use a fresh `entry_id` (ids are the audit key) |
| `ValueError: cannot reverse unknown entry '…'` / `only POSTED entries can be reversed` | Reversing a missing or already-reversed entry | Reverse only a live POSTED entry |

## Chart of accounts errors

| Exception & message | Cause | Resolution |
|---|---|---|
| `KeyError: no account '…' in '…' chart` | Posting to / looking up an account not in the chart | Add the account first; unknown accounts are never treated as zero |
| `ValueError: account '…' is inactive; cannot post to it` | Posting to a deactivated account | Reactivate it or post to a live account |
| `ValueError: duplicate account code '…'` | Adding a code already in the chart | Codes are unique per entity |
| `ValueError: circular parent relationship …` / `references unknown parent …` | Bad `parent_code` | Fix the parent reference; no cycles |
| `ValueError: entity mismatch: journal '…' attached to a chart for '…'` | A journal and chart describe different entities | Use the chart for the journal's own entity (entity isolation) |

## Period errors

| Exception & message | Cause | Resolution |
|---|---|---|
| `ValueError: unrecognised period '…'` | Period label isn't `YYYY-MM` / `YYYY-Qn` / `YYYY` | Use a supported label |
| `ValueError: period start … is after end …` | Reversed date range | Ensure start ≤ end |

## Persistence errors

| Exception & message | Cause | Resolution |
|---|---|---|
| `ValueError: cannot persist entry '…': already stored` | Saving an `entry_id` already in the DB (UNIQUE constraint) | The entry is already saved; the transaction rolled back, DB unchanged |

## Ollama / advisor errors (only for `advise` and live RAG)

| Exception & message | Cause | Resolution |
|---|---|---|
| `RuntimeError: Could not reach Ollama at … after N attempts` | Ollama down or model not pulled | Start Ollama; `ollama pull granite4.2:8b` / `nomic-embed-text`. Run `health_check()` first |
| `Advice(grounded=False, "Cannot advise: the books do not reconcile …")` | `advise()` called on an unbalanced journal | Not an exception — advice is *refused* over inconsistent books. Fix the journal, then re-ask |

## Principle

Deterministic engine calls (P&L, balance sheet, cash flow, trial balance,
reconcile) do **not** raise on well-formed input — they return results with
`validation_warnings()` / reconciliation failures surfaced in the data, so a
caller always sees problems rather than catching exceptions mid-report.
