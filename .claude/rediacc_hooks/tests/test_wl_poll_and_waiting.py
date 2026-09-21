"""The 5-minute poll shape, waiting-cross-session verification, the silent fast path and its forfeits, and the message catalogue.

Ported from `.claude/hooks/stop/worklist-cases/08-poll-and-waiting.sh`, one pytest function per numbered bash case, with the same assertions in the same order against the same subprocess.

THE POLL FAST PATH IS THE HEADLINE (case 111) AND ITS FORFEITS ARE THE REST. A no-op poll stop is silent, zero bytes and exit 0, and every case after it plants exactly one fact that must buy that silence back: a delivered request, tracked work the session quietly started, a baseline past its horizon, an expired lease. Each forfeit is paired with the control that shows the same
fixture going silent without the planted fact, because a silence nobody has seen broken proves nothing.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

FLAG_ITEM = "- [?] (deadbeef) keep the flag? DEFAULT: keep it"
FLAG_SAID = "answer\n\n## Remaining\n- the flag decision, deferred with a default"
POLL_CRON = {"id": "p", "schedule": "*/5 * * * *"}
WORK_CRON = {"id": "w", "schedule": "17 * * * *"}


def stamp(minutes_ago: float, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    """A UTC stamp `minutes_ago` in the past, the pytest shape of `date -u -d`."""
    moment = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes_ago)
    return moment.strftime(fmt)


def run_script(script, argv: list[str], env: dict, stdin: str = "") -> wlfix.Result:
    """One invocation of a COPY of the hook, for the missing-catalogue case.

    `wlfix.Fixture.python` always drives the shipped `worklist.py`; case 118 has to drive a copy that was deliberately separated from its own `wl_*` modules, so the path is a parameter here rather than a knob on the shared fixture.
    """
    proc = subprocess.run(
        [sys.executable, str(script), *argv],
        input=stdin,
        capture_output=True,
        text=True,
        env=dict(env),
        check=False,
    )
    return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)


def test_101_a_loop_with_no_five_minute_poll_blocks(wl):  # noqa: F811
    """v9: the enforced shape is one work loop plus the 5-minute inbox poll."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = json.dumps([WORK_CRON])
    wl.check(
        "block",
        "NOTHING LISTENING FOR CROSS-SESSION MAIL",
        "a work cron without the poll cron blocks",
    )


def test_102_two_poll_crons_block(wl):  # noqa: F811
    """One poll cron is the shape, so a second is redundancy rather than resilience."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = json.dumps(
        [
            WORK_CRON,
            {"id": "p1", "schedule": "*/5 * * * *"},
            {"id": "p2", "schedule": "*/5 * * * *"},
        ]
    )
    wl.check("block", "poll crons", "a redundant poll cron blocks")


def test_103_the_work_loop_dying_behind_a_surviving_poll_still_fires(wl):  # noqa: F811
    """The reason cron_memory is work-scoped in v9: a total-count high-water mark reads "1 cron live" and misses that the one driving work is gone."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = json.dumps([WORK_CRON, POLL_CRON])
    wl.run()
    wl.crons = json.dumps([POLL_CRON])
    wl.check("block", "WORK LOOP DIED", "work loop gone, poll surviving, still fires")


def test_104_control_poll_only_from_the_start_never_trips_loop_death(wl):  # noqa: F811
    """CONTROL: a session that never had a work cron is not nagged about losing one."""
    wl.brief_now()
    wl.say("all done")
    wl.crons = json.dumps([POLL_CRON])
    wl.check("allow", "", "a session that never had a work cron is not nagged")


def test_105_waiting_cross_session_with_a_verified_open_ask_passes(wl):  # noqa: F811
    """v9. Same two-class-2-sections shape as case 67: the brief and the open request both queue, and one is released per stop by default."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    rid = wl.askid("deadbeef", "cafe1234", "who owns caption regen? DEFAULT: the asker takes it")
    wl.task(7, "pending", "caption regen")
    wl.say(
        "answer\n\n## Remaining\n| #7 | caption regen | waiting-cross-session #%s |" % rid,
    )
    wl.check("allow", "still OPEN", "a verified open request IS the citation")


def test_106_a_verified_wait_exempts_the_task_from_i6_under_a_poll_only_cron(wl):  # noqa: F811
    """The pair for case 92's poll-only block: same crons, but the wait is real and verified, and the poll is exactly what delivers the answer. A fresh fixture, so cron_memory never saw a work cron here."""
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    rid = wl.askid("deadbeef", "cafe1234", "who owns caption regen? DEFAULT: the asker takes it")
    wl.task(7, "pending", "caption regen")
    wl.say("answer\n\n## Remaining\n| #7 | caption regen | waiting-cross-session #%s |" % rid)
    wl.crons = json.dumps([POLL_CRON])
    wl.check("allow", "", "verified waiting-cross-session plus poll cron is a legitimate idle")


