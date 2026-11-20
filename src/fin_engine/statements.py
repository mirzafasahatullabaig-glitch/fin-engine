"""Journal-derived financial statements (v1.5.0, prompt Part 5).

The single-source-of-truth layer: both the P&L and the balance sheet are built
from general-ledger balances, which come from posted journal entries. There is
no separate hand-entered dataset.

We REUSE the existing formulas rather than reimplementing them:
- ``pnl_from_journal`` assembles a :class:`~fin_engine.models.Ledger` of
  magnitudes from GL balances and calls the existing ``calculate_pnl`` — one
  P&L formula, one set of golden tests.
- ``balance_sheet_from_journal`` aggregates GL balances by statement category
  and constructs the existing :class:`~fin_engine.balance_sheet.BalanceSheet`,
  whose working-capital / ratio / identity logic is unchanged.

A P&L covers a PERIOD (date range); a balance sheet is AS OF a date. They are
not interchangeable (prompt 7.4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .accounts import ChartOfAccounts, StatementCategory
from .balance_sheet import BalanceSheet
from .cashflow import CashFlow
from .journal import EntryStatus, Journal
from .ledger_gl import _signed_net
from .models import AccountGroup, CashFlowCategory, Ledger, LedgerLine
from .pnl import PnL, calculate_pnl


# P&L statement categories -> the AccountGroup the P&L engine expects. The
# current/non-current split does not apply to P&L lines.
_PNL_CATEGORY_TO_GROUP = {
    StatementCategory.REVENUE: AccountGroup.REVENUE,
    StatementCategory.COGS: AccountGroup.COGS,
    StatementCategory.OPERATING_EXPENSE: AccountGroup.OPERATING_EXPENSE,
    StatementCategory.OTHER_INCOME: AccountGroup.OTHER_INCOME,
    StatementCategory.FINANCE_COST: AccountGroup.FINANCE_COST,
    StatementCategory.OTHER_EXPENSE: AccountGroup.OTHER_EXPENSE,
    StatementCategory.TAX: AccountGroup.TAX,
}


def _period_magnitude(journal: Journal, chart: ChartOfAccounts, code: str,
                      start: Optional[str], end: Optional[str]) -> Decimal:
    """Normal-balance-positive magnitude of an account's movement in a period.

    P&L accounts accumulate over a period (not as-of a date), so we net the
    signed postings in [start, end] and flip to the account's normal side. A
    revenue account (credit-normal) with net credit returns a positive revenue.
    """
    acct = chart.get(code)
    signed = _signed_net(journal, code, start, end)
    from .accounts import NormalBalance
    return signed if acct.normal_balance is NormalBalance.DEBIT else -signed


def pnl_from_journal(journal: Journal, chart: ChartOfAccounts, period: str,
                     start: Optional[str] = None,
                     end: Optional[str] = None) -> PnL:
    """Build a P&L for a period from journal balances (prompt 5.1).

    ``start``/``end`` bound the period (inclusive ISO dates). If omitted, they
    are resolved from the ``period`` label (``2026-11`` -> that month's range)
    when it is a recognised label; an unrecognised label falls back to the whole
    journal. ``period`` is the label carried onto the result. Reuses
    ``calculate_pnl`` so the PBT formula is identical to v1.4.0.
    """
    if start is None and end is None:
        try:
            from .periods import resolve_period
            pr = resolve_period(period)
            start, end = pr.start_iso(), pr.end_iso()
        except ValueError:
            pass  # opaque label (not YYYY-MM/Qn/YYYY): use the whole journal

    # Aggregate the SIGNED net per P&L group. A refund is a debit to revenue
    # that nets within the revenue group (sales - refunds); a reversal nets the
    # same way. We sum net-of-contra per group rather than per account, so a
    # refund correctly reduces revenue instead of crashing the P&L (v1.5.4 #4).
    group_net: dict = {}
    for acct in chart.accounts():
        group = _PNL_CATEGORY_TO_GROUP.get(acct.statement_category)
        if group is None:
            continue  # balance-sheet account (incl. inventory), not a P&L line
        mag = _period_magnitude(journal, chart, acct.code, start, end)
        group_net[group] = group_net.get(group, Decimal(0)) + mag

    # calculate_pnl consumes LedgerLines (amount >= 0) summed per group, so a
    # non-negative group net maps straight to a line. A group whose net went
    # contra (e.g. refunds exceeded sales) can't be a LedgerLine; compute the
    # P&L directly for that rare case so the real (signed) figure flows through.
    if all(v >= 0 for v in group_net.values()):
        lines = [LedgerLine(group=g, amount=v) for g, v in group_net.items() if v]
        return calculate_pnl(Ledger(entity=journal.entity, period=period,
                                    lines=lines))
    return _pnl_from_group_net(journal.entity, period, group_net)


# Which cash-flow section a non-cash leg's statement category implies. Investing
# = (de)investment in non-current assets; financing = loans, equity, dividends;
# everything else (revenue, expenses, current assets/liabilities) is operating.
_CATEGORY_TO_CASHFLOW = {
    StatementCategory.NON_CURRENT_ASSET: CashFlowCategory.INVESTING,
    StatementCategory.NON_CURRENT_LIABILITY: CashFlowCategory.FINANCING,
    StatementCategory.CURRENT_LIABILITY: CashFlowCategory.OPERATING,
    StatementCategory.EQUITY: CashFlowCategory.FINANCING,
    StatementCategory.FINANCE_COST: CashFlowCategory.FINANCING,
}


def cash_flow_from_journal(journal: Journal, chart: ChartOfAccounts, period: str,
                           start=None, end=None) -> CashFlow:
    """Direct-method cash flow derived from the journal (v1.5.7).

    For each posted entry that moves a cash account (``Account.is_cash``), the
    cash delta is the net of its cash-account postings. The entry's NON-cash
    legs decide the section: a credit to Sales -> operating, a debit to
    Equipment (non-current asset) -> investing, a loan or equity leg ->
    financing. Short-term loans map by their non-current flag.

    This is a genuine direct-method statement reconciled to the journal:
    ``net_change`` equals the actual change in cash-account balances over the
    period. It is NOT an indirect statement (no working-capital adjustments);
    see docs. Categories are never invented — an entry with no classifiable
    non-cash leg defaults to operating and is the documented edge.
    """
    if start is None and end is None:
        try:
            from .periods import resolve_period
            pr = resolve_period(period)
            start, end = pr.start_iso(), pr.end_iso()
        except ValueError:
            pass
    cash_codes = {a.code for a in chart.accounts() if a.is_cash}
    totals = {CashFlowCategory.OPERATING: Decimal(0),
              CashFlowCategory.INVESTING: Decimal(0),
              CashFlowCategory.FINANCING: Decimal(0)}
    for e in journal.entries:
        if e.status is EntryStatus.DRAFT:
            continue
        if start is not None and e.date < start:
            continue
        if end is not None and e.date > end:
            continue
        cash_delta = sum((p.amount for p in e.postings
                          if p.account in cash_codes), Decimal(0))
        if cash_delta == 0:
            continue  # no cash moved in this entry
        # Section from the non-cash legs. Short-term loans (current liability)
        # are financing even though current, so special-case loan accounts by
        # group; otherwise use the category map, defaulting to operating.
        section = CashFlowCategory.OPERATING
        for p in e.postings:
            if p.account in cash_codes:
                continue
            acct = chart.get(p.account)
            if acct.group is AccountGroup.LIABILITY and "loan" in acct.name.lower():
                section = CashFlowCategory.FINANCING
                break
            mapped = _CATEGORY_TO_CASHFLOW.get(acct.statement_category)
            if mapped is not None:
                section = mapped
                break
        totals[section] += cash_delta
    op = totals[CashFlowCategory.OPERATING]
    inv = totals[CashFlowCategory.INVESTING]
    fin = totals[CashFlowCategory.FINANCING]
    return CashFlow(entity=journal.entity, period=period, operating=op,
                    investing=inv, financing=fin, net_change=op + inv + fin)


def _pnl_from_group_net(entity: str, period: str, group_net: dict) -> PnL:
    """Apply the P&L formula to SIGNED per-group totals (contra-safe path).

    Identical formula to calculate_pnl; used only when a group net is negative
    (e.g. net-negative revenue from refunds), which a LedgerLine can't hold.
    """
    g = lambda grp: group_net.get(grp, Decimal(0))
    revenue = g(AccountGroup.REVENUE)
    cogs = g(AccountGroup.COGS)
    opex = g(AccountGroup.OPERATING_EXPENSE)
    other_income = g(AccountGroup.OTHER_INCOME)
    finance_costs = g(AccountGroup.FINANCE_COST)
    other_expenses = g(AccountGroup.OTHER_EXPENSE)
    tax = g(AccountGroup.TAX)
    gross_profit = revenue - cogs
    ebit = gross_profit - opex
    pbt = ebit + other_income - finance_costs - other_expenses
    return PnL(entity=entity, period=period, revenue=revenue, cogs=cogs,
               gross_profit=gross_profit, operating_expenses=opex, ebit=ebit,
               other_income=other_income, finance_costs=finance_costs,
               other_expenses=other_expenses, pbt=pbt, tax=tax,
               net_profit=pbt - tax)


def balance_sheet_from_journal(journal: Journal, chart: ChartOfAccounts,
                               as_of: str) -> BalanceSheet:
    """Build a balance sheet as of a date from journal balances (prompt 5.2).

    Aggregates GL balances by statement category into the existing
    ``BalanceSheet``, whose identity check / working capital / ratios are
    unchanged. Inventory is pulled out (any account named 'inventory') for the
    quick ratio.

    Retained earnings: a journal that has not been period-closed still holds its
    revenue/expense balances in income accounts, so raw equity would omit the
    period's profit and the sheet would not balance. We therefore fold net
    income to date (all revenue - all expenses through ``as_of``) into equity —
    the standard closing-to-retained-earnings step, done here on the fly rather
    than requiring an explicit closing entry. This is documented, not silent:
    see docs/UNIFIED_ACCOUNTING_ARCHITECTURE.md.
    """
    from .accounts import NormalBalance
    totals = {c: Decimal(0) for c in StatementCategory}
    inventory = Decimal(0)
    net_income = Decimal(0)
    income_cats = set(_PNL_CATEGORY_TO_GROUP)  # revenue/cogs/opex/.../tax
    for acct in chart.accounts():
        signed = _signed_net(journal, acct.code, start=None, end=as_of)
        bal = signed if acct.normal_balance is NormalBalance.DEBIT else -signed
        cat = acct.statement_category
        if cat in totals:
            totals[cat] += bal
        if cat in income_cats:
            # Revenue/other-income are credit-normal (bal>0 = income); expenses
            # are debit-normal (bal>0 = cost). Income adds, cost subtracts.
            if cat in (StatementCategory.REVENUE, StatementCategory.OTHER_INCOME):
                net_income += bal
            else:
                net_income -= bal
        if "inventory" in acct.name.lower():
            inventory += bal

    return BalanceSheet(
        entity=journal.entity,
        as_of=as_of,
        current_assets=totals[StatementCategory.CURRENT_ASSET],
        non_current_assets=totals[StatementCategory.NON_CURRENT_ASSET],
        current_liabilities=totals[StatementCategory.CURRENT_LIABILITY],
        non_current_liabilities=totals[StatementCategory.NON_CURRENT_LIABILITY],
        equity=totals[StatementCategory.EQUITY] + net_income,
        inventory=inventory,
    )
