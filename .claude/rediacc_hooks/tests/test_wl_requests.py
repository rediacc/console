"""Cross-session requests, ported from `.claude/hooks/stop/worklist-cases/05-requests.sh`.

Delivery, answers, declines, broadcasts, escalation to the operator, and the concurrency races. One test per numbered bash case, carrying the same assertions in the same order against the same subprocess.

THE CONTROLS ARE THE POINT of several of these, and they are marked as such: a request between two OTHER sessions that must not block a bystander, a poll cron that counts as a listener, an ask to the operator that needs no waiter, and a crowded stop with no request outstanding that must stay silent about one. Each is a document that must still PASS, so the rule under test cannot be
satisfied by blocking everything.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time

from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def stamp_minutes_ago(minutes: float) -> str:
    """The UTC stamp the bash cases produced with `date -u -d '-N minutes'`."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes * 60))


def plant_ask(fix, ident: str, sender: str, recipient: str, body: str, minutes_ago: float) -> None:
    """One raw `ask` event appended to the requests sidecar, backdated."""
    line = '{"ev":"ask","id":"%s","from":"%s","to":"%s","at":"%s","body":"%s"}\n' % (
        ident,
        sender,
        recipient,
        stamp_minutes_ago(minutes_ago),
        body,
    )
    with fix.stem(".requests").open("a", encoding="utf-8") as handle:
        handle.write(line)


def compact_with_timeout(fix, seconds: int = 20) -> subprocess.CompletedProcess:
    """`--compact` under a hard timeout.

    LOCAL HELPER, because `fix.python` has no timeout. The bash case wrapped this call in `timeout 20` deliberately: the event-log compaction once deadlocked against its own flock (`load(sync=True)` inside the held lock), and a bare call would turn that regression into a hung suite instead of a failure.
    """
    env = dict(fix.env)
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    return subprocess.run(
        [sys.executable, str(fix.hook), "--compact"],
        input="",
        capture_output=True,
        text=True,
        env=env,
        timeout=seconds,
        check=False,
    )


def posted(rid: str) -> str:
    """The request id `--ask` printed, refused when it is empty.

    FIXTURE INTEGRITY, not a behaviour assertion. `--ask` is refused when the recipient has never briefed, and a control that expects `allow` passes just as well when no request was planted at all: the first run of this port had exactly that shape and one control was green for the wrong reason.
    """
    assert rid, "FIXTURE BROKEN: --ask posted no request, so the assertion below is vacuous"
    return rid