def test_107_fire_waiting_cross_session_with_no_request_id_blocks(wl):  # noqa: F811
    """The state without a request id is a synonym for blocked."""
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "caption regen")
    wl.say(
        "answer\n\n## Remaining\n"
        "| #7 | caption regen | waiting-cross-session on the media session |"
    )
    wl.check("block", "names no request id", "the state without a request id is refused")


def test_108_fire_someone_elses_request_does_not_make_it_this_sessions_wait(wl):  # noqa: F811
    """BOTH peers brief, and the second one is not decoration: since v19 --ask refuses a recipient that has never briefed here, and this fixture's whole premise is that beef9999 is a REAL other session. Without it the ask is refused, the id is empty, and the case degrades into testing an empty citation."""
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    wl.brief_other("beef9999")
    rid = wl.askid_as("cafe1234", "cafe1234", "beef9999", "between two other sessions")
    assert rid, "the fixture ask was refused, so the citation below would be empty"
    wl.task(7, "pending", "thing")
    wl.say("answer\n\n## Remaining\n| #7 | thing | waiting-cross-session #%s |" % rid)
    wl.check("block", "not by you", "citing a request this session did not ask blocks")


def test_109_fire_an_answered_request_is_a_stale_wait(wl):  # noqa: F811
    """FOCUS=off: the ANSWERS delivery check also fires here (the asker has an unacked answer), and rotation would rightly surface it first."""
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("cafe1234")
    rid = wl.askid("deadbeef", "cafe1234", "please confirm the regen path")
    wl.cli_as(
        "cafe1234",
        "--answer",
        "cafe1234",
        rid,
        "confirmed: regen goes via the media session",
    )
    wl.task(7, "pending", "thing")
    wl.say("answer\n\n## Remaining\n| #7 | thing | waiting-cross-session #%s |" % rid)
    wl.env["WORKLIST_FOCUS"] = "off"
    wl.check("block", "already ANSWERED", "an answered id means the wait is over")


def test_110_fire_an_escalated_request_is_the_operators_now(wl):  # noqa: F811
    """The first stop escalates the aged ask into an operator `[?]`; the second must then refuse it as a justification for waiting."""
    wl.brief_now()
    wl.hand_now()
    with wl.stem(".requests").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "ask",
                    "id": "feedc0de",
                    "from": "deadbeef",
                    "to": "beef9999",
                    "at": stamp(120),
                    "body": "republish the caption media",
                }
            )
            + "\n"
        )
    wl.say("answer\n\n## Remaining\n- the republish ask, escalated to the operator as a [?]")
    wl.run()
    wl.task(7, "pending", "thing")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n| #7 | thing | waiting-cross-session #feedc0de |")
    wl.check("block", "already ESCALATED", "an escalated id can no longer justify waiting")


def test_111_the_headline_a_no_op_poll_stop_is_silent(wl):  # noqa: F811
    """Zero output, exit 0, and the marker consumed: one poll vouches for exactly one stop.

    The CONTROL is the last assertion and it is the one that makes the silence mean anything: the SAME world, with no fresh marker, is not silent.
    """
    wl.brief_now()
    wl.hand_now()
    wl.add_item(FLAG_ITEM)
    wl.say(FLAG_SAID)
    wl.check("allow", "operator may answer", "the full stop allows and reports")
    assert wl.stem(".pollbase-deadbeef").is_file(), "no pollbase file after an allowed stop"

    poll = wl.cli("--poll", "deadbeef")
    why = "--poll on an empty inbox must print NOTHING and exit 0: rc=%d out=%r err=%r" % (
        poll.rc,
        poll.out[:120],
        poll.err[:120],
    )
    assert poll.rc == 0, why
    assert not poll.out.strip(), why
    assert not poll.err, why

    got = wl.run()
    why = "the poll stop is not silent: rc=%d out=%r" % (got.rc, got.out[:160])
    assert got.rc == 0, why
    assert not got.out.strip(), why
    assert not wl.stem(".pollmark-deadbeef").exists(), "the poll marker survived the stop"

    again = wl.run()
    why = "CONTROL: an ordinary stop went silent without a poll marker: %r" % again.out[:120]
    assert again.out.strip(), why
    assert "operator may answer" in again.out, why


