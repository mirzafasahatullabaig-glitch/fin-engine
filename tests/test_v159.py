"""v1.5.9 tests: backup/restore/integrity (#2), authorization seam (#1)."""

import pytest
from decimal import Decimal

from fin_engine import (
    Account, AllowAll, ChartOfAccounts, Journal, JournalEntry, Permission,
    Posting, RoleBasedAuthorizer, advise, require, starter_chart,
)
from fin_engine.authz import PermissionError_
from fin_engine.store import JournalStore


# --- #2 backup / restore / integrity -------------------------------------
def _seeded_store(path):
    coa = starter_chart("demo")
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "5000"), Posting("3000", "-5000")]))
    s = JournalStore(path)
    s.save_journal(j)
    return s


def test_backup_and_restore_round_trip(tmp_path):
    live = _seeded_store(str(tmp_path / "live.db"))
    backup = str(tmp_path / "backup.db")
    live.backup(backup)
    live.close()
    # Restore to a new location and confirm the data is intact.
    restored = JournalStore.restore(backup, str(tmp_path / "restored.db"))
    j = restored.load_journal("demo")
    assert j.balance("1000") == Decimal("5000")
    restored.close()


def test_integrity_check_passes_on_healthy_db(tmp_path):
    s = _seeded_store(str(tmp_path / "ok.db"))
    assert s.integrity_check() is True
    s.close()


def test_backup_is_consistent_snapshot(tmp_path):
    # Backing up while open must produce a valid, integrity-clean copy.
    s = _seeded_store(str(tmp_path / "live.db"))
    b = str(tmp_path / "snap.db")
    s.backup(b)
    s.close()
    copy = JournalStore(b)
    assert copy.integrity_check() is True
    copy.close()


# --- #1 authorization seam -----------------------------------------------
def test_default_allows_everything():
    a = AllowAll()
    assert a.allowed(Permission.POST, "anyone") is True
    require(a, Permission.ADMIN, "anyone")  # does not raise


def test_role_based_grants_and_denies():
    authz = RoleBasedAuthorizer(principals={"alice": "viewer", "bob": "admin"})
    assert authz.allowed(Permission.READ, "alice") is True
    assert authz.allowed(Permission.POST, "alice") is False   # viewer can't post
    assert authz.allowed(Permission.ADMIN, "bob") is True
    assert authz.allowed(Permission.READ, "stranger") is False  # unknown principal


def test_require_raises_on_denial():
    authz = RoleBasedAuthorizer(principals={"alice": "viewer"})
    with pytest.raises(PermissionError):
        require(authz, Permission.POST, "alice")


def test_advise_respects_authorizer():
    coa = starter_chart("demo")
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "100"), Posting("3000", "-100")]))

    class _KB:
        def retrieve(self, q, k=3):
            return []

    authz = RoleBasedAuthorizer(principals={"alice": "viewer"})  # no ADVISE
    with pytest.raises(PermissionError):
        advise("x", j, coa, "2026-11", "2026-11-30", _KB(),
               generate=lambda p: "advice", authorizer=authz, principal="alice")


def test_advise_allowed_for_bookkeeper():
    coa = starter_chart("demo")
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "100"), Posting("3000", "-100")]))

    class _KB:
        def retrieve(self, q, k=3):
            return []

    authz = RoleBasedAuthorizer(principals={"bob": "bookkeeper"})
    adv = advise("x", j, coa, "2026-11", "2026-11-30", _KB(),
                 generate=lambda p: "ok advice", authorizer=authz, principal="bob")
    assert adv.recommendation == "ok advice"  # permitted, ran normally
