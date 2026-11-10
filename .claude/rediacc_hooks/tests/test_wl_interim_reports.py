"""A silent capture from an agent that ended its turn to WAIT on its own shell is held, not surfaced (agent/plans/PLAN-stop-hook-retro-20260924.md R.7, hint-proposal b).

Three of the lead's blocks on 2026-09-24 (15:02, 15:14, 15:17) were [SILENT] reports that said only that the agent was waiting on its background task. Since P1.5 these are the only unread-report blocks left. The capture now records the shell the agent is waiting on; `unread` holds the entry while that wait lasts, marks it `superseded` once the same agent is captured again, and returns it if the agent stops waiting with no later capture (it fails closed).

Every case drives `wl_report.py --subagent-stop` and the SessionStart surface, the same entry points the harness calls.
"""

from __future__ import annotations

import json
import os
import time

import wl_report
import wl_roster

from rediacc_hooks.tests.test_wl_report_inbox import BIG, Scratch

AGENT = "awaiter-000011112222"
WAITING = "I'll wait for this notification now."  # style-ok -- the agent's own words, quoted
SHELL = "bwait0001"


def transcript(sc: Scratch, notified: bool = False, flushed: bool = True):
    """The agent's transcript: a launched background shell, then an idle final record. `notified` appends the shell's `<task-id>` notification and a second idle record, the shape of an agent the harness resumed and that finished."""
    path = sc.subagents_dir() / ("agent-%s.jsonl" % AGENT)
    records = [
        {"type": "user", "message": {"content": "brief"}},
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "running in background"}]},
            "toolUseResult": {"backgroundTaskId": SHELL},
        },
        {
            "type": "assistant",
            "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": WAITING}]},
        },
    ]
    if not flushed:
        # The tail the harness had not flushed at SubagentStop: the last record is an api-request, not the end_turn.
        records[-1] = {"type": "api-request", "message": {"content": []}}
    if notified:
        records.append(
            {
                "type": "user",
                "message": {
                    "content": "<task-notification>\n<task-id>%s</task-id>\n<status>completed</status>"
                    % SHELL
                },
            }
        )
        records.append(
            {
                "type": "assistant",
                "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]},
            }
        )
    path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records), encoding="utf-8"
    )
    return path


def capture(sc: Scratch, body: str, tx) -> None:
    got = sc.raw_stop(
        {
            "agent_id": AGENT,
            "agent_type": "general-purpose",
            "session_id": "aaaaaaaa-1111",
            "cwd": sc.env["CLAUDE_PROJECT_DIR"],
            "agent_transcript_path": str(tx),
            "last_assistant_message": body,
        },
        env=sc.env,
    )
    assert got.rc == 0, got.err[:300]


def surfaced(sc: Scratch) -> str:
    return sc.surface("--session-start", "startup")


def test_r7_an_interim_wait_is_held_while_the_agent_waits(sc):
    """CONTROL: before R.7 the wait surfaced as an unread [SILENT] report."""
    capture(sc, WAITING, transcript(sc))
    assert WAITING not in surfaced(sc), surfaced(sc)[:600]


def test_r7_inverse_the_agent_stops_waiting_with_no_later_capture_and_it_returns(sc):
    capture(sc, WAITING, transcript(sc))
    transcript(sc, notified=True)
    assert WAITING in surfaced(sc), "a finished agent's interim entry stayed hidden"


def test_r7_inverse_a_later_capture_supersedes_it(sc):
    capture(sc, WAITING, transcript(sc))
    tx = transcript(sc, notified=True)
    capture(sc, "FINAL REPORT\n" + BIG, tx)
    out = surfaced(sc)
    assert "FINAL REPORT" in out, out[:600]
    assert WAITING not in out, out[:600]
    reads = (sc.store / "read.jsonl").read_text(encoding="utf-8")
    assert '"via":"superseded"' in reads.replace(" ", ""), reads[:600]


def test_r7_adversarial_a_substantive_report_is_never_held(sc):
    capture(sc, "SUBSTANCE WHILE WAITING\n" + BIG, transcript(sc))
    assert "SUBSTANCE WHILE WAITING" in surfaced(sc)


def _capture_interim(sc: Scratch) -> str:
    return "".join(json.loads(ln).get("interim", "") for ln in sc.index_lines() if ln.strip())


def test_r6_an_unflushed_tail_with_an_armed_shell_is_written_interim(sc):
    """CONTROL: the idle test read an api-request tail as working, so `interim` stayed empty and the capture blocked."""
    capture(sc, WAITING, transcript(sc, flushed=False))
    assert _capture_interim(sc) == SHELL


def test_r6_inverse_the_notification_present_writes_no_interim(sc):
    capture(sc, WAITING, transcript(sc, notified=True, flushed=False))
    assert _capture_interim(sc) == ""


def _roster_module():
    return wl_roster


def test_transcript_waiting_names_the_shell_for_a_fresh_idle_transcript(sc):
    """CONTROL: a fresh idle transcript with an armed shell is waiting on it."""

    path = transcript(sc)
    assert _roster_module().transcript_waiting(path, time.time()) == SHELL


def test_transcript_waiting_is_empty_for_a_missing_or_stale_transcript(sc):
    """last_record runs before the mtime horizon check, and a missing path reads as no record, so neither shape raises."""

    roster = _roster_module()
    path = transcript(sc)
    future = time.time() + (roster.WAIT_HORIZON_MIN + 1) * 60
    assert roster.transcript_waiting(path, future) == ""
    assert roster.transcript_waiting(path.with_name("agent-gone.jsonl"), time.time()) == ""


