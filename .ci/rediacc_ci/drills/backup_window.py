"""The backup-window guard of the mutating live steps on a production machine (finding #5ec68285).

The machine's backup timers (`rediacc-backup-*.timer`, the nightly one fires at 02:00:00 UTC) stage the production repositories; a fork, up or `delete --force` made while one runs races its staging (hostinger, 2026-11-06 at 01:58Z: a probe fork of `observability` was deleted under the 02:00 nightly, which failed on it). A mutating live step therefore reads the timers first and refuses to start when the machine's clock is within `LEAD_S` before a trigger or `TAIL_S` after it. The trigger is the timer's NEXT and its LAST.

`timers_script` is the one read (root-free, `systemctl list-timers` under `TZ=UTC` plus the machine's own clock); `parse_timers`, `parse_now` and `window_verdict` are pure and pinned by `tests/test_drills_backup_window.py`. An unreadable or unparseable read refuses too, since an unchecked window is not a clear one.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import NamedTuple

LEAD_S = 5 * 60
TAIL_S = 45 * 60
UNIT_PREFIX = "rediacc-backup-"

_STAMP = re.compile(r"\w{3} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)")
_UNIT = re.compile(r"(rediacc-backup-\S*\.timer)")


class Timer(NamedTuple):
    unit: str
    triggers: list[int]
    utc: bool


def timers_script() -> str:
    """The shell to run on the machine: the timer table in UTC, then the machine's clock as an epoch (`NOW=`)."""
    return "TZ=UTC systemctl list-timers --all --no-pager; echo NOW=$(date -u +%s)"


def parse_now(text: str) -> int | None:
    m = re.search(r"^NOW=(\d+)\s*$", text, re.MULTILINE)
    return int(m.group(1)) if m else None


def _epoch(stamp: str, zone: str) -> int | None:
    if zone not in ("UTC", "GMT"):
        return None
    when = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC)
    return int(when.timestamp())


def parse_timers(text: str) -> list[Timer]:
    """One row per `rediacc-backup-*.timer` line: its unit, the epochs of its NEXT and LAST (`n/a` is skipped) and whether every stamp was in UTC."""
    rows: list[Timer] = []
    for line in text.splitlines():
        unit = _UNIT.search(line)
        if not unit:
            continue
        triggers: list[int] = []
        utc = True
        for stamp in _STAMP.finditer(line[: unit.start()]):
            epoch = _epoch(stamp.group(1), stamp.group(2))
            if epoch is None:
                utc = False
            else:
                triggers.append(epoch)
        rows.append(Timer(unit.group(1), triggers, utc))
    return rows


def _utc(epoch: int) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def window_verdict(text: str, now: int | None = None) -> tuple[bool, str]:
    """(clear, why) from a `timers_script` read. `now` defaults to the read's own `NOW=` line. Refuses inside [trigger - LEAD_S, trigger + TAIL_S] of any backup timer and names the next clear time."""
    if now is None:
        now = parse_now(text)
    if now is None:
        return False, "backup-window: the machine's clock was not read, so the window is unchecked"
    if "NEXT" not in text:
        return False, "backup-window: the timer table was not read, so the window is unchecked"
    rows = parse_timers(text)
    if any(not r.utc for r in rows):
        return (
            False,
            "backup-window: a backup timer stamp is not in UTC, so the window is unchecked",
        )
    holds = [
        (trig + TAIL_S, "%s at %s" % (r.unit, _utc(trig)))
        for r in rows
        for trig in r.triggers
        if trig - LEAD_S <= now <= trig + TAIL_S
    ]
    if not holds:
        return True, "backup-window: clear at %s (%d backup timer(s))" % (_utc(now), len(rows))
    clear_at = max(h[0] for h in holds)
    return False, (
        "backup-window: refused at %s, within %d min before to %d min after %s; next clear time %s"
        % (
            _utc(now),
            LEAD_S // 60,
            TAIL_S // 60,
            "; ".join(h[1] for h in holds),
            _utc(clear_at + 1),
        )
    )
