"""A silent capture from an agent that ended its turn to WAIT on its own shell is held, not surfaced (agent/plans/PLAN-stop-hook-retro-20260924.md R.7, hint-proposal b).

Three of the lead's blocks on 2026-09-24 (15:02, 15:14, 15:17) were [SILENT] reports that said only that the agent was waiting on its background task. Since P1.5 these are the only unread-report blocks left. The capture now records the shell the agent is waiting on; `unread` holds the entry while that wait lasts, marks it `superseded` once the same agent is captured again, and returns it if the agent stops waiting with no later capture (it fails closed).

Every case drives `wl_report.py --subagent-stop` and the SessionStart surface, the same entry points the harness calls.
"""

from __future__ import annotations

import json
import os
import time

import pytest
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


# ---- review findings 418a8095.1 to .5 ----


def _write_line(path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def _launch(timeout_ms=None, persistent=False, first=None, tid=MONITOR) -> dict:
    result: dict = dict(first or {})
    result["taskId"] = tid
    if timeout_ms is not None:
        result["timeoutMs"] = timeout_ms
    result["persistent"] = persistent
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "Monitor started"}]},
        "toolUseResult": result,
    }


def _aged(path, minutes: float) -> float:
    now = time.time()
    old = now - minutes * 60
    os.utime(path, (old, old))
    return now


def test_r8_1_a_quiet_monitor_inside_its_own_timeout_stays_armed_past_the_flat_horizon(tmp_path):
    """FIRE: a 3-hour build Monitor emits no events; the flat 120-minute horizon released its waiting agent."""
    tx = tmp_path / "agent.jsonl"
    _write_line(tx, _launch(timeout_ms=3 * 3600 * 1000))
    now = _aged(tx, wl_roster.WAIT_HORIZON_MIN + 30)
    assert wl_report.armed_monitors(tx, now) == [MONITOR]


def test_r8_1_inverse_silence_past_the_monitor_timeout_and_grace_is_a_gone_agent(tmp_path):
    """INVERSE: the Monitor's own timeout notification would have been written by now, so the silence is a dead agent."""
    tx = tmp_path / "agent.jsonl"
    _write_line(tx, _launch(timeout_ms=600000))
    edge = 600 + wl_report.MONITOR_GRACE_SEC
    now = time.time()
    os.utime(tx, (now - edge + 5, now - edge + 5))
    assert wl_report.armed_monitors(tx, now) == [MONITOR]
    os.utime(tx, (now - edge - 5, now - edge - 5))
    assert wl_report.armed_monitors(tx, now) == []


def test_r8_1_a_persistent_monitor_keeps_the_wait_horizon(tmp_path):
    tx = tmp_path / "agent.jsonl"
    _write_line(tx, _launch(timeout_ms=600000, persistent=True))
    assert wl_report.armed_monitors(tx, _aged(tx, wl_roster.WAIT_HORIZON_MIN - 5)) == [MONITOR]
    assert wl_report.armed_monitors(tx, _aged(tx, wl_roster.WAIT_HORIZON_MIN + 5)) == []


def test_r8_2_a_launch_with_another_key_first_is_still_a_launch(tmp_path):
    """FIRE: the old pattern needed `taskId` as the first key of toolUseResult."""
    tx = tmp_path / "agent.jsonl"
    _write_line(tx, _launch(timeout_ms=600000, first={"command": "tail -f x"}))
    raw = tx.read_text(encoding="utf-8")
    assert raw.index('"command"') < raw.index('"taskId"')
    assert wl_report.armed_monitors(tx, time.time()) == [MONITOR]


def test_r8_2_inverse_a_line_that_only_names_task_id_is_not_a_launch(tmp_path):
    tx = tmp_path / "agent.jsonl"
    _write_line(tx, {"type": "user", "message": {"content": 'the "taskId" key of a brief'}})
    _write_line(tx, {"toolUseResult": {"taskId": 7}})
    with tx.open("a", encoding="utf-8") as fh:
        fh.write('{not json "taskId"\n')
    assert wl_report.armed_monitors(tx, time.time()) == []


