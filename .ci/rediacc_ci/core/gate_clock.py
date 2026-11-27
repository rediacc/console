"""The one clock the date-sensitive gates read, so a test can move it past a deadline.

A gate whose verdict flips on a calendar date (a waiver expiry, a baseline age limit, a plan retention window) is green today and red on a day nobody chose, and until that day nothing shows it can go red at all. `REDIACC_GATE_CLOCK` makes the day a parameter: set it to an ISO 8601 date or timestamp and `now()` answers that instant instead of the wall clock. The five clock gates read `now()` for every DEADLINE decision (plan-housekeeping, plan-folders, runner-advice, secret-reachability, and the pin-freshness hold expiry, whose TypeScript twin is `gateNowMs` in scripts/gates/check-pin-freshness.ts).

WRITES KEEP THE WALL CLOCK. A `refreshed_at` or `moved_at` stamp records when the work happened; stamping it with a planted clock would put a lie in a tracked file, so only the reads that decide a verdict come through here.

A BAD VALUE IS A FAILURE, never a fallback to the wall clock: a typo that silently reads today would turn a planted-clock test into a green that ran nothing. The seam is also not a skip. Every gate's pytest plants a clock past its deadline and requires RED, so a gate that ignores the seam fails its own test (tests/test_core_gate_clock.py).

When the variable is set, `now()` says so once on stderr, so a verdict produced under a moved clock is never mistaken for today's.

A PLANTED CLOCK CANNOT TURN A REAL RUN GREEN (review finding 914b173e.3). A date set before a waiver's expiry would excuse an expired waiver with only a stderr NOTE, so the seam is honoured ONLY when `REDIACC_GATE_CLOCK_TEST=1` marks the process as a test harness (a pytest case, a `--selftest`), and NEVER when `CI=true`. Anywhere else a set `REDIACC_GATE_CLOCK` is a REFUSAL, a `GateClockError` naming the variable (rc non-zero), not an ignored value: a stray export in a shell must be loud, not a quiet return to the wall clock that a reader would take for a planted-clock verdict. The marker is a second explicit variable on purpose; one leaked export cannot move a verdict.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

ENV = "REDIACC_GATE_CLOCK"
TEST_ENV = "REDIACC_GATE_CLOCK_TEST"

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


def _refusal(env: dict[str, str] | os._Environ[str]) -> str | None:
    """Why a set clock must not be honoured here, or None when the process is a marked test harness outside CI."""
    if env.get("CI", "").strip().lower() == "true":
        return f"{ENV} is set under CI=true, where no gate may run on a planted clock"
    if env.get(TEST_ENV, "").strip() != "1":
        return (
            f"{ENV} is set outside a test harness ({TEST_ENV}=1 is not set), so a real gate run "
            f"would be judged on a date nobody chose"
        )
    return None


def override() -> dt.datetime | None:
    """The planted instant, or None when the variable is unset or empty. Refuses (GateClockError) outside a test harness."""
    raw = os.environ.get(ENV, "")
    if not raw.strip():
        return None
    why = _refusal(os.environ)
    if why is not None:
        raise GateClockError(
            f"{why}. Unset {ENV}; only a gate's --selftest or pytest may plant it."
        )
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