def test_65_a_request_addressed_to_me_blocks_my_stop(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.askid_as("cafe1234", "cafe1234", "deadbeef", "regenerate the caption media and republish")
    wl.check("block", "waiting on you", "a direct request to this session blocks")


def test_65b_the_block_carries_the_whole_payload_both_directions(wl):  # noqa: F811
    """The motivating failure: a finding parked in a commit message, correct and unread, relayed by hand.

    Delivery must not depend on the recipient choosing to read anything (`--requests` included), so the body and the answer ride inside the block untruncated. The crucial detail sits past the 300-char mark that an earlier draft truncated at.
    """
    wl.say("done for now")
    wl.brief_now()
    longask = (
        "caption combos: "
        + "x" * 320
        + " CRUCIAL-ASK: republish then rerun check:ci-tutorial-caption-sync"
    )
    rid = wl.askid_as("cafe1234", "cafe1234", "deadbeef", longask)
    wl.check(
        "block",
        "CRUCIAL-ASK: republish then rerun",
        "the tail of a long request body survives into the block",
    )
    longans = (
        "context: " + "y" * 320 + " CRUCIAL-ANSWER: the media session already republished at 14:02Z"
    )
    wl.cli("--answer", "deadbeef", rid, longans)
    event = json.dumps(
        {
            "session_id": "cafe1234-9999-8888-7777-666666666666",
            "cwd": str(wl.proj),
            "transcript_path": str(wl.transcript),
            "last_assistant_message": "done",
        }
    )
    env = dict(wl.env)
    env["CLAUDE_PROJECT_DIR"] = str(wl.proj)
    env["WORKLIST_TASKS_DIR"] = str(wl.base / "tasks")
    env["WORKLIST_JUDGE"] = "off"
    env["GITHUB_ACTIONS"] = ""
    got = wl.python([], stdin=event, env=env)
    assert '"decision": "block"' in got.out, (
        "the answer did not block the asker: %s" % got.out[:220]
    )
    assert "CRUCIAL-ANSWER: the media session already republished" in got.out, (
        "the tail of a long answer was truncated: %s" % got.out[:220]
    )


def test_66_control_a_request_between_two_other_sessions_never_blocks_me(wl):  # noqa: F811
    """CONTROL: a bystander stays unblocked, so the delivery rule cannot be satisfied by blocking on every request in the store."""
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    posted(wl.askid_as("aaaa1111", "aaaa1111", "cafe1234", "please do Y"))
    wl.check("allow", "", "someone else's request does not block a bystander")


def test_67_control_my_own_open_request_never_blocks_me_and_is_reported(wl):  # noqa: F811
    """CONTROL: the asker is never blocked on their own open request.

    The fixture produces TWO class-2 sections (the other session's brief and the open request), and the output queue releases one per stop by default. This case is about the request being reported at all, not about rationing, so it drains wide; cases 173 to 177 own the rationing behaviour.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    posted(wl.askid("deadbeef", "cafe1234", "please regenerate captions"))
    wl.check("allow", "still OPEN", "the asker is never blocked on their own open request")


def test_68_answering_releases_the_recipient(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    rid = wl.askid_as("cafe1234", "cafe1234", "deadbeef", "do X")
    wl.check("block", "waiting on you", "unanswered, it blocks")
    wl.cli("--answer", "deadbeef", rid, "done: X is finished, gate green")
    wl.check("allow", "", "answered, it releases the recipient")


def test_69_a_decline_must_carry_a_reason_and_an_unanswered_ack_is_refused(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    rid = wl.askid_as("cafe1234", "cafe1234", "deadbeef", "do X")
    refused = wl.cli("--decline", "deadbeef", rid)
    assert refused.rc != 0, "a reasonless decline was accepted: %s" % refused.out[:200]
    sidecar = wl.stem(".requests").read_text(encoding="utf-8")
    assert '"ev":"decline"' not in sidecar, "the refused decline still left an event behind"
    acked = wl.cli_as("cafe1234", "--ack", "cafe1234", rid)
    assert acked.rc != 0, "acking an unanswered request was accepted: %s" % acked.out[:200]


def test_70_the_answer_is_delivered_to_the_asker_as_a_block_until_ack(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    rid = wl.askid("deadbeef", "cafe1234", "which session owns caption regen")
    wl.cli_as(
        "cafe1234",
        "--answer",
        "cafe1234",
        rid,
        "the media session owns it; rerun your gate after publish",
    )
    wl.check(
        "block",
        "the media session owns it",
        "an unacked answer blocks the asker WITH the answer text",
    )
    wl.cli("--ack", "deadbeef", rid)
    wl.check("allow", "", "after --ack the answer never re-blocks")


def test_71_a_direct_decline_resolves_it_and_carries_its_reason_back(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    rid = wl.askid("deadbeef", "cafe1234", "please also do Z")
    wl.cli_as(
        "cafe1234",
        "--decline",
        "cafe1234",
        rid,
        "out of scope: Z belongs to the GPU session",
    )
    wl.check(
        "block",
        "out of scope: Z belongs to the GPU session",
        "the decline reason reaches the asker as a block",
    )
    wl.cli("--ack", "deadbeef", rid)
    wl.check("allow", "", "an acked decline is silent")


def test_72_a_broadcast_blocks_each_live_session_only_until_it_responds(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    rid = wl.askid_as("cafe1234", "cafe1234", "*", "who owns tutorial caption regeneration")
    wl.check(
        "block", "broadcast", "an unanswered broadcast blocks a session that has not responded"
    )
    wl.cli("--decline", "deadbeef", rid, "not my area: I only touch the stop hook")
    wl.check("allow", "", "declining a broadcast releases the decliner")


def test_73_a_request_to_a_dead_recipient_escalates_to_an_operator_deferral_once(wl):  # noqa: F811
    """v10: the `[?]` is a store event, not a markdown append. `--list` renders the same line shape the markdown used to carry, so the assertions keep their shape and read the store instead of the file."""
    wl.say("done for now")
    wl.brief_now()
    plant_ask(wl, "feedc0de", "cafe1234", "beef9999", "republish the caption media", 120)
    wl.check("allow", "ESCALATED", "a dead-recipient request blocks nobody and escalates")
    listing = wl.cli("--list").out
    assert "- [?] (cafe1234) request #feedc0de" in listing, (
        "no operator [?] item was recorded: %s" % listing[:400]
    )
    assert "proceeds without an answer" in listing, (
        "the [?] item carries no generic DEFAULT: %s" % listing[:400]
    )
    wl.run()
    lines = [line for line in wl.cli("--list").out.splitlines() if "request #feedc0de" in line]
    assert len(lines) == 1, "escalation is not idempotent: %d lines" % len(lines)


def test_74_a_broadcast_with_no_other_live_session_escalates(wl):  # noqa: F811
    """The `[?]` lands on the ASKER (deadbeef), so it is a deferred item of ours the moment it is appended, and the usual something-remains machinery (handover, `## Remaining`) applies to this stop. That is intended: the asker must report that the question went to the operator."""
    wl.say(
        "done for now\n\n## Remaining\n"
        "- the fedora ownership question, escalated to the operator as a [?]"
    )
    wl.brief_now()
    wl.hand_now()
    wl.askid("deadbeef", "*", "anyone own the flaky fedora leg? DEFAULT: I quarantine it myself")
    wl.check("allow", "ESCALATED", "a broadcast nobody can answer escalates immediately")
    listing = wl.cli("--list").out
    assert "DEFAULT: I quarantine it myself" in listing, (
        "the ask's own DEFAULT was not reused: %s" % listing[:400]
    )


def test_75_control_the_request_block_no_ops_under_github_actions(wl):  # noqa: F811
    """CONTROL: the same world that blocks off a runner must never block on one, or the suite would pass in CI for the wrong reason."""
    wl.say("done for now")
    wl.brief_now()
    wl.askid_as("cafe1234", "cafe1234", "deadbeef", "do X")
    wl.check("block", "waiting on you", "off a runner the request still blocks")
    wl.gha = "true"
    wl.check("allow", "", "GITHUB_ACTIONS=true never blocks a runner on a request")


def test_76_race_concurrent_writers_lose_nothing(wl):  # noqa: F811
    threads = [
        threading.Thread(
            target=wl.cli_as,
            args=("sess000%d" % i, "--ask", "sess000%d" % i, "cafe1234", "concurrent probe %d" % i),
        )
        for i in range(1, 17)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    sidecar = wl.stem(".requests")
    ids, bad, asks = set(), 0, 0
    for raw in sidecar.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if event.get("ev") == "ask":
            asks += 1
            ids.add(event.get("id"))
    assert (asks, len(ids), bad) == (16, 16, 0), (
        "concurrent asks were lost or torn: asks=%d ids=%d bad=%d" % (asks, len(ids), bad)
    )

    rid = min(
        json.loads(line)["id"]
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    answerers = [
        threading.Thread(
            target=wl.cli_as,
            args=("answ000%d" % i, "--answer", "answ000%d" % i, rid, "answer %d" % i),
        )
        for i in range(1, 9)
    ]
    for thread in answerers:
        thread.start()
    for thread in answerers:
        thread.join()
    needle = '"ev":"answer","id":"%s"' % rid
    found = sum(1 for line in sidecar.read_text(encoding="utf-8").splitlines() if needle in line)
    assert found == 8, "expected 8 answer events, found %d" % found


def test_77_an_over_length_body_is_refused_never_silently_truncated(wl):  # noqa: F811
    """Silent write-time truncation would be the commit-message defect one layer down: the tail (often the crucial part) vanishes while the sender is told the payload was delivered."""
    wl.say("done for now")
    wl.brief_now()
    at_limit = wl.cli_as("cafe1234", "--ask", "cafe1234", "deadbeef", "x" * 1000)
    assert at_limit.rc == 0, (
        "a body exactly at the 1000-char limit was refused: %s"
        % (at_limit.out + at_limit.err)[:200]
    )
    over = wl.cli_as("cafe1234", "--ask", "cafe1234", "deadbeef", "x" * 1100)
    assert over.rc != 0, "an over-length ask was accepted"
    assert "REFUSED rather than silently truncated" in over.err, (
        "over-length refusal was silent: %s" % over.err[:200]
    )
    asks = sum(
        1
        for line in wl.stem(".requests").read_text(encoding="utf-8").splitlines()
        if '"ev":"ask"' in line
    )
    assert asks == 1, "the refused ask leaked an event: %d ask events" % asks

    found = re.search(r"(?m)^#([0-9a-f]{8})", wl.cli("--requests").out)
    rid = found.group(1) if found else ""
    long_answer = wl.cli("--answer", "deadbeef", rid, "y" * 1100)
    assert long_answer.rc != 0, "an over-length answer was accepted"
    assert "REFUSED rather than silently truncated" in long_answer.err, (
        "over-length answer refusal was silent: %s" % long_answer.err[:200]
    )
    assert '"ev":"answer"' not in wl.stem(".requests").read_text(encoding="utf-8"), (
        "the refused answer leaked an event"
    )


def test_78_compact_never_touches_the_requests_sidecar(wl):  # noqa: F811
    """Blocking survives `--compact`, and the sidecar comes out byte-identical.

    The events file is forced into existence BEFORE compacting: the event-log compaction once deadlocked against its own flock (`load(sync=True)` inside the held lock), and this fixture's original shape dodged that path entirely because no events file had been created yet.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.askid_as("cafe1234", "cafe1234", "deadbeef", "must survive compaction")
    wl.add_item("- [ ] (deadbeef) live item that must survive compaction, exit 0")
    wl.add_item("- [~] (cafe1234) archived tombstone line")
    wl.cli("--list")
    before = hashlib.md5(wl.stem(".requests").read_bytes()).hexdigest()
    compact_with_timeout(wl)
    assert "archived tombstone" not in wl.wl.read_text(encoding="utf-8"), (
        "--compact did not run (tombstone still present), the test would be vacuous"
    )
    listing = wl.cli("--list").out
    assert "live item that must survive compaction" in listing, (
        "event-log compaction lost a live item: %s" % listing[:400]
    )
    after = hashlib.md5(wl.stem(".requests").read_bytes()).hexdigest()
    assert before == after, "--compact modified the requests sidecar"
    # FOCUS=off: this fixture has several outstanding checks and the assertion is about the request one specifically, not about which check the rotation picks.
    wl.env["WORKLIST_FOCUS"] = "off"
    wl.check("block", "waiting on you", "an open request still blocks after --compact")


def test_79_requests_survive_the_worklist_file_being_deleted_entirely(wl):  # noqa: F811
    """Deleting the worklist is the hook's documented allow-a-stop residual, but it must not delete cross-session obligations: the sidecar is a separate file and the request checks run unconditionally, not under `worklist.exists()`."""
    wl.say("done for now")
    wl.brief_now()
    rid = wl.askid_as("cafe1234", "cafe1234", "deadbeef", "still here after the worklist dies")
    wl.wl.unlink()
    wl.check("block", "waiting on you", "deleting the worklist does not delete the obligation")
    wl.cli("--answer", "deadbeef", rid, "done regardless of the worklist")
    wl.check("allow", "", "and the lifecycle still completes without a worklist file")


def test_80_race_concurrent_escalators_write_the_deferral_exactly_once(wl):  # noqa: F811
    """The double-write question: two sessions escalating the same request in the same second.

    By construction both appends happen INSIDE the non-blocking flock and every escalator re-reads AFTER acquiring it, so a racer either fails the acquire (skips) or sees the winner's escalate event. This drives 8 hook processes at one dead-recipient request to prove it empirically.
    """
    wl.say("done for now")
    wl.brief_now()
    plant_ask(wl, "feedc0de", "cafe1234", "beef9999", "race the escalators", 120)
    threads = [threading.Thread(target=wl.run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    items = [line for line in wl.cli("--list").out.splitlines() if "request #feedc0de" in line]
    events = [
        line
        for line in wl.stem(".requests").read_text(encoding="utf-8").splitlines()
        if '"ev":"escalate","id":"feedc0de"' in line
    ]
    assert (len(items), len(events)) == (1, 1), (
        "expected 1 [?] item and 1 escalate event, got %d and %d" % (len(items), len(events))
    )


def test_81_asking_a_live_peer_without_a_waiter_blocks(wl):  # noqa: F811
    """THE GAP THIS CLOSES, measured live 2026-08-27.

    The general NOT LISTENING check needs three things before it fires: a live non-poll work cron, a live peer, and WAITER_GRACE_NUDGES ignored nudges (half an hour). A session with NO cron directory therefore never trips it, and one was observed holding an open request to a peer seen minutes earlier, with no waiter, about to stop and wait forever for an answer it had no way to
    hear. Posting a request is the session choosing to depend on a reply, so this arm needs no grace period at all: one stop is enough.

    NO CRONS AT ALL, and that is the precise gap. A work cron WITHOUT a poll cron trips the existing V_NO_POLL_CRON check ("THIS SESSION HAS A LOOP BUT NOTHING LISTENING"), which would block first and mask this one: the first draft of this case did exactly that and reported a block from the wrong check. A session with NO loop is outside that check by construction, and is the shape
    actually observed live.
    """
    wl.crons = "[]"
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    wl.askid("deadbeef", "cafe1234", "please format the file that is reddening the lane")
    wl.check(
        "block",
        "NOT LISTENING FOR THE ANSWER",
        "an open ask, no waiter and no poll cron, blocks the stop",
    )


def test_81b_control_a_poll_cron_is_a_listener(wl):  # noqa: F811
    """CONTROL: the distinction the first draft of this check missed, and two existing cases caught: a waiter is faster, a cron is slower, both HEAR. Without this control the arm above would pass just as well if the check ignored crons entirely."""
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    posted(wl.askid("deadbeef", "cafe1234", "same state, but this session polls"))
    wl.check_quiet(
        "NOT LISTENING FOR THE ANSWER",
        "an open ask with a live poll cron does not demand a waiter",
    )


def test_82_control_an_ask_to_the_operator_needs_no_waiter(wl):  # noqa: F811
    """CONTROL: a human answers at a shell; there is nothing for a waiter to hear, and blocking here would make `--ask operator` unusable.

    THIS CONTROL IS VACUOUS IN THE LIVE TREE, found while porting it and reported rather than papered over. `--ask deadbeef operator ...` with no `DEFAULT:` in the body exits 1 and writes nothing: "REFUSED: a request to the operator must carry a DEFAULT:." So no request is ever posted, and the needle below is absent from any hook at all. The fixture is kept byte-faithful to the
    bash case it came from; making it real means a body carrying a `DEFAULT:`, which is a change to the case rather than to the port.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.askid("deadbeef", "operator", "which branch should this land on")
    wl.check_quiet("NOT LISTENING FOR THE ANSWER", "an operator ask does not demand a waiter")


def test_83_control_an_ask_to_a_session_that_never_briefed(wl):  # noqa: F811
    """CONTROL: nobody is going to answer, so requiring a listener would be theatre. The existing escalation path owns that case.

    THIS CONTROL IS VACUOUS IN THE LIVE TREE, for the same reason and found the same way. `--ask deadbeef 99999999 ...` exits 1 and writes nothing: "REFUSED: 99999999 has never briefed in this store, so a request addressed there lands in an inbox nobody reads." The recipient the case names is the one `--ask` refuses, so no request exists to demand a listener for, and unlike case 82
    no body would make it real.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.askid("deadbeef", "99999999", "into the void")
    wl.check_quiet(
        "NOT LISTENING FOR THE ANSWER",
        "an ask to an unbriefed session does not demand a waiter",
    )


def test_84_control_once_the_peer_answers_the_demand_lifts(wl):  # noqa: F811
    """CONTROL: the obligation is to hear the reply, not to hold a process forever. This leg proves the check keys on OPEN requests rather than on any request having ever existed. Without it, a check stuck permanently on would pass case 81."""
    wl.say("done for now")
    wl.brief_now()
    wl.brief_other("cafe1234")
    rid = posted(wl.askid("deadbeef", "cafe1234", "answer me"))
    wl.cli_as("cafe1234", "--answer", "cafe1234", rid, "done")
    wl.cli("--ack", "deadbeef", rid)
    wl.check_quiet("NOT LISTENING FOR THE ANSWER", "an answered ask no longer demands a waiter")


def test_69z_a_peers_request_is_an_invariant_and_cannot_be_rotated_away(wl):  # noqa: F811
    """Its own comment says "the payload rides inside the obstacle": this block IS the delivery of the peer's message, not a pointer to it.

    A delivery mechanism that can be rotated behind docs drift is not one, and the peer cannot see that this session decided to read about its STATE.md instead. Promoted 2026-08-28 under I2 (somebody else pays), alongside no-waiter and no-waiter-asked.

    `brief_now` is REQUIRED, not decoration: `--ask` is refused when the recipient has never briefed, so without it the fixture plants no request at all and the case measures an empty inbox. (It did, on its first run: six checks outstanding and not one of them the request.) NO hand_now, one open item, an unfixed finding, no poll cron: four rotating checks that used to be able to
    win the pick ahead of the request.
    """
    wl.crons = json.dumps([{"id": "c1", "schedule": "*/30 * * * *", "prompt": "work loop"}])
    wl.brief_other("peer1234")
    wl.brief_now()
    wl.add_item("- [ ] (deadbeef) something of my own")
    posted(
        wl.askid_as("peer1234", "peer1234", "deadbeef", "the baseline number you measured, please")
    )
    wl.say("I looked at it.\n\n- Agent finding I did not fix: the dead symlink under .ci")
    out = wl.run().out
    assert "cross-session REQUEST(S) are waiting on you" in out, (
        "the request was rotated behind this session's own housekeeping: %s" % out[:400]
    )
    assert "the baseline number you measured" in out, (
        "the request's body did not survive a crowded first stop: %s" % out[:400]
    )


def test_69z_c1_control_no_request_and_the_same_crowd_says_nothing(wl):  # noqa: F811
    """CONTROL: without this, 69z passes for any hook that prints the word REQUEST somewhere."""
    wl.crons = json.dumps([{"id": "c1", "schedule": "*/30 * * * *", "prompt": "work loop"}])
    wl.brief_other("peer1234")
    wl.brief_now()
    wl.add_item("- [ ] (deadbeef) something of my own")
    wl.say("I looked at it.\n\n- Agent finding I did not fix: the dead symlink under .ci")
    out = wl.run().out
    assert out.strip(), "the hook produced NO output at all, so the absence below is vacuous"
    assert "cross-session REQUEST(S) are waiting on you" not in out, (
        "the request section fires with no request: %s" % out[:300]
    )
