"""Stuck shell-waiters (agent/plans/PLAN-writers-now-cadence.md WN4, wl_stuckshell).

An agent waiting on a shell is STUCK, not live, once its final report is captured or once the shell has run longer than STUCK_SHELL_MIN; the `stuck-shell` check names the agent, the shell and both moves, and the roster stops counting it. The last case reproduces the 2026-11-23 shape: writer a7f511c739e4aa739 reported a final TICK block and showed "waiting on 1 shell" behind its own narrow-CI shell for hours.

Every fire case has a control differing by one planted fact.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import (
    W4,
    mk_sub,
    plant_lease,
    stamp,
    subagents_dir,
    verdict,
)

STUCK_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_stuckshell as S
ev = json.loads(sys.stdin.read())
problems = []
rows = S.stop_rows(ev, ev["session_id"], problems=problems)
print(json.dumps({"rows": rows, "problems": problems}))
"""

TICK_BODY = (
    "SD1 is committed and its own test passes.\n\n"
    "TICK PLAN-stripe-disable.md#1a2b3c4d done commits=abc1234 landed=all owed=-\n"
    "    close: nothing\n"
)


def plant_launch(fix, aid: str, sid: str, minutes_ago: float, running: bool = True) -> None:
    """The real launch record: a tool result carrying `backgroundTaskId` with the record's `timestamp`, inserted before the transcript's final record (mtime kept), and the shell listed running."""
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % aid)
    st = tx.stat()
    launch = {
        "type": "user",
        "timestamp": stamp(minutes_ago).replace("Z", ".000Z"),
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "content": "Command running in background with ID: %s." % sid,
                }
            ]
        },
        "toolUseResult": {"backgroundTaskId": sid, "stdout": "", "stderr": ""},
    }
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    tx.write_text(
        "".join(lines[:-1]) + json.dumps(launch, separators=(",", ":")) + "\n" + lines[-1],
        encoding="utf-8",
    )
    os.utime(tx, (st.st_atime, st.st_mtime))
    if running:
        rows = json.loads(fix.bg)
        rows.append({"id": sid, "type": "shell", "status": "running", "description": "narrow ci"})
        fix.bg = json.dumps(rows)


def plant_notified(fix, aid: str, sid: str) -> None:
    """A task notification for `sid` reaching the agent's transcript before its final record: a shell it no longer waits on."""
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % aid)
    st = tx.stat()
    note = {"type": "attachment", "content": "<task-notification><task-id>%s</task-id>" % sid}
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    tx.write_text(
        "".join(lines[:-1]) + json.dumps(note, separators=(",", ":")) + "\n" + lines[-1],
        encoding="utf-8",
    )
    os.utime(tx, (st.st_atime, st.st_mtime))


def plant_report(fix, aid: str, minutes_ago: float, body: str) -> dict:
    """Capture `body` as `aid`'s report through `wl_report.capture`, the same writer the SubagentStop hook uses, stamped `minutes_ago`."""
    code = r"""
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import wl_report as RPT
e = RPT.capture(pathlib.Path(sys.argv[2]), "1121-1", agent_id=sys.argv[3], agent_type="general-purpose",
    agent_name="general-purpose", session="fixture0", body=sys.argv[5], transcript="", at=sys.argv[4])
print(json.dumps(e))
"""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(wlfix.STOP_DIR),
            fix.env["WORKLIST_REPORTS_DIR"],
            aid,
            stamp(minutes_ago),
            body,
        ],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout)


def stuck(fix) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", STUCK_SNIPPET, str(wlfix.STOP_DIR)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    got = json.loads(proc.stdout)
    assert got["problems"] == [], got["problems"]
    return dict(got["rows"])


def waiter(fix, aid: str = W4, shell: str = "bshell01", age_min: float = 10) -> None:
    """A leased writer that ended its turn `age_min` ago, its shell launched at the same time and still running."""
    mk_sub(fix, aid, "general-purpose", age_min, last="end_turn", running=False)
    plant_launch(fix, aid, shell, age_min)
    plant_lease(fix, "wait1", aid)


# ---- (a) a captured final report makes the waiter stuck ----------------------------------------


def test_a_report_captured_waiter_is_stuck_and_not_live(wl):
    waiter(wl)
    rep = plant_report(wl, W4, 5, TICK_BODY)
    assert rep["boxes"], rep
    rows = stuck(wl)
    assert rows[W4]["reason"] == "report", rows
    assert rows[W4]["shell"] == "bshell01", rows
    assert rows[W4]["report"] == rep["id"], rows
    v = verdict(wl)
    assert W4 not in v["writers"], v["writers"]
    assert [d[0] for d in v["leased_dead"]] == ["wait1"], v["leased_dead"]


def test_a_control_a_report_from_before_the_launch_keeps_it_live(wl):
    """The same report captured before the shell launched belongs to an earlier turn."""
    waiter(wl)
    plant_report(wl, W4, 15, TICK_BODY)
    assert stuck(wl) == {}
    v = verdict(wl)
    assert W4 in v["writers"], v["writers"]
    assert v["leased_dead"] == [], v["leased_dead"]


def test_a_control_a_short_turn_end_line_is_not_a_closing_summary(wl):
    """A status line under RELAY_FLOOR naming no box ("waiting on the narrow run") is not a final report."""
    waiter(wl)
    plant_report(
        wl, W4, 5, "Waiting on the narrow CI run in shell bshell01; the report follows. " * 3
    )
    assert stuck(wl) == {}


