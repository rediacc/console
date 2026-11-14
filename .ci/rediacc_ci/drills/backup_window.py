"""The backup-window guard of the mutating live steps on a production machine (finding #5ec68285).

The machine's backup timers (`rediacc-backup-*.timer`, the nightly one fires at 02:00:00 UTC) stage the production repositories; a fork, up or `delete --force` made while one runs races its staging (hostinger, 2026-11-06 at 01:58Z: a probe fork of `observability` was deleted under the 02:00 nightly, which failed on it). A mutating live step therefore reads the timers first and refuses to start when the machine's clock is within `LEAD_S` before a trigger or `TAIL_S` after it. The trigger is the timer's NEXT and its LAST.

`timers_script` is the one read (root-free, `systemctl list-timers` under `TZ=UTC` plus the machine's own clock); `parse_timers`, `parse_now` and `window_verdict` are pure and pinned by `tests/test_drills_backup_window.py`. An unreadable or unparseable read refuses too, since an unchecked window is not a clear one.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

LEAD_S = 5 * 60
TAIL_S = 45 * 60
# What the caller's own run may take: a start is refused when a trigger falls inside [now, now + RUN_BUDGET_S + LEAD_S], and, past a trigger, until TAIL_S after it.
RUN_BUDGET_S = 30 * 60
UNIT_PREFIX = "rediacc-backup-"
RUNNING_BEGIN = "RUNNING-BEGIN"
RUNNING_END = "RUNNING-END"
LIST_FAILED = "LIST-UNITS-FAILED"

_STAMP = re.compile(r"\w{3} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+)")
_UNIT = re.compile(r"(%s\S*\.timer)" % re.escape(UNIT_PREFIX))


class Timer(NamedTuple):
    unit: str
    triggers: list[int]
    utc: bool


def timers_script() -> str:
    """The shell to run on the machine: the timer table in UTC, then the machine's clock as an epoch (`NOW=`)."""
    return (
        "TZ=UTC systemctl list-timers --all --no-pager; echo NOW=$(date -u +%s); "
        "echo " + RUNNING_BEGIN + "; "
        "systemctl list-units --all --no-legend --plain '" + UNIT_PREFIX + "*.service' "
        "--state=activating,active,deactivating || echo '" + LIST_FAILED + "'; "
        "pgrep -af '[r]enet backup (snapshot|verify|push)' || true; "
        "echo " + RUNNING_END
    )


def parse_running(text: str) -> list[str] | None:
    """The rows between the markers (a backup service in an active state, a renet backup process), or None when a marker is missing."""
    lines = text.splitlines()
    try:
        begin = lines.index(RUNNING_BEGIN)
        end = lines.index(RUNNING_END, begin)
    except ValueError:
        return None
    return [ln.strip() for ln in lines[begin + 1 : end] if ln.strip()]


def parse_now(text: str) -> int | None:
    m = re.search(r"^NOW=(\d+)\s*$", text, re.MULTILINE)
    return int(m.group(1)) if m else None


def _epoch(stamp: str, zone: str) -> int | None:
    if zone not in ("UTC", "GMT"):
        return None
    try:
        when = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.UTC)
    except ValueError:
        return None
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


def window_verdict(
    text: str,
    now: int | None = None,
    run_s: int = RUN_BUDGET_S,
    *,
    require_timer: bool = False,
    check_running: bool = True,
) -> tuple[bool, str]:
    """(clear, why) from a `timers_script` read. `now` defaults to the read's own `NOW=` line. Refuses when a backup is running now (`check_running`), and inside [trigger - LEAD_S - run_s, trigger + TAIL_S] of any backup timer, naming the next clear time. `run_s` is the time the caller's own run needs; 0 re-checks a moment before one destructive step. `require_timer` refuses a machine that lists no backup timer at all."""
    if now is None:
        now = parse_now(text)
    if now is None:
        return False, "backup-window: the machine's clock was not read, so the window is unchecked"
    if "NEXT" not in text:
        return False, "backup-window: the timer table was not read, so the window is unchecked"
    if check_running:
        running = parse_running(text)
        if running is None:
            return (
                False,
                "backup-window: the running-backup read has no markers, so it is unchecked",
            )
        if LIST_FAILED in running:
            return (
                False,
                "backup-window: the backup unit listing failed, so a running backup is unchecked",
            )
        if running:
            return False, "backup-window: refused, a backup is running: %s" % "; ".join(running)
    rows = parse_timers(text)
    if any(not r.utc for r in rows):
        return (
            False,
            "backup-window: a backup timer stamp is not a readable UTC time, so the window is unchecked",
        )
    if require_timer and not rows:
        return (
            False,
            "backup-window: no %s*.timer is listed, so the window is unchecked" % UNIT_PREFIX,
        )
    windows = [
        (trig - LEAD_S - run_s, trig + TAIL_S, "%s at %s" % (r.unit, _utc(trig)))
        for r in rows
        for trig in r.triggers
    ]
    holds = [(end, why) for start, end, why in windows if start <= now <= end]
    if not holds:
        return True, "backup-window: clear at %s (%d backup timer(s))" % (_utc(now), len(rows))
    # The first moment no window holds: the end of the latest window holding `now`, and past it the end of any window that opens before then.
    clear_at = max(h[0] for h in holds)
    while True:
        later = [end for start, end, _ in windows if start <= clear_at + 1 <= end]
        if not later:
            break
        clear_at = max(later)
    return False, (
        "backup-window: refused at %s, within %d min before (run budget %d min) to %d min after %s; next clear time %s"
        % (
            _utc(now),
            LEAD_S // 60,
            run_s // 60,
            TAIL_S // 60,
            "; ".join(h[1] for h in holds),
            _utc(clear_at + 1),
        )
    )


def machine_verdict(
    run: Callable[[str], tuple[int, str]],
    run_s: int = RUN_BUDGET_S,
    *,
    require_timer: bool = True,
    check_running: bool = True,
) -> tuple[bool, str]:
    """Read the machine through `run(command) -> (rc, stdout)` and judge it. A failed read refuses."""
    rc, out = run(timers_script())
    if rc != 0:
        return (
            False,
            "backup-window: the timer read failed (rc=%d), so the window is unchecked" % rc,
        )
    return window_verdict(
        out, run_s=run_s, require_timer=require_timer, check_running=check_running
    )
