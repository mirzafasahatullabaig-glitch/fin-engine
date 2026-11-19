"""Balance sheet and liquidity ratio tests.

Expected values are computed by hand and asserted literally (report §9).
"""

from decimal import Decimal

from fin_engine import BalanceSheet


def _bs(**kw):
    base = dict(
        entity="demo", as_of="2026-11-30",
        current_assets="150000", non_current_assets="350000",
        current_liabilities="100000", non_current_liabilities="200000",
        equity="200000", inventory="60000",
    )
    base.update(kw)
    return BalanceSheet(**base)


def test_totals_and_identity_hold():
    bs = _bs()
    assert bs.total_assets == Decimal("500000")
    assert bs.total_liabilities == Decimal("300000")
    # 500000 == 300000 + 200000 -> balances, no warning
    assert bs.validation_warnings() == []


def test_working_capital():
    # 150000 - 100000 = 50000
    assert _bs().working_capital == Decimal("50000")


def test_current_ratio():
    # 150000 / 100000 = 1.5
    assert _bs().current_ratio == Decimal("1.5")


def test_quick_ratio_excludes_inventory():
    # (150000 - 60000) / 100000 = 0.9
    assert _bs().quick_ratio == Decimal("0.9")


def test_ratios_none_when_no_current_liabilities():
    bs = _bs(current_liabilities="0", non_current_liabilities="300000")
    assert bs.current_ratio is None
    assert bs.quick_ratio is None
    assert bs.working_capital == Decimal("150000")


def test_imbalance_is_flagged():
    # equity too high by 1 -> identity broken, warning surfaced not hidden
    bs = _bs(equity="200001")
    warnings = bs.validation_warnings()
    assert any("does not balance" in w for w in warnings)


def test_negative_working_capital_flagged():
    bs = _bs(current_assets="80000", current_liabilities="100000",
             equity="180000")  # keep identity: assets 430000 = 300000+? -> adjust
    # total_assets = 80000+350000 = 430000; liab+equity = 300000+180000 = 480000
    # that would double-flag; use a clean set instead:
    bs = BalanceSheet(
        entity="demo", as_of="2026-11-30",
        current_assets="80000", non_current_assets="350000",
        current_liabilities="100000", non_current_liabilities="130000",
        equity="200000", inventory="0",
    )
    # assets 430000 == liab 230000 + equity 200000 -> identity OK
    warnings = bs.validation_warnings()
    assert any("negative working capital" in w for w in warnings)
    assert not any("does not balance" in w for w in warnings)
