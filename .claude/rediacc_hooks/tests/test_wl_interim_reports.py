"""A silent capture from an agent that ended its turn to WAIT on its own shell is held, not surfaced (agent/plans/PLAN-stop-hook-retro-20260924.md R.7, hint-proposal b).

Three of the lead's blocks on 2026-09-24 (15:02, 15:14, 15:17) were [SILENT] reports that said only that the agent was waiting on its background task. Since P1.5 these are the only unread-report blocks left. The capture now records the shell the agent is waiting on; `unread` holds the entry while that wait lasts, marks it `superseded` once the same agent is captured again, and returns it if the agent stops waiting with no later capture (it fails closed).

Every case drives `wl_report.py --subagent-stop` and the SessionStart surface, the same entry points the harness calls.
"""

from __future__ import annotations

import json

from rediacc_hooks.tests.test_wl_report_inbox import BIG, Scratch, sc  # noqa: F401

AGENT = "awaiter-000011112222"
WAITING = "I'll wait for this notification now."  # style-ok -- the agent's own words, quoted
SHELL = "bwait0001"


def transcript(sc: Scratch, notified: bool = False):  # noqa: F811
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


def capture(sc: Scratch, body: str, tx) -> None:  # noqa: F811
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


def surfaced(sc: Scratch) -> str:  # noqa: F811
    return sc.surface("--session-start", "startup")


def test_r7_an_interim_wait_is_held_while_the_agent_waits(sc):  # noqa: F811
    """CONTROL: before R.7 the wait surfaced as an unread [SILENT] report."""
    capture(sc, WAITING, transcript(sc))
    assert WAITING not in surfaced(sc), surfaced(sc)[:600]


def test_r7_inverse_the_agent_stops_waiting_with_no_later_capture_and_it_returns(sc):  # noqa: F811
    capture(sc, WAITING, transcript(sc))
    transcript(sc, notified=True)
    assert WAITING in surfaced(sc), "a finished agent's interim entry stayed hidden"


def test_r7_inverse_a_later_capture_supersedes_it(sc):  # noqa: F811
    capture(sc, WAITING, transcript(sc))
    tx = transcript(sc, notified=True)
    capture(sc, "FINAL REPORT\n" + BIG, tx)
    out = surfaced(sc)
    assert "FINAL REPORT" in out, out[:600]
    assert WAITING not in out, out[:600]
    reads = (sc.store / "read.jsonl").read_text(encoding="utf-8")
    assert '"via":"superseded"' in reads.replace(" ", ""), reads[:600]


def test_r7_adversarial_a_substantive_report_is_never_held(sc):  # noqa: F811
    capture(sc, "SUBSTANCE WHILE WAITING\n" + BIG, transcript(sc))
    assert "SUBSTANCE WHILE WAITING" in surfaced(sc)
