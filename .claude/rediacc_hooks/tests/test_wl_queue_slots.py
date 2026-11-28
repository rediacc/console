"""Queued writer work, and an honest live-writer estimate (agent/plans/PLAN-stop-hook-retro-20260924.md R.5 and R.6).

R.5. Every `worker:queue` item read as a lease on a finished worker: at 15:08:58 on 2026-09-24 a block carried 15 "a slot is free now: start it" lines under roster-dead. Queued items have their own key, `queue-slot`. With no writer limit (agent/plans/PLAN-unlimited-writers.md) the key names every queued item no live plan holds, however many writers run, and the one-slot `HOLD_FOR:#<id>` reservation went with the slots.

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
    W5,
    backdate,
    mk_sub,
    pad,
    plant_lease,
    plant_shell_wait,
    subagents_dir,
    verdict,
)


def three_writers(fix) -> None:
    """Three of W1..W4 plus the `pad` crowd: thirty-three live writers, past the old cap of 25."""
    fix.brief_now()
    fix.hand_now()
    pad(fix)
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(fix, aid, "general-purpose", 1)
        plant_lease(fix, "live%d" % i, aid)


def queue(fix, count: int) -> list[str]:
    """`count` queue leases, the first the OLDEST."""
    ids = ["q%02d" % i for i in range(count)]
    for i, ident in enumerate(ids):
        plant_lease(fix, ident, "queue", lease_age_min=40 - i)
    return ids


# ---- R.5 (a): every queued item no plan holds is named, whatever the crowd --------------------------


def test_r5a_every_queued_item_nothing_holds_is_named_under_its_own_key(wl):
    """CONTROL: before R.5 the stop carried "start it" lines under roster-dead, and before agent/plans/PLAN-unlimited-writers.md a full cap named none."""
    three_writers(wl)
    ids = queue(wl, 12)
    v = verdict(wl)
    assert v["queue_start"] == ids, v.get("queue_start")
    assert v["leased_dead"] == [], v["leased_dead"]
    wl.say("working\n\n## Remaining\n- the queue")
    got = wl.run()
    assert "a slot is free now: start it" not in got.out, got.out[:1500]
    assert "QUEUED WORK NOTHING HOLDS: 12 of 12 queued item(s)" in got.out, got.out[:1500]
    assert "start #q00, #q01," in got.out, got.out[:1500]


def test_r5a_inverse_one_more_writer_still_names_the_whole_queue(wl):
    """The old full-cap case, one planted writer added: the count of live writers no longer hides a queued item."""
    three_writers(wl)
    mk_sub(wl, W4, "general-purpose", 1)
    plant_lease(wl, "live3", W4)
    mk_sub(wl, W5, "general-purpose", 1)
    plant_lease(wl, "live4", W5)
    ids = queue(wl, 12)
    v = verdict(wl)
    assert len(v["writers"]) == 35, v["writers"]
    assert v["queue_start"] == ids, v["queue_start"]
    assert v["state"] == "DISHONEST", v["state"]


# ---- R.5 (b): a queue lease is only for work a live plan holds ------------------------------------


def added(fix, text: str) -> str:
    got = fix.cli("--add", wlfix.ME, text)
    found = re.search(r"#([0-9a-f]+)", got.out)
    assert found, got.out[:200] + got.err[:200]
    return found.group(1)


def test_r5b_a_hold_for_note_reserves_nothing_and_an_unheld_item_is_refused(wl):
    """The `HOLD_FOR:#<id>` reservation held one free slot; with no slots it is gone, so such a note admits nothing. CONTROL: the plain lease is refused the same way, naming why."""
    three_writers(wl)
    item = added(wl, "(deadbeef) writer work whose writer is about to be spawned")
    for note in ("HOLD_FOR:#%s" % item, "plain"):
        got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", note)
        assert got.rc != 0, (note, got.out[:300])
        assert "#%s stays OPEN (not leased)" % item in got.err, got.err[:400]
        assert "no live plan holds it" in got.err, got.err[:400]
    v = verdict(wl)
    assert "queue_held" not in v, sorted(v)


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


def test_r6c_a_shell_the_agent_already_heard_back_from_is_not_a_wait(wl):
    """CONTROL: before R.6 the event's still-running shell made the finished agent a waiter, and the estimate counted it."""
    mk_sub(wl, W4, "general-purpose", 5, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell77", running=True)
    reported_back(wl, W4, "bshell77")
    lastevent(wl).write_text(wl.event(), encoding="utf-8")
    assert W4 not in estimate(wl)


def test_r6c_inverse_a_shell_still_armed_is_a_wait(wl):
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


def test_r6d_a_completion_after_the_event_frees_the_slot(wl):
    """CONTROL: before R.6 the estimate trusted the event's running list over the harness's own later completion notice."""
    completion_world(wl)
    lead_notified(wl, W4)
    assert W4 not in estimate(wl)


def test_r6d_inverse_no_completion_keeps_the_slot(wl):
    completion_world(wl)
    lead_notified(wl, W1)
    assert W4 in estimate(wl)


# ---- #2a252641: an interrupted or long-dead transcript frees its slot ------------------------------


def dead_world(fix, last_record: dict, silent_min: float) -> None:
    """W4 is listed running by a last Stop event older than the agent, and its transcript ends in `last_record`, untouched for `silent_min` minutes."""
    mk_sub(fix, W4, "general-purpose", silent_min + 1, last="text", running=True)
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % W4)
    with tx.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(last_record) + "\n")
    backdate(tx, silent_min)
    lastevent(fix).write_text(fix.event(), encoding="utf-8")
    backdate(lastevent(fix), silent_min + 5)
    lead_transcript(fix).write_text("", encoding="utf-8")


INTERRUPT = {
    "type": "user",
    "message": {"content": [{"type": "text", "text": "[Request interrupted by user]"}]},
}
ANSWERED_TOOL = {
    "type": "user",
    "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]},
}
TOOL_IN_FLIGHT = {
    "type": "assistant",
    "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
}


def test_2a252641_an_interrupted_transcript_frees_the_slot(wl):
    """CONTROL: a workflow agent cut by the harness ends in the interrupt marker, and before the fix it counted as a live writer until the next Stop event."""
    dead_world(wl, INTERRUPT, 1)
    assert W4 not in estimate(wl)


def test_2a252641_inverse_an_answered_tool_a_minute_ago_is_live(wl):
    dead_world(wl, ANSWERED_TOOL, 1)
    assert W4 in estimate(wl)


def test_2a252641_a_transcript_silent_past_the_horizon_frees_the_slot(wl):
    """CONTROL: nine agents killed mid-turn held nine slots for nine hours."""
    dead_world(wl, ANSWERED_TOOL, 180)
    assert W4 not in estimate(wl)


def test_2a252641_inverse_a_tool_in_flight_past_the_horizon_stays_live(wl):
    dead_world(wl, TOOL_IN_FLIGHT, 180)
    assert W4 in estimate(wl)