def test_r8_3_an_api_request_tail_after_the_resume_is_held_until_superseded(sc):
    """The mid-turn reading of an api-request tail is intended: the shell's notification resumed the agent, so the tail is a turn in flight, and its own SubagentStop capture supersedes the entry."""
    path = transcript(sc, flushed=False)
    capture(sc, WAITING, path)
    assert _capture_interim(sc) == SHELL
    _write_line(path, _rec_notice(SHELL))
    _write_line(path, {"type": "api-request", "message": {"content": []}})
    assert WAITING not in surfaced(sc), surfaced(sc)[:600]


def test_r8_3_inverse_the_same_tail_gone_quiet_past_the_fresh_window_is_returned(sc):
    path = transcript(sc, flushed=False)
    capture(sc, WAITING, path)
    _write_line(path, _rec_notice(SHELL))
    _write_line(path, {"type": "api-request", "message": {"content": []}})
    _aged(path, 30)
    assert WAITING in surfaced(sc), "an api-request tail that never flushed stayed hidden"


def _stop_event(sc: Scratch, tx) -> dict:
    return {
        "agent_id": MON_AGENT,
        "agent_type": "general-purpose",
        "session_id": "aaaaaaaa-1111",
        "cwd": sc.env["CLAUDE_PROJECT_DIR"],
        "agent_transcript_path": str(tx),
        "last_assistant_message": MON_WAITING,
    }


def _in_process_in_scratch(sc: Scratch, monkeypatch) -> None:
    """An in-process `handle_subagent_stop` writes to `$WORKLIST_REPORTS_DIR`, and with the scratch env unset it writes to the operator's real report store: a first draft of the r8_4 cases did, and its fixture capture (id 000333344445) blocked the lead's stop as an unread report."""
    for key, value in sc.env.items():
        monkeypatch.setenv(key, value)
    got = os.environ.get("WORKLIST_REPORTS_DIR")
    assert got == str(sc.store), "the scratch report store is not pinned (got %r): the capture would land in the real store" % got


def test_r8_4_a_filesystem_error_from_armed_monitors_costs_only_the_interim(sc, monkeypatch):
    """The capture hook never wedges a stop on an unreadable transcript."""
    tx = monitor_transcript(sc, "waiting", shell=False)
    _in_process_in_scratch(sc, monkeypatch)

    def boom(*_a, **_k):
        raise OSError("unreadable")

    monkeypatch.setattr(wl_report, "armed_monitors", boom)
    wl_report.handle_subagent_stop(_stop_event(sc, tx))
    assert _capture_interim(sc) == ""
    assert sc.index_lines(), "the capture itself was lost"


def test_r8_4_inverse_any_other_error_from_armed_monitors_surfaces(sc, monkeypatch):
    """FIRE: suppress(Exception) hid a bug in the scan as a silent loss of the interim mark."""
    tx = monitor_transcript(sc, "waiting", shell=False)
    _in_process_in_scratch(sc, monkeypatch)

    def bug(*_a, **_k):
        raise RuntimeError("a bug in the scan")

    monkeypatch.setattr(wl_report, "armed_monitors", bug)
    with pytest.raises(RuntimeError):
        wl_report.handle_subagent_stop(_stop_event(sc, tx))


def test_r8_5_the_transcript_is_read_once_per_call(tmp_path, monkeypatch):
    """FIRE: the scan copied the rest of the transcript per launch; one call now reads the file once however many Monitors it launched."""
    tx = tmp_path / "agent.jsonl"
    for i in range(40):
        _write_line(tx, _launch(timeout_ms=600000, tid="bmon%05d" % i))
    _write_line(tx, _rec_notice("bmon00003"))
    reads = []
    real = type(tx).read_bytes

    def counting(self):
        reads.append(self)
        return real(self)

    monkeypatch.setattr(type(tx), "read_bytes", counting)
    got = wl_report.armed_monitors(tx, time.time())
    assert len(reads) == 1
    assert len(got) == 39
    assert "bmon00003" not in got
    assert got[-1] == "bmon00039"
