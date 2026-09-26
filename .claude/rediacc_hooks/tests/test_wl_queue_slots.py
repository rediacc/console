"""Queued writer work against free writer slots, and an honest cap estimate (agent/plans/PLAN-stop-hook-retro-20260924.md R.5 and R.6).

R.5. Every `worker:queue` item read as a lease on a finished worker the moment one slot was free: at 15:08:58 on 2026-09-24 a block carried 15 "a slot is free now: start it" lines for 1 free slot, and at 13:34 the lead was forced to fill a slot it was holding for a writer about to be spawned. Queued items now have their own key naming only the K oldest, and ONE `HOLD_FOR:#<id>` reservation may hold a slot.

R.6. The spawn guard counted a writer that had finished (15:08:28, a9130421): its transcript had already received its shell's `<task-id>` notification, yet `shell_waiters` still called it a waiter because the event listed that shell. And the estimate trusted the previous Stop event even after the harness's completion notification reached the lead.

Every fire case has an inverse differing by one planted fact.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import (
    W1,
    W2,
    W3,
    W4,
    backdate,
    mk_sub,
    plant_lease,
    plant_shell_wait,
    subagents_dir,
    verdict,
)
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def three_writers(fix) -> None:
    fix.brief_now()
    fix.hand_now()
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(fix, aid, "general-purpose", 1)
        plant_lease(fix, "cap%d" % i, aid)


def queue(fix, count: int) -> list[str]:
    """`count` queue leases, the first the OLDEST."""
    ids = ["q%02d" % i for i in range(count)]
    for i, ident in enumerate(ids):
        plant_lease(fix, ident, "queue", lease_age_min=40 - i)
    return ids


# ---- R.5 (a): only the K oldest queued items are named ------------------------------------------


def test_r5a_one_free_slot_names_one_queued_item(wl):  # noqa: F811
    """CONTROL: before R.5 the stop carried twelve "start it" lines under roster-dead for one free slot."""
    three_writers(wl)
    ids = queue(wl, 12)
    v = verdict(wl)
    assert v["queue_start"] == [ids[0]], v.get("queue_start")
    assert v["leased_dead"] == [], v["leased_dead"]
    wl.say("working\n\n## Remaining\n- the queue")
    got = wl.run()
    assert "a slot is free now: start it" not in got.out, got.out[:1500]
    assert "1 slot(s) free, 12 queued: start #q00." in got.out, got.out[:1500]
    for later in ids[1:]:
        assert "#%s" % later not in got.out.split("QUEUED WORK", 1)[1][:400], got.out[:1500]


def test_r5a_inverse_a_full_cap_names_no_queued_item(wl):  # noqa: F811
    three_writers(wl)
    mk_sub(wl, W4, "general-purpose", 1)
    plant_lease(wl, "cap3", W4)
    queue(wl, 12)
    v = verdict(wl)
    assert v["queue_start"] == [], v["queue_start"]
    assert v["state"] != "DISHONEST", v


# ---- R.5 (b): one HOLD_FOR reservation ------------------------------------------------------------


def added(fix, text: str) -> str:
    got = fix.cli("--add", wlfix.ME, text)
    found = re.search(r"#([0-9a-f]+)", got.out)
    assert found, got.out[:200] + got.err[:200]
    return found.group(1)


def test_r5b_a_hold_for_an_open_item_holds_the_slot(wl):  # noqa: F811
    """CONTROL: before R.5 a queue lease with a free slot was refused outright, so the slot could not be held."""
    three_writers(wl)
    item = added(wl, "(deadbeef) writer work whose writer is about to be spawned")
    got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "HOLD_FOR:#%s" % item)
    assert got.rc == 0, got.err[:400]
    v = verdict(wl)
    assert v["queue_start"] == [], v["queue_start"]
    assert v["queue_held"] == item, v
    assert v["state"] != "DISHONEST", v


def test_r5b_inverse_a_hold_for_a_closed_item_or_a_second_hold_is_refused(wl):  # noqa: F811
    three_writers(wl)
    closed = added(wl, "(deadbeef) already done")
    assert wl.cli("--tick", wlfix.ME, closed, "landed, exit 0").rc == 0
    item = added(wl, "(deadbeef) writer work")
    got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "HOLD_FOR:#%s" % closed)
    assert got.rc != 0, got.out[:300]
    assert "names no open or in-flight item" in got.err, got.err[:400]
    assert wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "HOLD_FOR:#%s" % item).rc == 0
    second = added(wl, "(deadbeef) more writer work")
    got = wl.cli("--lease", wlfix.ME, second, "+30", "worker:queue", "HOLD_FOR:#%s" % second)
    assert got.rc != 0, got.out[:300]
    assert "a slot is already held" in got.err, got.err[:400]
    # And a plain queue lease with a slot free is still refused: the reservation is the only door.
    got = wl.cli("--lease", wlfix.ME, second, "+30", "worker:queue", "plain")
    assert got.rc != 0, got.out[:300]


# ---- R.6 (c): a shell already reported back does not make a waiter --------------------------------

ESTIMATE_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_roster as R
print(json.dumps([r["id"] for r in R.live_writers_estimate(sys.argv[2], sys.argv[3])]))
"""


