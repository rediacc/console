"""Proposed judge rule utc-clock (observation 3, e68, row eo-e65a852f). Self-contained."""

import re

_LOCAL = re.compile(r"(?i)\b(?:environment|local|system)\s+date\b")


def matches(reason, has_utc_stamp):
    """True when the reason overrides a UTC stamp with the environment's local date."""
    return has_utc_stamp and bool(_LOCAL.search(reason))


def test_flags_local_date_override():
    assert matches(
        "The message's clock (22:16Z) conflicts with the environment date (2026-10-15)", True
    )


def test_control():
    assert not matches("Fix the failing assertion.", True)
    assert not matches("environment date is shown", False)
