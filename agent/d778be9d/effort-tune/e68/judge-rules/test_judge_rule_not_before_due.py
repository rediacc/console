"""Proposed judge rule not-before-due (observation 1, e68, rows eo-9dd5fd14 eo-e65a852f). Self-contained."""

import datetime
import re

_NB = re.compile(r"NOT-BEFORE:(\d{4}-\d\d-\d\dT\d\d:\d\dZ)")


def matches(reason, item_line, now_utc):
    """True when the reason calls an item due that carries a NOT-BEFORE instant after now_utc (a UTC datetime)."""
    stamps = _NB.findall(item_line)
    if not stamps or not re.search(r"(?i)\bdue\b", reason):
        return False
    when = datetime.datetime.strptime(
        stamps[-1], "%Y-%m-%dT%H:%M:%SZ" if stamps[-1].count(":") > 1 else "%Y-%m-%dT%H:%MZ"
    ).replace(tzinfo=datetime.UTC)
    return now_utc < when


def test_flags_due_before_instant():
    line = "pins T13 NOT-BEFORE:2026-10-15T00:00Z"
    assert matches(
        "Pins T13 is due and local.",
        line,
        datetime.datetime(2026, 10, 14, 22, 11, tzinfo=datetime.UTC),
    )


def test_control_after_instant_and_no_token():
    line = "pins T13 NOT-BEFORE:2026-10-15T00:00Z"
    assert not matches(
        "Pins T13 is due.", line, datetime.datetime(2026, 10, 15, 0, 1, tzinfo=datetime.UTC)
    )
    assert not matches(
        "Pins T13 is due.", "pins T13", datetime.datetime(2026, 10, 14, 22, 11, tzinfo=datetime.UTC)
    )
