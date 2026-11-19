"""Property-based accounting invariants (prompt 9.7).

No Hypothesis dependency (prompt: don't add deps unnecessarily) — we generate
many randomised-but-seeded cases with the stdlib and assert invariants hold.
"""

import random
from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.models import AccountGroup
from fin_engine.reconciliation import reconcile


def _chart():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("2000", "AP", AccountGroup.LIABILITY))
    coa.add(Account("3000", "Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE, current=False))
    return coa


def test_equal_debit_credit_preserves_balance():
    """Adding any balanced entry keeps the whole journal balanced."""
    rng = random.Random(42)
    coa = _chart()
    j = Journal(entity="demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "10000"), Posting("3000", "-10000")]))
    for i in range(100):
        amt = Decimal(rng.randint(1, 100000))
        j.post(JournalEntry(f"S{i}", "2026-11-02", "sale",
                            [Posting("1000", amt), Posting("4000", -amt)]))
        assert j.is_balanced()


def test_reversal_offsets_movements():
    """Reversing a posted entry nets its account movements back to prior."""
    rng = random.Random(7)
    coa = _chart()
    for i in range(50):
        j = Journal(entity="demo", chart=coa)
        amt = Decimal(rng.randint(1, 50000))
        j.post(JournalEntry("A", "2026-11-01", "sale",
                            [Posting("1000", amt), Posting("4000", -amt)]))
        before = j.balance("1000")
        j.reverse("A", "AR", "2026-11-02")
        assert j.balance("1000") == before - amt  # back to pre-entry (0 here)
        assert j.balance("1000") == Decimal("0")


def test_random_balanced_company_always_reconciles():
    """Any journal built only from balanced entries passes reconciliation."""
    rng = random.Random(123)
    for trial in range(30):
        coa = _chart()
        j = Journal(entity="demo", chart=coa)
        cap = Decimal(rng.randint(1000, 99999))
        j.post(JournalEntry("E0", "2026-11-01", "capital",
                            [Posting("1000", cap), Posting("3000", -cap)]))
        for i in range(rng.randint(1, 10)):
            amt = Decimal(rng.randint(1, 10000))
            j.post(JournalEntry(f"T{i}", "2026-11-05", "sale",
                                [Posting("1000", amt), Posting("4000", -amt)]))
        rep = reconcile(j, coa, as_of="2026-11-30")
        assert rep.passed, rep.failures


def test_reconciliation_detects_injected_imbalance():
    """A deliberately corrupted entry is always caught."""
    rng = random.Random(99)
    for trial in range(30):
        coa = _chart()
        j = Journal(entity="demo", chart=coa)
        amt = Decimal(rng.randint(2, 10000))
        j.post(JournalEntry("E0", "2026-11-01", "capital",
                            [Posting("1000", amt), Posting("3000", -amt)]))
        # Corrupt the credit by a random non-zero delta -> unbalanced.
        delta = Decimal(rng.randint(1, int(amt) - 1))
        e = j.entries[0]
        object.__setattr__(e, "postings",
                           (Posting("1000", amt), Posting("3000", -(amt - delta))))
        rep = reconcile(j, coa, as_of="2026-11-30")
        assert not rep.passed
