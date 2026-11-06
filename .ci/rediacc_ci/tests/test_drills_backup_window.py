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
    "RUNNING-BEGIN\nRUNNING-END\n"
)


def with_running(*rows: str) -> str:
    return TABLE.replace("RUNNING-BEGIN\n", "RUNNING-BEGIN\n" + "".join(r + "\n" for r in rows))


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
    # A zero run budget leaves only the 5 minute lead.
    assert bw.window_verdict(TABLE, at(1, 54, 59), run_s=0)[0]
    assert not bw.window_verdict(TABLE, at(1, 55), run_s=0)[0]
    assert not bw.window_verdict(TABLE, at(2, 45))[0]
    assert bw.window_verdict(TABLE, at(2, 45, 1))[0]


def test_the_run_budget_widens_the_lead() -> None:
    assert bw.RUN_BUDGET_S == 30 * 60
    assert not bw.window_verdict(TABLE, at(1, 50))[0]
    assert not bw.window_verdict(TABLE, at(1, 25))[0]
    assert bw.window_verdict(TABLE, at(1, 24, 59))[0]
    assert bw.window_verdict(TABLE, at(1, 50), run_s=0)[0]


def test_a_running_adhoc_service_refuses_with_no_timer_near() -> None:
    text = with_running("rediacc-backup-adhoc.service loaded active running Backup adhoc")
    clear, why = bw.window_verdict(text, at(9, 0))
    assert not clear
    assert "rediacc-backup-adhoc.service" in why


def test_a_seed_process_refuses() -> None:
    text = with_running("4242 renet backup snapshot --repo demo")
    assert not bw.window_verdict(text, at(9, 0))[0]
    assert bw.window_verdict(TABLE, at(9, 0))[0]


def test_running_check_can_be_skipped_for_the_callers_own_snapshot() -> None:
    text = with_running("4242 renet backup snapshot --repo demo")
    assert bw.window_verdict(text, at(9, 0), run_s=0, check_running=False)[0]


def test_missing_markers_refuse() -> None:
    assert not bw.window_verdict(TABLE.replace("RUNNING-END\n", ""), at(9, 0))[0]


def test_the_script_has_the_markers_and_the_service_listing() -> None:
    script = bw.timers_script()
    assert script.index("RUNNING-BEGIN") < script.index("list-units") < script.index("RUNNING-END")
    assert "--state=activating,active,deactivating" in script
    assert "systemctl is-active" not in script


def test_zero_timers_refuse_when_a_timer_is_required() -> None:
    bare = "NEXT LEFT\nNOW=%d\nRUNNING-BEGIN\nRUNNING-END\n" % at(9, 0)
    assert bw.window_verdict(bare, require_timer=False)[0]
    assert not bw.window_verdict(bare, require_timer=True)[0]


def test_machine_verdict_refuses_a_failed_read() -> None:
    assert not bw.machine_verdict(lambda _c: (255, ""))[0]
    assert not bw.machine_verdict(lambda _c: (0, TABLE + "NOW=%d\n" % at(1, 58)))[0]


def test_the_last_trigger_counts_too() -> None:
    # NEXT already moved a day on; LAST is 02:00 today and the run is still inside its tail.
    table = TABLE.replace("Fri 2026-11-06 02:00:00 UTC 2h ", "Sat 2026-11-07 02:00:00 UTC 2h ")
    table = table.replace("Thu 2026-11-05", "Fri 2026-11-06")
    assert not bw.window_verdict(table, at(2, 30))[0]
    assert bw.window_verdict(table, at(3, 0), run_s=0)[0]


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
    other += "RUNNING-BEGIN\nRUNNING-END\n"
    assert bw.window_verdict(other, at(2, 0))[0]


def test_a_failed_unit_listing_is_not_reported_as_a_running_backup() -> None:
    clear, why = bw.window_verdict(with_running("LIST-UNITS-FAILED"), at(9, 0))
    assert not clear
    assert "a backup is running" not in why
    assert "unit listing failed" in why


def test_the_next_clear_time_is_outside_every_window_not_only_the_first() -> None:
    # A 02:50 timer beside the 02:00 one: its window opens at 02:15, so clearing the 02:00 tail at 02:45:01 lands inside it.
    table = TABLE.replace(
        "n/a                         n/a   n/a                         n/a     rediacc-backup-weekly.timer",
        "Fri 2026-11-06 02:50:00 UTC 2h    n/a                         n/a     rediacc-backup-weekly.timer",
    )
    clear, why = bw.window_verdict(table, at(1, 58))
    assert not clear
    assert "next clear time 2026-11-06 03:35:01Z" in why
    assert bw.window_verdict(table, at(3, 35, 1))[0]


def test_an_impossible_date_in_a_stamp_refuses_without_raising() -> None:
    table = TABLE.replace("2026-11-06 02:00:00 UTC 2h ", "2026-13-06 02:00:00 UTC 2h ", 1)
    clear, why = bw.window_verdict(table, at(9, 0))
    assert not clear
    assert "unchecked" in why