def test_112_the_poll_delivers_and_a_waiting_request_forfeits_the_silence(wl):  # noqa: F811
    """A delivery is a wake-up, so the stop that follows it blocks with the payload rather than sleeping through it."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item(FLAG_ITEM)
    wl.say(FLAG_SAID)
    wl.check("allow", "", "baseline stop")
    rid = wl.askid_as("cafe1234", "cafe1234", "deadbeef", "please rebuild the docs index")
    poll = wl.cli("--poll", "deadbeef")
    assert poll.rc == 0, "--poll rc=%d out=%r" % (poll.rc, poll.out[:160])
    assert "INBOX #%s" % rid in poll.out, "--poll did not print the pending id: %r" % poll.out[:160]
    assert "please rebuild the docs index" in poll.out, (
        "--poll did not print the full pending payload: %r" % poll.out[:160]
    )
    wl.check("block", "waiting on you", "the stop after a delivery blocks, never silently")


def test_113_abuse_control_tracked_work_forfeits_the_fast_path(wl):  # noqa: F811
    """ABUSE CONTROL: a changed world signature pays the full battery despite the poll, so quietly starting work cannot buy the silence."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item(FLAG_ITEM)
    wl.say(FLAG_SAID)
    wl.check("allow", "", "baseline stop")
    wl.task(9, "pending", "the new thing quietly started")
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    why = "work slipped through the poll fast path: %r" % got.out[:160]
    assert got.out.strip(), why
    assert "OUT OF SYNC" in got.out, why


def test_114_the_fast_path_expires_and_an_old_baseline_pays_the_battery_again(wl):  # noqa: F811
    """Past the horizon a poll stop runs the full battery and re-arms, so the silence is bounded rather than permanent."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item(FLAG_ITEM)
    wl.say(FLAG_SAID)
    wl.check("allow", "", "baseline stop")
    old = time.time() - 80 * 60
    os.utime(wl.stem(".pollbase-deadbeef"), (old, old))
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    why = "the horizon did not expire the fast path: %r" % got.out[:120]
    assert got.out.strip(), why
    assert "operator may answer" in got.out, why
    wl.cli("--poll", "deadbeef")
    again = wl.run()
    why = "the baseline did not re-arm: rc=%d out=%r" % (again.rc, again.out[:120])
    assert again.rc == 0, why
    assert not again.out.strip(), why


def test_115_an_expiring_lease_forfeits_the_silence(wl):  # noqa: F811
    """The poll notices in five minutes, so an expired lease is a wake-up the poll stop must not sleep through."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item(FLAG_ITEM)
    wl.say(FLAG_SAID)
    wl.check("allow", "", "baseline stop")
    wl.add_item("- [>] (deadbeef) until:%s delegated thing" % stamp(5, "%Y-%m-%dT%H:%MZ"))
    wl.cli("--poll", "deadbeef")
    wl.check("block", "lease expired", "an expired lease wakes the poll stop")


def test_116_poll_misuse_is_refused_loudly(wl):  # noqa: F811
    """A short prefix half-works, so it is refused with the reason: its marker does not match."""
    got = wl.cli("--poll", "dead")
    assert got.rc != 0, "a 4-char prefix was accepted (its marker does not match)"
    assert "8-char" in got.err, "the refusal was silent: %r" % got.err[:120]


