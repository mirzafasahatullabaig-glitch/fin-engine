"""Golden cash-flow tests (report §7.4 dual-classification example)."""

from decimal import Decimal

from fin_engine import calculate_cash_flow
from fin_engine.cashflow import CashMovement
from fin_engine.models import CashFlowCategory


def test_sections_sum_to_net():
    movements = [
        CashMovement(CashFlowCategory.OPERATING, "500000", "sales collected"),
        CashMovement(CashFlowCategory.OPERATING, "-100000", "opex paid"),
        CashMovement(CashFlowCategory.INVESTING, "-200000", "bought machinery"),
        CashMovement(CashFlowCategory.FINANCING, "300000", "bank loan received"),
        CashMovement(CashFlowCategory.FINANCING, "-5000", "interest paid"),
    ]
    cf = calculate_cash_flow("demo", "2026-11", movements)
    assert cf.operating == Decimal("400000")
    assert cf.investing == Decimal("-200000")
    assert cf.financing == Decimal("295000")
    assert cf.net_change == Decimal("495000")


def test_loan_is_financing_not_operating():
    """Report §7.4: a bank loan received is a FINANCING inflow."""
    cf = calculate_cash_flow(
        "demo", "2026-11",
        [CashMovement(CashFlowCategory.FINANCING, "300000", "bank loan")],
    )
    assert cf.financing == Decimal("300000")
    assert cf.operating == Decimal("0")


def test_empty_is_zero():
    cf = calculate_cash_flow("demo", "2026-11", [])
    assert cf.net_change == Decimal("0")
