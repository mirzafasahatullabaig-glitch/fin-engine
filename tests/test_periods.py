"""Date and period validation tests (prompt 9, Part 7). Hand-specified ranges."""

import pytest
from datetime import date

from fin_engine.periods import (
    date_in_period, parse_date, resolve_period, validate_range,
)


def test_parse_valid_iso_date():
    assert parse_date("2026-11-20") == date(2026, 11, 20)


@pytest.mark.parametrize("bad", [
    "2026-02-30",   # impossible day
    "2026-13-01",   # impossible month
    "2026/11/20",   # wrong separator
    "20-11-2026",   # wrong order
    "",             # empty
    "2026-11",      # not a full date
])
def test_parse_bad_date_rejected(bad):
    with pytest.raises(ValueError):
        parse_date(bad)


def test_resolve_month():
    pr = resolve_period("2026-11")
    assert pr.start == date(2026, 11, 1)
    assert pr.end == date(2026, 11, 30)


def test_resolve_quarter():
    pr = resolve_period("2026-Q4")
    assert pr.start == date(2026, 10, 1)
    assert pr.end == date(2026, 12, 31)


def test_resolve_year():
    pr = resolve_period("2026")
    assert pr.start == date(2026, 1, 1)
    assert pr.end == date(2026, 12, 31)


def test_leap_year_february():
    assert resolve_period("2024-02").end == date(2024, 2, 29)   # leap
    assert resolve_period("2026-02").end == date(2026, 2, 28)   # non-leap


def test_q1_leap_year_end():
    # Q1 ends 31 March regardless, but Feb length inside differs; range end is
    # the quarter end, 31 March.
    assert resolve_period("2024-Q1").end == date(2024, 3, 31)


def test_bad_period_label_rejected():
    for bad in ("2026-Q5", "2026-00", "2026-M1", "nonsense", "26-11"):
        with pytest.raises(ValueError):
            resolve_period(bad)


def test_date_in_period():
    assert date_in_period("2026-11-15", "2026-11")
    assert not date_in_period("2026-12-01", "2026-11")
    assert date_in_period("2026-11-15", "2026-Q4")
    assert date_in_period("2026-11-15", "2026")


def test_validate_range_rejects_reversed():
    assert validate_range("2026-01-01", "2026-12-31")
    with pytest.raises(ValueError, match="after end"):
        validate_range("2026-12-31", "2026-01-01")