# ---- recount residue #819c9be9 (agent/plans/PLAN-stop-hook-retro-20261110.md R.8) ----
# The 2026-11-10 16:37Z shape: the agent backgrounded a build shell, armed a Monitor on it, ended its turn saying it was waiting, then a Monitor event resumed it and it sat in a Bash call. R.7 asked only "idle with a shell armed", so the in-flight tool_use read as finished and the silent capture blocked.

MON_AGENT = "amonitor0000333344445"
MON_WAITING = "The build is still running, and I'm waiting for the monitor to report that it finished."  # style-ok -- the agent's own words, quoted
MONITOR = "bmon00001"


def _rec_tool_use(name: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": "toolu_x", "name": name, "input": {}}],
        },
    }


def _rec_end(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]},
    }


def _rec_notice(tid: str, status: str = "completed") -> dict:
    return {
        "type": "user",
        "message": {
            "content": "<task-notification>\n<task-id>%s</task-id>\n<status>%s</status>\n</task-notification>"
            % (tid, status)
        },
    }


def monitor_transcript(sc: Scratch, stage: str, shell: bool = True):
    """`waiting`: shell and Monitor armed, turn ended. `resumed`: the Monitor ended and the agent is mid-Bash with the shell still armed. `working`: every child ended and the agent is mid-Bash. `finished`: every child ended and the agent ended its turn."""
    path = sc.subagents_dir() / ("agent-%s.jsonl" % MON_AGENT)
    records: list[dict] = [{"type": "user", "message": {"content": "brief"}}]
    if shell:
        records.append(
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "moved to background"}]},
                "toolUseResult": {"backgroundTaskId": SHELL},
            }
        )
    records += [
        _rec_tool_use("Monitor"),
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "Monitor started"}]},
            "toolUseResult": {"taskId": MONITOR, "timeoutMs": 600000, "persistent": False},
        },
        _rec_end(MON_WAITING),
    ]
    if stage in ("resumed", "working", "finished"):
        records.append(_rec_notice(MONITOR))
        if stage != "resumed" and shell:
            records.append(_rec_notice(SHELL))
        records.append(_rec_tool_use("Bash"))
    if stage == "finished":
        records.append(
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}
        )
        records.append(_rec_end("done"))
    path.write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records), encoding="utf-8"
    )
    return path


def _mon_capture(sc: Scratch, tx) -> None:
    got = sc.raw_stop(
        {
            "agent_id": MON_AGENT,
            "agent_type": "general-purpose",
            "session_id": "aaaaaaaa-1111",
            "cwd": sc.env["CLAUDE_PROJECT_DIR"],
            "agent_transcript_path": str(tx),
            "last_assistant_message": MON_WAITING,
        },
        env=sc.env,
    )
    assert got.rc == 0, got.err[:300]


def test_r8_silent_a_resumed_agent_mid_tool_with_its_shell_armed_is_held(sc):
    """SILENT: the 16:37Z shape. Before R.8 the in-flight Bash read as finished and the capture surfaced."""
    _mon_capture(sc, monitor_transcript(sc, "waiting"))
    monitor_transcript(sc, "resumed")
    assert MON_WAITING not in surfaced(sc), surfaced(sc)[:600]


def test_r8_silent_a_fresh_mid_turn_agent_with_no_child_left_is_held(sc):
    """SILENT: every child ended and the agent is still working toward its next capture."""
    _mon_capture(sc, monitor_transcript(sc, "waiting"))
    monitor_transcript(sc, "working")
    assert MON_WAITING not in surfaced(sc), surfaced(sc)[:600]


def test_r8_fire_a_finished_silent_agent_still_blocks(sc):
    """FIRE: an idle last record with nothing armed is a finished agent that said nothing; its capture surfaces."""
    _mon_capture(sc, monitor_transcript(sc, "waiting"))
    monitor_transcript(sc, "finished")
    assert MON_WAITING in surfaced(sc), "a finished agent's silent capture stayed hidden"


def test_r8_fire_a_stale_mid_turn_transcript_is_not_believed(sc):
    """FIRE: a mid-turn transcript quiet past the horizon is a dead agent, not a working one."""
    _mon_capture(sc, monitor_transcript(sc, "waiting"))
    tx = monitor_transcript(sc, "working")
    old = time.time() - (wl_roster.WAIT_HORIZON_MIN + 5) * 60
    os.utime(tx, (old, old))
    assert MON_WAITING in surfaced(sc), "a dead mid-turn agent's capture stayed hidden"


def test_r8_control_a_monitor_only_wait_is_written_interim(sc):
    """CONTROL: a Monitor launch carries `taskId`, not `backgroundTaskId`; before R.8 a Monitor-only wait wrote no `interim` and blocked."""
    _mon_capture(sc, monitor_transcript(sc, "waiting", shell=False))
    assert _capture_interim(sc) == MONITOR
    assert MON_WAITING not in surfaced(sc), surfaced(sc)[:600]


def test_r8_control_a_non_terminal_monitor_event_keeps_it_armed(sc):
    """CONTROL: a per-event notice is not the stream's end, and a terminal one is."""
    tx = monitor_transcript(sc, "waiting", shell=False)
    with tx.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec_notice(MONITOR, "running"), separators=(",", ":")) + "\n")
    assert wl_report.armed_monitors(tx, time.time()) == [MONITOR]
    with tx.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec_notice(MONITOR), separators=(",", ":")) + "\n")
    assert wl_report.armed_monitors(tx, time.time()) == []
