"""The one clock the date-sensitive gates read, so a test can move it past a deadline.

A gate whose verdict flips on a calendar date (a waiver expiry, a baseline age limit, a plan retention window) is green today and red on a day nobody chose, and until that day nothing shows it can go red at all. `REDIACC_GATE_CLOCK` makes the day a parameter: set it to an ISO 8601 date or timestamp and `now()` answers that instant instead of the wall clock. The five clock gates read `now()` for every DEADLINE decision (plan-housekeeping, plan-folders, runner-advice, secret-reachability, and the pin-freshness hold expiry, whose TypeScript twin is `gateNowMs` in scripts/gates/check-pin-freshness.ts).

WRITES KEEP THE WALL CLOCK. A `refreshed_at` or `moved_at` stamp records when the work happened; stamping it with a planted clock would put a lie in a tracked file, so only the reads that decide a verdict come through here.

A BAD VALUE IS A FAILURE, never a fallback to the wall clock: a typo that silently reads today would turn a planted-clock test into a green that ran nothing. The seam is also not a skip. Every gate's pytest plants a clock past its deadline and requires RED, so a gate that ignores the seam fails its own test (tests/test_core_gate_clock.py).

When the variable is set, `now()` says so once on stderr, so a verdict produced under a moved clock is never mistaken for today's.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

ENV = "REDIACC_GATE_CLOCK"

_announced: set[str] = set()


class GateClockError(ValueError):
    """`REDIACC_GATE_CLOCK` is set to something that is not an ISO 8601 date or timestamp."""


def parse(raw: str) -> dt.datetime:
    """The UTC instant `raw` names. A bare date is midnight UTC; a naive timestamp is read as UTC."""
    text = raw.strip()
    try:
        moment = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise GateClockError(
            f"{ENV}={raw!r} is not an ISO 8601 date or timestamp (for example 2027-01-01 or "
            f"2027-01-01T00:00:00Z). The gate refuses to guess, because falling back to today "
            f"would make a planted clock pass without running."
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC)


def override() -> dt.datetime | None:
    """The planted instant, or None when the variable is unset or empty."""
    raw = os.environ.get(ENV, "")
    if not raw.strip():
        return None
    moment = parse(raw)
    if raw not in _announced:
        _announced.add(raw)
        print(
            f"  NOTE: {ENV}={raw} moves this gate's clock; this verdict is not today's.",
            file=sys.stderr,
        )
    return moment


def now() -> dt.datetime:
    """The instant a deadline is judged against: the planted clock, else the wall clock (UTC)."""
    return override() or dt.datetime.now(dt.UTC)


def today() -> dt.date:
    """`now()`'s calendar date."""
    return now().date()