def estimate(fix) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-c", ESTIMATE_SNIPPET, str(wlfix.STOP_DIR), str(fix.proj), wlfix.SID],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return json.loads(proc.stdout)


def lastevent(fix):
    return fix.wl.with_suffix(".lastevent-deadbeef.json")


def insert_before_last(fix, aid: str, record: dict) -> None:
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % aid)
    st = tx.stat()
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    tx.write_text("".join(lines[:-1]) + json.dumps(record) + "\n" + lines[-1], encoding="utf-8")
    os.utime(tx, (st.st_atime, st.st_mtime))


def reported_back(fix, aid: str, shell: str) -> None:
    insert_before_last(
        fix,
        aid,
        {
            "type": "user",
            "message": {
                "content": "<task-notification>\n<task-id>%s</task-id>\n<status>completed</status>"
                % shell
            },
        },
    )


def test_r6c_a_shell_the_agent_already_heard_back_from_is_not_a_wait(wl):  # noqa: F811
    """CONTROL: before R.6 the event's still-running shell made the finished agent a waiter, and the estimate counted it."""
    mk_sub(wl, W4, "general-purpose", 5, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell77", running=True)
    reported_back(wl, W4, "bshell77")
    lastevent(wl).write_text(wl.event(), encoding="utf-8")
    assert W4 not in estimate(wl)


def test_r6c_inverse_a_shell_still_armed_is_a_wait(wl):  # noqa: F811
    mk_sub(wl, W4, "general-purpose", 5, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell77", running=True)
    lastevent(wl).write_text(wl.event(), encoding="utf-8")
    assert W4 in estimate(wl)


# ---- R.6 (d): a completion that reached the lead after the last event ---------------------------


def lead_transcript(fix):
    return subagents_dir(fix).parent.with_suffix(".jsonl")


def lead_notified(fix, aid: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    with lead_transcript(fix).open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": stamp,
                    "message": {
                        "content": "<task-notification>\n<task-id>%s</task-id>\n"
                        "<status>completed</status>\n<summary>done</summary>" % aid
                    },
                }
            )
            + "\n"
        )


def completion_world(fix) -> None:
    """W4 is listed running by the last Stop event, written 10 minutes ago, and its transcript's last record is a tool call (not proven finished)."""
    mk_sub(fix, W4, "general-purpose", 20, last="tool_use", running=True)
    lastevent(fix).write_text(fix.event(), encoding="utf-8")
    backdate(lastevent(fix), 10)
    lead_transcript(fix).write_text("", encoding="utf-8")


def test_r6d_a_completion_after_the_event_frees_the_slot(wl):  # noqa: F811
    """CONTROL: before R.6 the estimate trusted the event's running list over the harness's own later completion notice."""
    completion_world(wl)
    lead_notified(wl, W4)
    assert W4 not in estimate(wl)


def test_r6d_inverse_no_completion_keeps_the_slot(wl):  # noqa: F811
    completion_world(wl)
    lead_notified(wl, W1)
    assert W4 in estimate(wl)