# The arity of every catalogue constant at its call site in `worklist.py`. Seven strings have no needle anywhere in this suite (V_DIVERGED, V_PR_UNREADABLE, V_EVENT_UNPARSEABLE, R_JUDGE_CONTINUE, CLI_REQUEST_USAGE, CTX_SESSION_START_STALE, the exempt-overrun stuck detail), and this registry is their shape protection: every constant must exist and render with the EXACT argument
# arity its call site uses, so a placeholder added or dropped in the catalogue cannot lurk in a branch no test drives. `None` means the constant is printed verbatim and the `%` check is skipped; it still has to be REGISTERED, which is what the gap check at the end of the test is for.
ARITY = {
    "V_STUCK": ("H", 3, "D"),
    "V_EVENT_UNPARSEABLE": ("f",),
    "V_OPEN_ITEMS": (1, "x"),
    "V_UNDEFAULTED": (1, "x"),
    "V_REQUESTS_WAITING": (1, "r", "m", "m"),
    "V_ANSWERS_UNACKED": ("r", "m"),
    "V_COMPLETION_EVIDENCE": ("a", "b"),
    "V_COMPLETION_TICKS": ("x",),
    "V_COMPLETION_TASKS": ("x",),
    "V_IDLE": ("#1",),
    "V_XSESSION_BAD": ("r", "m"),
    "V_BRIEF": ("s", "", "m"),
    "V_STALE_LOCAL": ("r", 2),
    "V_DIVERGED": ("r", 2, "r"),
    "V_PR_STALE": ("d",),
    "V_PR_UNREADABLE": ("d",),
    "V_LOOP_DIED": (1,),
    "V_CI_RED": ("9", 1, "q", "rows", 2, 1, "m"),
    "V_CI_UNREADABLE": ("d",),
    # (task-id, the offending command blob): see wl_ci.adhoc_watch.
    "V_ADHOC_WATCH": ("b1", "blob"),
    "CI_NOTE_RETRYABLE": ("9", 1, "pats", "rows"),
    "CI_NOTE_DOWNGRADED": ("9", 1, 2, "", "rows"),
    # v24 review-red gate (wl_ci.review_red). V_REVIEW_RED takes the PR number, head sha, the check-run's title and summary, then owner/name/pr FOUR times (inline-query, inline-reply, top-level-reply and workflow re-dispatch commands each need their own repo slug), then the block ceiling, the current count, the session prefix, and the PR number again for the --defer exit.
    # REVIEW_NOTE_DOWNGRADED takes the PR, the title, the count, then owner/name/pr for its own re-dispatch command.
    "V_REVIEW_RED": (
        "9",
        "sha",
        "t",
        "s",
        "o",
        "n",
        9,
        "o",
        "n",
        9,
        "o",
        "n",
        9,
        "o",
        "n",
        9,
        2,
        1,
        "me",
        "9",
    ),
    "REVIEW_NOTE_DOWNGRADED": ("9", "t", 1, "o", "n", "9"),
    "V_REVIEW_UNREADABLE": ("d",),
    "V_NO_POLL_CRON": ("m", "m"),
    "V_NO_WAITER": (2, "p", "m"),
    "N_WAITER_NUDGE": (2, "p", "m", 60),
    "V_MANY_WORK_CRONS": (2, "l"),
    # (n waiters, the TaskStop rows, the wl_wait path, the session prefix, the fresh timeout)
    "N_WAITER_DRAINED": (1, "rows", "p", "m", 60),
    "V_MANY_POLL_CRONS": (2,),
    "V_AGENT_STATE": ("me", "s", "", 250, 4000, "m"),
    "V_AGENT_BOOTSTRAP": ("me", "me"),
    "V_AGENT_STILL_ABSENT": ("me",),
    "CLI_STATE_REFUSED": ("v", "d", 250, 4000),
    "N_AGENT_PEERS": ("rows",),
    "CLI_STATE_WHOLE_DOC": ("m",),
    # One substitution: the offending first step, quoted back so the refusal names what it saw rather than restating the rule in the abstract.
    "CLI_STATE_WAIT_LED": ("lead",),
    "V_SOLO_GRIND": (39, 12),
    "N_UNREAD_REPORTS": (2, "b", "rows", "p", "p", "m"),
    "CLI_REAP_USAGE": (),
    "CLI_REAP_UNKNOWN": ("t", "l"),
    "N_ROSTER_STALE": (20, 1, 19, "p", "m"),
    "CLI_LOOP_USAGE": (),
    "CLI_BRIEF_USAGE": (),
    "CLI_UNKNOWN_VERB": ("v",),
    "CLI_BRIEF_LOOKS_LIKE_ID": ("v",),
    "V_JUDGE_ORDER_REJECTED": ("v", "v"),
    "V_LADDER_INVESTIGATE_GONE": ("rows", "facts", "m", "m"),
    "CLI_STATE_NO_DIR": ("me", "me"),
    "CLI_STATE_USAGE": (),
    "CLI_STATE_NO_BODY": ("x", "p"),
    "V_DOCS_DRIFT": (3, "s", "d"),
    "V_UNCONFIRMED": ("#1",),
    "V_BROKEN_SCHEDULE": (2, "rows"),
    "GUIDE_HEADER": None,
    "GUIDE_EMPTY": None,
    "GUIDE_TRUNCATED": (3, 12),
    "V_DEFER_EXPIRED": (2, 120, "rows", "", "m"),
    "V_UNJUSTIFIED": (2, 30, "rows", "", "m", "m"),
    "V_CI_WAITING": ("w", 2, "rows"),
    "V_DEFER_AUDIT": (1, "rows", "m"),
    "N_DEFER_AUDIT_OK": (1, "rows"),
    "R_AUDIT_MALFORMED": ("p", "f"),
    "CLI_DEFER_NO_JUSTIFICATION": None,
    "CLI_DEFER_VAGUE_WHY": ("w",),
    "DEFER_AUDIT_PROMPT": {"n": 1, "window": 120, "items": "i"},
    "V_LADDER_INVESTIGATE": ("rows", "facts", "m"),
    "V_LADDER_RESOLVE": ("rows", "facts", "m"),
    "N_LADDER_PING": ("rows", "m"),
    "N_JUDGE_STAMP": ("m", "approved"),
    "N_JUDGE_STAMP_FULL": ("m", "approved", "why"),
    "N_OUTQ_MORE": (3,),
    "N_OUTQ_BLOCKED": (3, 3),
    "N_AGENT_HINT": ("a", "a", "t, t"),
    "N_AGENT_CORPUS_ERR": ("rows",),
    # (claims, agent, matched terms): the give-up push-back.
    "V_AGENT_PUSHBACK": ("does-not-reproduce", "ops-vms", "ceph, ops, vms"),
    "N_POLL_BACKOFF": (25, 5, "*/5 * * * *", "*/10 * * * *", 10),
    "N_POLL_BACKOFF_RESET": ("*/10 * * * *", "*/5 * * * *"),
    "N_QUIET_WAKE": (3, 5, "*/5 * * * *", "*/10 * * * *", 10),
    "N_QUIET_WAKE_CAPPED": (7, 60),
    "CLI_ITEM_USAGE": None,
    "CLI_TICK_NO_EVIDENCE": ("id",),
    # v16: the triage verb, the tick door gate and the plan-file convention.
    "CLI_TICK_ISSUE_DOOR": ("id",),
    "CLI_TRIAGE_INLINE": {"id": "i", "me": "m", "reason": "r"},
    "CLI_TRIAGE_PLAN": {"id": "i", "me": "m", "reason": "r", "plan": "p", "finding": "f"},
    "CLI_TRIAGE_OPERATOR": {"id": "i", "me": "m", "reason": "r"},
    "CLI_TRIAGE_SELF": {"id": "i", "me": "m", "why": "", "context": "c", "branch": "b"},
    "TRIAGE_PROMPT": {"finding": "f", "context": "c"},
    # v20: the /handoff checklist gate (wl_checklist, agent/programs/<slug>/CHECKLIST.md).
    "V_CL_SHAPE": ("d", "rows"),
    "V_CL_UNREADABLE": ("e",),
    "V_CL_PRODUCING": ("s", 0, 1, "rows", "d"),
    "V_CL_PRODUCING_DONE": ("s", "d"),
    "V_CL_FLIP": ("d", "executing", "rows", "d"),
    "V_CL_WAVES": ("s", "d", "rows"),
    "N_CL_FOREIGN": ("s", "o", ""),
    "N_CL_FOREIGN_DRIFT": ("d", "executing", "o", "rows"),
    "N_CL_FOREIGN_WAVES": ("slug", "d", "o", "rows", "hint"),
    "N_CL_DOOR_PARKED": ("d", 1, "rows"),
    "N_CADENCE_PAUSE": (2, "k", 1, 3, "carried"),
    "N_CADENCE_PAUSE_CARRIED": ("rows",),
    "V_ASK_NOLISTEN_CMD": ("p", "m"),
    "V_PLAN_DRIFT": (1, "rows"),
    "V_INTENT_EXPIRED": ("t", 1, 1, "cov"),
    # Epics and the published snapshot. USAGE constants carry no placeholder; the rest are single-substitution except CLI_EPIC_MADE/ATTACHED/WROTE.
    "CLI_EPIC_USAGE": None,
    "CLI_EPIC_REFUSED": ("reason",),
    "CLI_EPIC_MADE": ("f2757830", "a title"),
    "CLI_EPIC_ATTACHED": ("f2757830", 3),
    "CLI_PUBLISH_USAGE": None,
    "CLI_PUBLISH_WROTE": ("agent/pr/x.md", 1312, 1),
    "CLI_INTENT_USAGE": None,
    "CTX_CHECKLISTS": ("listing",),
    "CTX_PLANS": ("l",),
    "CTX_PLANS_EXCERPT": ("p", "b"),
    "V_UNCITED": ("x",),
    "V_FOUND_NOT_FIXED": None,
    "V_UNSTATED": ("#1",),
    "V_MISLABELLED": ("x",),
    "V_OUT_OF_SYNC": (1, "#1"),
    "V_SUBMODULE_POINTER": (1, "x"),
    # Printed verbatim by `--help`; no interpolation, so None (skip the % check) rather than an arity. It still has to be REGISTERED, which is the point of the gap check: a constant nobody mapped is a constant nobody rendered.
    "USAGE": None,
    "V_HOOK_BLIND": ("p", "e", "f"),
    "V_NO_REMAINING": ("x",),
    "R_BLOCK": (1, "v", "f"),
    "R_BLOCK_FOCUS": ("v", "m", "f"),
    "R_FOCUS_MORE": (2,),
    "R_FOCUS_ONLY": None,
    "N_CI_QUEUE": ("r", 2, 30, ""),
    "N_CI_QUEUE_PR_STALE_LINE": None,
    "V_BG_REPORT": ("never", "2026-01-01T00:15:00Z", 15, 2, "rows"),
    "V_BG_REPORT_TASKS": ("never", "2026-01-01T00:15:00Z", 15, 2, 1, "tasks", "rows"),
    "CLI_ASK_OPERATOR_NO_DEFAULT": None,
    "CLI_ASK_UNKNOWN_RECIPIENT": ("to", "a, b"),
    # v19: runtime caller identity (L1 refusal, L2 backstop, L3 repair).
    "CLI_REASSIGN_USAGE": None,
    "CLI_REASSIGN_ALIVE": ("p", "p"),
    "CLI_REASSIGN_YOUNG": ("p", 5, 30, "p"),
    "CLI_REASSIGN_EMPTY": ("p", "p"),
    "CLI_REASSIGN_DONE": ("p", "m", "i", "r", "m", "m"),
    "N_PHANTOM_IDENTITY": (1, "rows", "p", "m"),
    "N_PHANTOM_BLIND": ("why",),
    "R_JUDGE_UNAVAILABLE": ("e", "f", "m"),
    "R_REGGATE_MALFORMED": ("p", "f"),
    "R_JUDGE_CONTINUE": ("r", "n", "t"),
    "R_REGGATE_BLOCK": ("b", "i", "", "", "m", "t"),
    "R_REGGATE_HALLUCINATED": ("g",),
    "CLI_REQUEST_USAGE": None,
    # Round-log splice verb (wl_roundlog.py) and the admission detector (wl_admit.py). USAGE and PROMPT carry no placeholders; REFUSED takes (reason, detail) and NO_LOG takes the target path.
    "CLI_ROUNDLOG_USAGE": None,
    "ADMISSION_PROMPT": None,
    "CLI_ROUNDLOG_REFUSED": ("v", "d"),
    "CLI_ROUNDLOG_NO_LOG": ("p",),
    "CLI_BODY_REFUSED": ("b", 1200, 1000),
    "CTX_SESSION_START": ("s", "d", "l", ""),
    "CTX_SESSION_START_STALE": (3, "s"),
    "CTX_POSTCOMPACT_MISSING": ("p", "m"),
    "CTX_POSTCOMPACT_BRIEFING": ("d", "s", "r", "p", "t"),
    "CTX_POSTCOMPACT_PEERS": ("b",),
    "JUDGE_PROMPT": {
        "streak": 1,
        "remaining": "r",
        "leases": 0,
        "loop": "l",
        "citations": "c",
        "message": "m",
        "traps": "t",
    },
    "REGGATE_PROMPT": {"fixset": "f", "keys": "k"},
    "FIXSET_GROUND_TRUTH": {"count": 1, "files": "f", "more": ""},
    "V_PLAN_ADOPTED": {"rel": "p", "n_open": 2, "n_gap": 1, "recipes": "r", "me": "m"},
    # v20 plan fidelity (wl_planfid.py). V_PLANFID takes the plan path, the umbrella rows, the untracked-task rows, the judge's instruction, and then the session prefix TWICE (once for the --add exit, once as the owner tag of the deferral line) before the planfid: token.
    "V_PLANFID": ("p", "u", "m", "i", "me", "me", "t"),
    "V_PLANFID_DEGRADED": ("e",),
    # v21 idle-stall gate. V_IDLE_STALL takes the open-item count, the rendered rows, then the session prefix THREE times (one per exit: --tick, --lease, --defer). V_UNBLOCKED_CLAIM takes the count and the claimed lines.
    "V_IDLE_STALL": (1, "rows", "me", "me", "me"),
    "V_UNBLOCKED_CLAIM": (1, "rows"),
    # v23 pending-ask gate. V_PENDING_ASK takes the announcing line then the session prefix (the --defer exit); N_ASK_REFUSALS takes the count and the ledger path.
    "V_PENDING_ASK": ("line", "me"),
    "N_ASK_REFUSALS": (2, "p"),
    # v22. V_DEFERRED_FINDING takes the rendered finding lines; V_SWEEP_MOMENT takes what just closed. Both are single-substitution, and case 117 is what caught them being unregistered: the registry works.
    "V_DEFERRED_FINDING": ("rows",),
    "V_SWEEP_MOMENT": ("an item this turn",),
    "PLANFID_PROMPT": {"plan": "p", "items": "i", "message": "m"},
    # v21 priority ladder. V_WAITER_LAPSED takes which exit the waiter took, how many minutes ago, the live-peer count, the wl_wait path and the session prefix. V_PR_FINISH takes the branch, the PR number, the rendered boxes, then the hook path, the session prefix and the PR number for the --add exit, and the hook path and the session prefix for the --tick. R_ALWAYS_COLLAPSED takes
    # the rendered one-line-per-invariant block.
    "V_WAITER_LAPSED": ("timeout", 12, 2, "p", "me"),
    "V_PR_FINISH": ("b", 543, "rows", "h", "me", 543, "h", "me"),
    "R_ALWAYS_COLLAPSED": ("rows",),
    # v23 lineage. CLI_ADOPT_USAGE takes nothing (it is a static usage block). CLI_ADOPT_REFUSED takes the session prefix, the predecessor prefix and the reason the evidence failed; CLI_ADOPT_SELF takes the prefix that turned out to be the caller; and CLI_ADOPT_DONE takes the session prefix, the predecessor prefix, the rung that fired, the evidence basis, the boundary uuid, how
    # many items just changed owner, and the session prefix again for the follow-up command.
    "CLI_ADOPT_USAGE": None,
    "CLI_MIGRATE_USAGE": None,
    "CLI_ADOPT_REFUSED": ("me", "prev", "why"),
    # No format args: it is appended to REGGATE_PROMPT verbatim, never % -ed.
    "REGGATE_GATE_MAINTENANCE": None,
    "CLI_ADOPT_SELF": ("prev",),
    "CLI_ADOPT_DONE": ("me", "prev", "continued-in", "1 shared record", "bde8bb05", 3, "me"),
    # W12 plan records (wl_planrec.py). USAGE carries no placeholder; REFUSED takes the RecordError text and DRY takes the rendered record, both single substitutions. WROTE and REVIVED are keyed, and WROTE spends `blob` three times (the git show recipe, the git log recipe, and the message body), which is exactly the arity a positional tuple would get wrong silently.
    "CLI_PLANREC_USAGE": None,
    "CLI_PLANREC_REFUSED": ("why",),
    "CLI_PLANREC_DRY": ("record",),
    "CLI_PLANREC_WROTE": {
        "rel": "p",
        "status": "compacted",
        "bytes": 900,
        "was": 9000,
        "blob": "b",
        "me": "m",
    },
    "CLI_PLANREC_REVIVED": {"rel": "p", "blob": "b", "bytes": 9000},
    # W12 P2. --plan-why has THREE answers and each is its own constant, because "no record names this file" and "there is no index" are different results and collapsing them would make an empty answer indistinguishable from a blind one. NO_EDGE spends `path` twice (the sentence and the git log recipe), which a positional tuple would get wrong silently.
    "CLI_PLANWHY_USAGE": None,
    "CLI_PLANWHY_HIT": {"path": "p", "body": "b"},
    "CLI_PLANWHY_NO_EDGE": {"path": "p", "n": 3, "index": "agent/INDEX.md"},
    "CLI_PLANWHY_NO_INDEX": {"path": "p", "index": "agent/INDEX.md"},
    "CLI_PLANTICK_USAGE": None,
    "CLI_PLANTICK_DRY": {"rel": "p", "note": "n"},
    "CLI_PLANTICK_WROTE": {"rel": "p", "ledger": "l", "note": "n", "me": "m"},
}


