"""Parse period labels used by the sources into (start date, frequency)."""

from __future__ import annotations

import re
from datetime import date

_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "D"),
    (re.compile(r"^(\d{4})-?Q([1-4])$"), "Q"),
    (re.compile(r"^(\d{4})-?S([12])$"), "S"),
    (re.compile(r"^(\d{4})-?H([12])$"), "S"),
    (re.compile(r"^(\d{4})-?M?(\d{2})$"), "M"),
    (re.compile(r"^(\d{4})-W(\d{2})$"), "W"),
    (re.compile(r"^(\d{4})(?:-A)?$"), "A"),
]


def parse_period(label: str) -> tuple[date, str]:
    """Return the first day of the period and its frequency code.

    >>> parse_period("2026-Q3")
    (datetime.date(2026, 7, 1), 'Q')
    """
    text = label.strip()
    for pattern, freq in _PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        year = int(m.group(1))
        if freq == "D":
            return date(year, int(m.group(2)), int(m.group(3))), "D"
        if freq == "Q":
            return date(year, 3 * int(m.group(2)) - 2, 1), "Q"
        if freq == "S":
            return date(year, 6 * int(m.group(2)) - 5, 1), "S"
        if freq == "M":
            month = int(m.group(2))
            if 1 <= month <= 12:
                return date(year, month, 1), "M"
            continue
        if freq == "W":
            return date.fromisocalendar(year, int(m.group(2)), 1), "W"
        return date(year, 1, 1), "A"
    raise ValueError(f"unrecognised period label: {label!r}")


def period_label(start: date, freq: str) -> str:
    """Canonical label for a period start date."""
    if freq == "A":
        return f"{start.year}"
    if freq == "Q":
        return f"{start.year}-Q{(start.month - 1) // 3 + 1}"
    if freq == "S":
        return f"{start.year}-S{(start.month - 1) // 6 + 1}"
    if freq == "M":
        return f"{start.year}-{start.month:02d}"
    return start.isoformat()


def shift(start: date, freq: str, n: int) -> date:
    """Move a period start by n periods (M, Q, S, A only)."""
    months = {"M": 1, "Q": 3, "S": 6, "A": 12}[freq] * n
    total = start.year * 12 + start.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)
