"""Typed date and accounting-period handling (v1.5.0, prompt Part 7).

Period labels stay strings (``"2026-11"``, ``"2026-Q4"``, ``"2026"``) for
backward compatibility; this module adds validation and converts a label to a
concrete inclusive ``(start, end)`` date range so statements can filter by real
boundaries instead of string prefixes. Leap years are handled by the stdlib
``calendar``/``date`` — no hand-rolled month lengths.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")
_YEAR = re.compile(r"^(\d{4})$")


def parse_date(s: str) -> date:
    """Parse a strict ISO ``YYYY-MM-DD`` date, rejecting anything else.

    ``date.fromisoformat`` accepts only real calendar dates, so impossible dates
    (2026-02-30) and bad formats raise ``ValueError`` (prompt 7.1).
    """
    if not isinstance(s, str) or not _ISO.match(s):
        raise ValueError(f"date must be ISO YYYY-MM-DD, got {s!r}")
    return date.fromisoformat(s)  # raises ValueError on impossible dates


@dataclass(frozen=True)
class PeriodRange:
    """A resolved accounting period as an inclusive date range."""

    label: str
    start: date
    end: date

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def start_iso(self) -> str:
        return self.start.isoformat()

    def end_iso(self) -> str:
        return self.end.isoformat()


def resolve_period(label: str) -> PeriodRange:
    """Convert a period label to its inclusive date range (prompt 7.2).

    Supported: ``YYYY-MM`` (month), ``YYYY-Qn`` (quarter), ``YYYY`` (year).
    Month/quarter end days come from the calendar, so leap years are correct
    (``2024-02`` ends 2024-02-29; ``2026-02`` ends 2026-02-28).
    """
    m = _MONTH.match(label)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if not 1 <= month <= 12:
            raise ValueError(f"invalid month in period {label!r}")
        last = calendar.monthrange(year, month)[1]
        return PeriodRange(label, date(year, month, 1), date(year, month, last))

    q = _QUARTER.match(label)
    if q:
        year, quarter = int(q.group(1)), int(q.group(2))
        start_month = 3 * (quarter - 1) + 1
        end_month = start_month + 2
        last = calendar.monthrange(year, end_month)[1]
        return PeriodRange(label, date(year, start_month, 1),
                           date(year, end_month, last))

    y = _YEAR.match(label)
    if y:
        year = int(y.group(1))
        return PeriodRange(label, date(year, 1, 1), date(year, 12, 31))

    raise ValueError(
        f"unrecognised period {label!r}; use YYYY-MM, YYYY-Qn or YYYY"
    )


def date_in_period(date_iso: str, period_label: str) -> bool:
    """True iff a transaction date falls within a period (prompt 7.3)."""
    return resolve_period(period_label).contains(parse_date(date_iso))


def validate_range(start_iso: str, end_iso: str) -> tuple[date, date]:
    """Validate a start/end range: both ISO, start <= end. Returns the dates."""
    start, end = parse_date(start_iso), parse_date(end_iso)
    if start > end:
        raise ValueError(f"period start {start_iso} is after end {end_iso}")
    return start, end
