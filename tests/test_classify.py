"""Golden classification tests (report §7.1 JSON test + §7.4 dual labels)."""

from fin_engine import classify_transaction
from fin_engine.models import AccountGroup, CashFlowCategory


def test_sale_is_revenue_operating():
    c = classify_transaction("Sale of goods to customer")
    assert c.group is AccountGroup.REVENUE
    assert c.cash_flow is CashFlowCategory.OPERATING
    assert not c.needs_review


def test_rent_is_opex_operating():
    c = classify_transaction("Monthly office rent")
    assert c.group is AccountGroup.OPERATING_EXPENSE
    assert c.cash_flow is CashFlowCategory.OPERATING


def test_machinery_is_asset_investing():
    c = classify_transaction("Purchase of machinery")
    assert c.group is AccountGroup.ASSET
    assert c.cash_flow is CashFlowCategory.INVESTING


def test_loan_is_liability_financing():
    """The §7.1 case that needs dual labels: liability AND financing inflow."""
    c = classify_transaction("Bank loan received")
    assert c.group is AccountGroup.LIABILITY
    assert c.cash_flow is CashFlowCategory.FINANCING


def test_electricity_is_opex_operating():
    c = classify_transaction("Electricity bill payment")
    assert c.group is AccountGroup.OPERATING_EXPENSE
    assert c.cash_flow is CashFlowCategory.OPERATING


def test_unknown_is_flagged_for_review():
    c = classify_transaction("Miscellaneous settlement 4471-X")
    assert c.needs_review
    assert c.confidence == "low"
    assert c.matched_rule == ""


def test_empty_description_is_flagged():
    assert classify_transaction("").needs_review


# --- regression tests for the substring-matching bug (audit finding #1) ---
def test_wholesale_does_not_match_sale():
    """'wholesale' must NOT be classified as revenue via the 'sale' keyword."""
    c = classify_transaction("Wholesale distribution agreement")
    assert c.group is not AccountGroup.REVENUE


def test_office_building_is_capital_asset_not_opex():
    c = classify_transaction("Office building purchase")
    assert c.group is AccountGroup.ASSET
    assert c.cash_flow is CashFlowCategory.INVESTING


def test_insurance_claim_received_is_flagged_not_expense():
    """Income ('claim received') matched as expense -> ambiguous -> review."""
    c = classify_transaction("Insurance claim received")
    assert c.needs_review


def test_multiple_conflicting_rules_flagged_for_review():
    """'Loan received for new machinery' matches two different rules."""
    c = classify_transaction("Loan received for new machinery")
    assert c.needs_review


def test_clear_single_match_is_high_confidence():
    c = classify_transaction("Monthly office rent payment")
    assert not c.needs_review
    assert c.group is AccountGroup.OPERATING_EXPENSE