def test_a_a_long_closing_summary_with_no_tick_is_final(wl):
    waiter(wl)
    plant_report(wl, W4, 5, "All four fixes landed with their tests green. " * 20)
    assert stuck(wl)[W4]["reason"] == "report"


# ---- (b) a shell past the bound makes the waiter stuck -------------------------------------------


def test_b_a_46_minute_waiter_is_stuck(wl):
    waiter(wl, age_min=46)
    rows = stuck(wl)
    assert rows[W4]["reason"] == "runtime", rows
    assert rows[W4]["age_min"] > 45, rows
    v = verdict(wl)
    assert W4 not in v["writers"], v["writers"]


# ---- (c) control: a fresh waiter with no report stays live ---------------------------------------


def test_c_a_10_minute_waiter_with_no_report_is_live(wl):
    waiter(wl, age_min=10)
    assert stuck(wl) == {}
    v = verdict(wl)
    assert W4 in v["writers"], v["writers"]
    assert v["leased_dead"] == [], v["leased_dead"]


def test_c_control_a_44_minute_waiter_is_still_live(wl):
    waiter(wl, age_min=44)
    assert stuck(wl) == {}


# ---- the 2026-11-23 shape, through the whole Stop hook --------------------------------------------

A7 = "a7f511c739e4aa739"


def test_fixture_a7f511_reported_tick_block_behind_its_own_shell_fires(wl):
    """Writer a7f511c739e4aa739 (stripe-disable): shell bigs9j96f launched and notified back, then its narrow-CI shell bgjvtrdck launched, then a final TICK block; the event still lists bgjvtrdck running and calls the agent finished."""
    mk_sub(wl, A7, "general-purpose", 20, last="end_turn", running=False)
    plant_launch(wl, A7, "bigs9j96f", 24, running=False)
    plant_notified(wl, A7, "bigs9j96f")
    plant_launch(wl, A7, "bgjvtrdck", 21)
    plant_lease(wl, "sd1", A7)
    plant_report(wl, A7, 20, TICK_BODY)
    rows = stuck(wl)
    assert list(rows) == [A7], rows
    assert rows[A7]["shell"] == "bgjvtrdck", rows
    wl.say("working\n\n## Remaining\n- the stripe-disable report")
    got = wl.run()
    assert "STUCK SHELL-WAITER: 1 agent(s)" in got.out, got.out[:3000]
    assert "agent %s waiting on shell bgjvtrdck" % A7 in got.out, got.out[:3000]
    assert "TaskStop bgjvtrdck" in got.out, got.out[:3000]
    assert "SendMessage to %s" % A7 in got.out, got.out[:3000]


def test_fixture_control_the_same_writer_without_its_report_stays_quiet(wl):
    mk_sub(wl, A7, "general-purpose", 20, last="end_turn", running=False)
    plant_launch(wl, A7, "bigs9j96f", 24, running=False)
    plant_notified(wl, A7, "bigs9j96f")
    plant_launch(wl, A7, "bgjvtrdck", 21)
    plant_lease(wl, "sd1", A7)
    assert stuck(wl) == {}
    wl.say("working\n\n## Remaining\n- the stripe-disable report")
    got = wl.run()
    assert "STUCK SHELL-WAITER" not in got.out, got.out[:3000]


# ---- a long report written while the agent still waits on its own shell is not final -------------

ARMED_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_report as RPT
import wl_stuckshell as S
n = RPT.RELAY_FLOOR + 400
print(json.dumps([
    S.is_final({"bytes": n, "armed": "bdy2q4ke7"}),
    S.is_final({"bytes": n}),
    S.is_final({"bytes": n, "armed": "bdy2q4ke7", "boxes": ["PLAN-x.md#abcd1234"]}),
]))
"""


def test_a_long_report_with_an_armed_shell_is_not_final() -> None:
    """2026-11-23: the hostinger runner wrote a long "waiting on restart-services" message while its shell ran; it is not finished.

    Controls: the same size with nothing armed at capture is a closing summary, and a TICK block still wins.
    """
    proc = subprocess.run(
        [sys.executable, "-c", ARMED_SNIPPET, str(wlfix.STOP_DIR)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(proc.stdout) == [False, True, True]


NEWEST_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_report as RPT
import wl_stuckshell as S
n = RPT.RELAY_FLOOR + 400
aid = "ae1f51c5c5b30755f"
rid = RPT.short_id(aid)
old_final = {"id": rid + "-2", "at": "2026-11-23T20:20:00Z", "bytes": n}
new_interim = {"id": rid + "-4", "at": "2026-11-23T20:40:00Z", "bytes": n, "armed": "bdy2q4ke7"}
since = 0
print(json.dumps([
    S.final_report([old_final, new_interim], aid, since) is None,
    S.final_report([old_final], aid, since) is not None,
    S.final_report([new_interim, dict(old_final, at="2026-11-23T20:50:00Z")], aid, since) is not None,
]))
"""


def test_the_newest_report_decides_not_an_older_final_looking_one() -> None:
    """An older closing-looking row is superseded by a newer interim one; controls: alone it is final, and a newer final row wins."""
    proc = subprocess.run(
        [sys.executable, "-c", NEWEST_SNIPPET, str(wlfix.STOP_DIR)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(proc.stdout) == [True, True, True]
