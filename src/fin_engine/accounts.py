"""Chart of Accounts (v1.5.0, prompt Part 3).

The single source of account definitions and the single, explicit mapping from
each account to a financial-statement category. Statement classification is
looked up here by ``account_code`` — never guessed from an account's name.

Design: we do NOT introduce a second account taxonomy. The existing
:class:`~fin_engine.models.AccountGroup` already splits revenue/COGS/opex/other-
income/finance-cost/other-expense/tax/asset/liability/equity — exactly the
statement categories the P&L and balance sheet consume. So each account carries
its ``AccountGroup`` directly, and the coarse 5-way ``AccountType`` (asset /
liability / equity / revenue / expense, prompt Part 3.1) plus its normal balance
are *derived* from that group. One mapping, kept in ``_GROUP_FACTS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import AccountGroup


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class NormalBalance(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class StatementCategory(str, Enum):
    """Where an account lands on a statement. Finer than AccountType.

    Balance-sheet accounts (asset/liability) still need a current/non-current
    split, which AccountGroup alone does not give; that split is a per-account
    property (``current``) set in the chart, not inferred.
    """

    CURRENT_ASSET = "current_asset"
    NON_CURRENT_ASSET = "non_current_asset"
    CURRENT_LIABILITY = "current_liability"
    NON_CURRENT_LIABILITY = "non_current_liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    COGS = "cogs"
    OPERATING_EXPENSE = "operating_expense"
    OTHER_INCOME = "other_income"
    FINANCE_COST = "finance_cost"
    OTHER_EXPENSE = "other_expense"
    TAX = "tax"


# The one mapping: AccountGroup -> (coarse type, normal balance). Deriving these
# keeps a single source of truth; adding an account only needs its group.
_GROUP_FACTS: dict[AccountGroup, tuple[AccountType, NormalBalance]] = {
    AccountGroup.ASSET: (AccountType.ASSET, NormalBalance.DEBIT),
    AccountGroup.LIABILITY: (AccountType.LIABILITY, NormalBalance.CREDIT),
    AccountGroup.EQUITY: (AccountType.EQUITY, NormalBalance.CREDIT),
    AccountGroup.REVENUE: (AccountType.REVENUE, NormalBalance.CREDIT),
    AccountGroup.OTHER_INCOME: (AccountType.REVENUE, NormalBalance.CREDIT),
    AccountGroup.COGS: (AccountType.EXPENSE, NormalBalance.DEBIT),
    AccountGroup.OPERATING_EXPENSE: (AccountType.EXPENSE, NormalBalance.DEBIT),
    AccountGroup.FINANCE_COST: (AccountType.EXPENSE, NormalBalance.DEBIT),
    AccountGroup.OTHER_EXPENSE: (AccountType.EXPENSE, NormalBalance.DEBIT),
    AccountGroup.TAX: (AccountType.EXPENSE, NormalBalance.DEBIT),
}

# AccountGroup -> StatementCategory for P&L/equity/income groups. Assets and
# liabilities are split current/non-current per account, handled in Account.
_GROUP_STATEMENT: dict[AccountGroup, StatementCategory] = {
    AccountGroup.REVENUE: StatementCategory.REVENUE,
    AccountGroup.COGS: StatementCategory.COGS,
    AccountGroup.OPERATING_EXPENSE: StatementCategory.OPERATING_EXPENSE,
    AccountGroup.OTHER_INCOME: StatementCategory.OTHER_INCOME,
    AccountGroup.FINANCE_COST: StatementCategory.FINANCE_COST,
    AccountGroup.OTHER_EXPENSE: StatementCategory.OTHER_EXPENSE,
    AccountGroup.TAX: StatementCategory.TAX,
    AccountGroup.EQUITY: StatementCategory.EQUITY,
}


@dataclass(frozen=True)
class Account:
    """One account in the chart.

    ``group`` is the authoritative classification; ``account_type`` and
    ``normal_balance`` are derived from it (not stored redundantly). ``current``
    only matters for assets/liabilities (their current vs non-current split) and
    is ignored for other groups.
    """

    code: str
    name: str
    group: AccountGroup
    current: bool = True            # current vs non-current (asset/liability only)
    parent_code: Optional[str] = None
    is_active: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("account code must be non-empty")
        if self.group not in _GROUP_FACTS:
            raise ValueError(f"unknown account group {self.group!r}")

    @property
    def account_type(self) -> AccountType:
        return _GROUP_FACTS[self.group][0]

    @property
    def normal_balance(self) -> NormalBalance:
        return _GROUP_FACTS[self.group][1]

    @property
    def statement_category(self) -> StatementCategory:
        """Explicit statement bucket. Current/non-current split for BS accounts."""
        if self.group is AccountGroup.ASSET:
            return (StatementCategory.CURRENT_ASSET if self.current
                    else StatementCategory.NON_CURRENT_ASSET)
        if self.group is AccountGroup.LIABILITY:
            return (StatementCategory.CURRENT_LIABILITY if self.current
                    else StatementCategory.NON_CURRENT_LIABILITY)
        return _GROUP_STATEMENT[self.group]


@dataclass
class ChartOfAccounts:
    """Registry of accounts for one entity, with validation (prompt 3.3)."""

    entity: str
    _accounts: dict[str, Account] = field(default_factory=dict)

    def add(self, account: Account) -> None:
        if account.code in self._accounts:
            raise ValueError(f"duplicate account code {account.code!r}")
        if account.parent_code is not None:
            if account.parent_code not in self._accounts:
                raise ValueError(
                    f"account {account.code!r} references unknown parent "
                    f"{account.parent_code!r}"
                )
            # No cycles: walk the parent chain; a code reappearing is a cycle.
            seen = {account.code}
            cur = account.parent_code
            while cur is not None:
                if cur in seen:
                    raise ValueError(
                        f"circular parent relationship at {account.code!r}"
                    )
                seen.add(cur)
                cur = self._accounts[cur].parent_code
        self._accounts[account.code] = account

    def get(self, code: str) -> Account:
        try:
            return self._accounts[code]
        except KeyError:
            raise KeyError(f"no account {code!r} in {self.entity!r} chart")

    def __contains__(self, code: str) -> bool:
        return code in self._accounts

    def validate_postable(self, code: str) -> Account:
        """Return the account if a posting may reference it, else raise.

        Enforces prompt 3.3/4.2: unknown or inactive accounts are rejected
        before a journal entry can post to them.
        """
        acct = self.get(code)  # raises KeyError if unknown
        if not acct.is_active:
            raise ValueError(f"account {code!r} is inactive; cannot post to it")
        return acct

    def accounts(self) -> list[Account]:
        return list(self._accounts.values())


# Starter chart (prompt 3.2). A configuration, not a statutory CoA; callers add
# their own. Long-term loans are non-current; everything else here is current by
# the prompt's example. Equipment is a non-current asset.
_STARTER: list[tuple[str, str, AccountGroup, bool]] = [
    ("1000", "Cash", AccountGroup.ASSET, True),
    ("1010", "Bank", AccountGroup.ASSET, True),
    ("1100", "Accounts Receivable", AccountGroup.ASSET, True),
    ("1200", "Inventory", AccountGroup.ASSET, True),
    ("1500", "Equipment", AccountGroup.ASSET, False),
    ("2000", "Accounts Payable", AccountGroup.LIABILITY, True),
    ("2100", "Short-term Loans", AccountGroup.LIABILITY, True),
    ("2200", "Long-term Loans", AccountGroup.LIABILITY, False),
    ("3000", "Owner's Equity", AccountGroup.EQUITY, False),
    ("3100", "Retained Earnings", AccountGroup.EQUITY, False),
    ("4000", "Sales Revenue", AccountGroup.REVENUE, False),
    ("5000", "Cost of Goods Sold", AccountGroup.COGS, False),
    ("6000", "Salaries", AccountGroup.OPERATING_EXPENSE, False),
    ("6100", "Rent", AccountGroup.OPERATING_EXPENSE, False),
    ("6200", "Utilities", AccountGroup.OPERATING_EXPENSE, False),
    ("6300", "Marketing", AccountGroup.OPERATING_EXPENSE, False),
    ("7000", "Finance Costs", AccountGroup.FINANCE_COST, False),
    ("7100", "Tax Expense", AccountGroup.TAX, False),
]


def starter_chart(entity: str) -> ChartOfAccounts:
    """A ready-to-use chart matching the prompt's example (prompt 3.2)."""
    coa = ChartOfAccounts(entity=entity)
    for code, name, group, current in _STARTER:
        coa.add(Account(code=code, name=name, group=group, current=current))
    return coa