def load_catalogue():
    """`worklist_messages.py` loaded by path, exactly as the bash probe loaded it."""
    path = wlfix.STOP_DIR / "worklist_messages.py"
    spec = importlib.util.spec_from_file_location("wm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_117_the_message_catalogue_renders_at_every_call_site_arity():
    """Shape protection for the whole catalogue, including the constants no needle in this suite ever reaches."""
    catalogue = load_catalogue()
    failures = []
    for name, args in ARITY.items():
        value = getattr(catalogue, name, None)
        if value is None:
            failures.append("MISSING %s" % name)
            continue
        if args is None:
            continue
        try:
            value % args
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            # The bash caught bare Exception. These four are what a `%` render can raise: a missing key, too few or mistyped arguments, and an unsupported format character. Anything outside them is a defect this test should surface as an error rather than fold into the tally.
            failures.append("ARITY %s: %s" % (name, exc))
    strings = {
        key
        for key, value in vars(catalogue).items()
        if not key.startswith("_") and isinstance(value, str)
    }
    gap = strings - set(ARITY)
    if gap:
        failures.append("UNMAPPED new constant(s), add arity here: %s" % sorted(gap))
    assert not failures, "catalogue-arity failures=%d: %s" % (len(failures), failures)


def test_118_a_missing_catalogue_fails_closed_and_spares_the_query_modes(wl):  # noqa: F811
    """The import is guarded so a broken worklist_messages.py cannot become the old crash-reads-as-ALLOW hole: message USE raises into the crash handler (block, naming the catalogue), while --path, which uses no messages, keeps working for the scripts that call it."""
    nocat = wl.base / "nocat"
    (nocat / "proj" / ".git").mkdir(parents=True, exist_ok=True)
    (nocat / "tmp").mkdir(parents=True, exist_ok=True)
    hook = nocat / "worklist.py"
    shutil.copy(str(wlfix.HOOK), str(hook))

    env = dict(wl.env)
    env["TMPDIR"] = str(nocat / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(nocat / "proj")
    got = run_script(hook, ["--path"], env)
    merged = got.out + got.err
    why = "--path broke without the catalogue: rc=%d %r" % (got.rc, merged[:120])
    assert got.rc == 0, why
    assert "claude-worklist" in merged, why

    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(nocat / "proj")).lstrip("_")
    worklist = nocat / "tmp" / "claude-worklist" / ("%s.md" % slug)
    worklist.parent.mkdir(parents=True, exist_ok=True)
    with worklist.open("a", encoding="utf-8") as handle:
        handle.write("- [ ] (deadbeef) open thing\n")

    stop_env = dict(env)
    stop_env["WORKLIST_TASKS_DIR"] = str(nocat / "tasks")
    stop_env["GITHUB_ACTIONS"] = ""
    payload = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(nocat / "proj"),
            "transcript_path": "/none",
            "last_assistant_message": "done",
        }
    )
    blocked = run_script(hook, [], stop_env, stdin=payload)
    assert blocked.decision == "block", "missing catalogue produced decision=%s: %r" % (
        blocked.decision,
        blocked.out[:160],
    )
    assert "worklist_messages" in blocked.out, (
        "the blocking stop did not name the catalogue: %r" % blocked.out[:160]
    )
