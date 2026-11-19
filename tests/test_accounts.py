"""Chart of Accounts tests (prompt 9.1).

Expected derivations (type, normal balance, statement category) are specified
here by hand, independent of the module's mapping tables.
"""

import pytest

from fin_engine.accounts import (
    Account, AccountType, ChartOfAccounts, NormalBalance, StatementCategory,
    starter_chart,
)
from fin_engine.models import AccountGroup


def test_derived_type_and_normal_balance():
    cash = Account("1000", "Cash", AccountGroup.ASSET)
    assert cash.account_type is AccountType.ASSET
    assert cash.normal_balance is NormalBalance.DEBIT

    sales = Account("4000", "Sales", AccountGroup.REVENUE)
    assert sales.account_type is AccountType.REVENUE
    assert sales.normal_balance is NormalBalance.CREDIT

    cogs = Account("5000", "COGS", AccountGroup.COGS)
    assert cogs.account_type is AccountType.EXPENSE
    assert cogs.normal_balance is NormalBalance.DEBIT


def test_statement_category_current_vs_non_current():
    # Same group, different current flag -> different statement bucket.
    cash = Account("1000", "Cash", AccountGroup.ASSET, current=True)
    equip = Account("1500", "Equipment", AccountGroup.ASSET, current=False)
    assert cash.statement_category is StatementCategory.CURRENT_ASSET
    assert equip.statement_category is StatementCategory.NON_CURRENT_ASSET

    ap = Account("2000", "AP", AccountGroup.LIABILITY, current=True)
    ltl = Account("2200", "LT Loan", AccountGroup.LIABILITY, current=False)
    assert ap.statement_category is StatementCategory.CURRENT_LIABILITY
    assert ltl.statement_category is StatementCategory.NON_CURRENT_LIABILITY


def test_pnl_statement_categories():
    assert Account("7000", "Fin", AccountGroup.FINANCE_COST).statement_category \
        is StatementCategory.FINANCE_COST
    assert Account("7100", "Tax", AccountGroup.TAX).statement_category \
        is StatementCategory.TAX


def test_duplicate_code_rejected():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    with pytest.raises(ValueError, match="duplicate account code"):
        coa.add(Account("1000", "Cash again", AccountGroup.ASSET))


def test_unknown_parent_rejected():
    coa = ChartOfAccounts("demo")
    with pytest.raises(ValueError, match="unknown parent"):
        coa.add(Account("1001", "Petty Cash", AccountGroup.ASSET,
                        parent_code="9999"))


def test_circular_parent_rejected():
    # Seed a chart that already contains a parent loop X->Y->X (accounts are
    # frozen, so inject directly), then adding anything on that chain must fail.
    loop = ChartOfAccounts("demo")
    loop._accounts["X"] = Account("X", "X", AccountGroup.ASSET, parent_code="Y")
    loop._accounts["Y"] = Account("Y", "Y", AccountGroup.ASSET, parent_code="X")
    with pytest.raises(ValueError, match="circular"):
        loop.add(Account("Z", "Z", AccountGroup.ASSET, parent_code="X"))


def test_inactive_account_not_postable():
    coa = ChartOfAccounts("demo")
    coa.add(Account("6000", "Old Salaries", AccountGroup.OPERATING_EXPENSE,
                    is_active=False))
    with pytest.raises(ValueError, match="inactive"):
        coa.validate_postable("6000")


def test_unknown_account_not_postable():
    coa = ChartOfAccounts("demo")
    with pytest.raises(KeyError):
        coa.validate_postable("1000")


def test_valid_account_is_postable():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    assert coa.validate_postable("1000").name == "Cash"


def test_starter_chart_shape():
    coa = starter_chart("demo")
    assert len(coa.accounts()) == 18
    assert coa.get("1500").statement_category is StatementCategory.NON_CURRENT_ASSET
    assert coa.get("2200").statement_category is StatementCategory.NON_CURRENT_LIABILITY
    assert coa.get("4000").statement_category is StatementCategory.REVENUE
