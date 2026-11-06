"""The backup-window guard: timer table parse plus the clock gives a verdict (finding #5ec68285)."""

from __future__ import annotations

import datetime as dt

from rediacc_ci.drills import backup_window as bw

TABLE = (
    "NEXT                        LEFT  LAST                        PASSED  UNIT                             ACTIVATES\n"
    "Fri 2026-11-06 02:00:00 UTC 2h    Thu 2026-11-05 02:00:00 UTC 22h ago rediacc-backup-nightly-hot.timer rediacc-backup-nightly-hot.service\n"
    "Fri 2026-11-06 12:00:00 UTC 12h   n/a                         n/a     apt-daily.timer                  apt-daily.service\n"
    "n/a                         n/a   n/a                         n/a     rediacc-backup-weekly.timer      rediacc-backup-weekly.service\n"
    "\n3 timers listed.\n"
)


def at(h: int, m: int, s: int = 0, day: int = 6) -> int:
    return int(dt.datetime(2026, 11, day, h, m, s, tzinfo=dt.UTC).timestamp())


def test_parse_keeps_only_backup_timers_and_skips_na() -> None:
    rows = bw.parse_timers(TABLE)
    assert [r.unit for r in rows] == [
        "rediacc-backup-nightly-hot.timer",
        "rediacc-backup-weekly.timer",
    ]
    assert rows[0].triggers == [at(2, 0), at(2, 0, day=5)]
    assert rows[1].triggers == []


def test_two_minutes_before_the_trigger_refuses_and_names_the_next_window() -> None:
    clear, why = bw.window_verdict(TABLE, at(1, 58))
    assert not clear
    assert "rediacc-backup-nightly-hot.timer at 2026-11-06 02:00:00Z" in why
    assert "next clear time 2026-11-06 02:45:01Z" in why


def test_window_edges() -> None:
    assert bw.window_verdict(TABLE, at(1, 54, 59))[0]
    assert not bw.window_verdict(TABLE, at(1, 55))[0]
    assert not bw.window_verdict(TABLE, at(2, 45))[0]
    assert bw.window_verdict(TABLE, at(2, 45, 1))[0]


def test_the_last_trigger_counts_too() -> None:
    # NEXT already moved a day on; LAST is 02:00 today and the run is still inside its tail.
    table = TABLE.replace("Fri 2026-11-06 02:00:00 UTC 2h ", "Sat 2026-11-07 02:00:00 UTC 2h ")
    table = table.replace("Thu 2026-11-05", "Fri 2026-11-06")
    assert not bw.window_verdict(table, at(2, 30))[0]
    assert bw.window_verdict(table, at(3, 0))[0]


def test_now_comes_from_the_machine_read() -> None:
    assert bw.parse_now(TABLE + "NOW=%d\n" % at(1, 58)) == at(1, 58)
    assert not bw.window_verdict(TABLE + "NOW=%d\n" % at(1, 58))[0]
    assert bw.window_verdict(TABLE + "NOW=%d\n" % at(9, 0))[0]


def test_unchecked_reads_refuse() -> None:
    assert not bw.window_verdict("", at(9, 0))[0]
    assert not bw.window_verdict(TABLE)[0]  # no NOW= line
    local = TABLE.replace("UTC 2h ", "CET 2h ", 1)
    assert not bw.window_verdict(local, at(9, 0))[0]


def test_no_backup_timer_on_a_read_table_is_clear() -> None:
    other = TABLE.splitlines()[0] + "\nFri 2026-11-06 12:00:00 UTC 12h n/a n/a apt-daily.timer a\n"
    assert bw.window_verdict(other, at(2, 0))[0]
