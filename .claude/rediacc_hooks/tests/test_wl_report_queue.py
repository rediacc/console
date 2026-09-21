"""The one-section-per-stop report queue (FIFO, priority, one-shots), the judge stamp, poll baselines, and the quiet-wake collapse.

Ported from `.claude/hooks/stop/worklist-cases/17-report-queue.sh`, one pytest function per numbered bash case. A bash block that called `setup` a second time mid-case becomes its own function here, which is what splits 173, 174 and 176 into a FIRE function and a CONTROL function each.

Operator, 2026-07-31: the allow report still emitted every fired section at once. It now releases WORKLIST_REPORT_PER_STOP of them, highest priority first, and the tail states how many are waiting, because a silent cap reads as "that is everything", the same argument the guide's own truncation carries.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_rollup, ci_run, ci_running, ci_setup
from rediacc_hooks.tests.test_wl_guide_and_deferrals import shim_judge_out
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# The four class-2 sections the outq fixture fires on one stop. FOUR, not three: an orphaned item is by construction another session's OPEN item, so it always drags the other-session count along with it.
OUTQ_SECTIONS = (
    "INBOX HAS BEEN QUIET",
    "Other sessions in this worktree",
    "ORPHANED item(s)",
    "nothing open for this session",
)

# The stop message case 176 needs. The escalation opens a real `- [?]`, so the stop message must carry a Remaining section and STATE.md must exist; without both, higher-ranked checks outrank the very note under test.
CIMSG_176 = "work done\n\n## Remaining\n- the escalated operator question"


def stale_peer_transcript(fix) -> None:
    """An orphan needs a dead owner: a transcript for cafe1234 older than WORKLIST_DEAD_HOURS but younger than WORKLIST_ARCHIVE_HOURS."""
    path = fix.base / "cafe1234.jsonl"
    path.write_text("", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(path, (old, old))


def outq_fixture(fix) -> None:
    """Four class-2 sections firing on one stop."""
    fix.say("done for now")
    fix.brief_now()
    fix.hand_now()
    fix.brief_other("cafe1234")
    stale_peer_transcript(fix)
    fix.add_item("- [ ] (cafe1234) their abandoned item")


def outq_seen(out: str) -> int:
    """How many of the four section headers are present."""
    return sum(1 for needle in OUTQ_SECTIONS if needle in out)


def outq_fill(fix) -> None:
    """Queue the four, one stop at a time, emitting nothing."""
    fix.env["WORKLIST_REPORT_PER_STOP"] = "0"
    fix.say("done for now")
    fix.brief_now()
    fix.hand_now()
    fix.run()  # the poll-backoff tip is alone on this stop
    fix.brief_other("cafe1234")
    fix.newturn()
    fix.say("done for now")
    fix.run()  # the other session's brief joins it
    stale_peer_transcript(fix)
    fix.add_item("- [ ] (cafe1234) their abandoned item")
    fix.newturn()
    fix.say("done for now")
    fix.run()  # the orphan and its item count join


def outq_order(fix) -> list[str]:
    """Drain four stops at one section each, returning the order they arrived in."""
    fix.env["WORKLIST_REPORT_PER_STOP"] = "1"
    order: list[str] = []
    for _ in range(4):
        fix.newturn()
        fix.say("done for now")
        out = fix.run().out
        if "INBOX HAS BEEN QUIET" in out:
            order.append("backoff")
        if "Other sessions in this worktree" in out:
            order.append("others")
        if "ORPHANED item(s)" in out:
            order.append("orphans")
        if "nothing open for this session" in out:
            order.append("items")
    return order


def escalations(fix) -> int:
    """How many escalate events the request log carries."""
    path = fix.stem(".requests")
    if not path.is_file():
        return 0
    return path.read_text(encoding="utf-8").count('"ev":"escalate"')


def plant_dead_request(fix, rid: str) -> None:
    """One 300-minute-old ask nobody has answered, which is what the escalation fires on."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 300 * 60))
    with fix.stem(".requests").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "ask",
                    "id": rid,
                    "from": "deadbeef",
                    "to": "zzzzzzzz",
                    "at": stamp,
                    "body": "restart the leg? DEFAULT: restart it",
                }
            )
            + "\n"
        )


def ctx_event(fix, mode: str) -> None:
    """Drive a context-rebuilding hook mode: `ctx_event(wl, "--session-start")`."""
    fix.python([mode], stdin=json.dumps({"session_id": fix.sid, "cwd": str(fix.proj)}))


def judge_turn(fix) -> None:
    """A fresh turn whose message satisfies the Remaining demand."""
    fix.newturn()
    fix.say("answer\n\n## Remaining\n| #7 | merge the chain | pending, the operator |")


def bgwait_doc(fix) -> tuple:
    """The per-session state document and its parsed contents."""
    path = fix.stem(".state-deadbeef.json")
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return path, {}


def age_bgwait(fix) -> None:
    """Backdate the check-in clock so the next stop finds the window open."""
    path, doc = bgwait_doc(fix)
    doc.setdefault("bgwait", {})["at"] = "2026-01-01T00:00:00Z"
    path.write_text(json.dumps(doc), encoding="utf-8")


def has_bgwait(fix) -> str:
    """ "present" when the wait clock survives, "absent" when leaving the wait cleared it."""
    _, doc = bgwait_doc(fix)
    return "present" if doc.get("bgwait") else "absent"


def bg_watch(fix, ident: str, description: str = "long watch") -> str:
    """One running shell worker with a stream under WORKLIST_BG_OUTPUT_DIR."""
    outdir = fix.base / "bgout"
    outdir.mkdir(parents=True, exist_ok=True)
    fix.env["WORKLIST_BG_OUTPUT_DIR"] = str(outdir)
    (outdir / ("%s.output" % ident)).write_text("stream\n", encoding="utf-8")
    return json.dumps(
        [{"id": ident, "type": "shell", "status": "running", "description": description}]
    )


def test_173_exactly_one_of_four_sections_is_released_and_the_tail_counts_the_rest(wl):  # noqa: F811
    """FOUR sections fire, one is released, and the tail states how many are waiting."""
    outq_fixture(wl)
    got = wl.run()
    assert outq_seen(got.out) == 1, "released %d section(s): %s" % (
        outq_seen(got.out),
        got.out[:400],
    )
    assert "(3 more report section(s) queued" in got.out, got.out[:400]


def test_173_control_a_wide_drain_emits_all_four_and_claims_no_queue(wl):  # noqa: F811
    """CONTROL: one planted fact differs, the per-stop budget. All four land and nothing claims a queue, so the cap is the only thing the FIRE leg measured."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    outq_fixture(wl)
    got = wl.run()
    assert outq_seen(got.out) == 4, "released %d of 4: %s" % (outq_seen(got.out), got.out[:400])
    assert "more report section(s) queued" not in got.out, got.out[:400]


def test_174_one_priority_class_drains_in_the_order_it_was_enqueued(wl):  # noqa: F811
    """FIFO inside a priority class. All four sections are class 2, so nothing outranks anything here and the only thing deciding the order is the sequence number each entry earned when it was first queued."""
    outq_fill(wl)
    assert outq_order(wl) == ["backoff", "others", "orphans", "items"]


def test_174_control_a_changed_section_goes_to_the_back_of_its_own_class(wl):  # noqa: F811
    """CONTROL: the operator's "changed content re-enqueues at its priority", proven rather than asserted. Touch the SECOND section's body and it loses the position it had earned instead of keeping it."""
    outq_fill(wl)
    wl.brief_at("cafe1234", 0, "pivoted to the deploy fix")
    wl.newturn()
    wl.say("done for now")
    wl.run()
    assert outq_order(wl) == ["backoff", "orphans", "items", "others"]


def test_175_the_class_0_ci_note_is_released_ahead_of_the_older_class_2_advisory(wl):  # noqa: F811
    """Priority beats FIFO: an actionable CI note passes an older advisory.

    PLANTED DEFECT, run 2026-07-31: outq_drain's sort key was changed from (prio, seq) to (seq,). Both legs failed, the first reporting the worklist advisory in the released slot while the CI note was the one left queued, which is the inversion exactly. Cases 173 and 174 stayed green throughout. A priority ladder nobody has watched invert is a ladder nobody knows is wired up.
    """
    ci_setup(wl)
    # The older advisory is another session's item count, NOT its brief: ci_trouble returns "multi-session" the moment a second brief is live, and a fixture that quietly switches off the check it is racing proves nothing.
    wl.add_item("- [ ] (cafe1234) their abandoned item")
    wl.env["WORKLIST_REPORT_PER_STOP"] = "0"
    ci_rollup(wl, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    ci_run(wl)  # the class-2 advisory is queued first, and waits
    wl.env["WORKLIST_REPORT_PER_STOP"] = "1"
    ci_rollup(
        wl,
        "PENDING",
        "[%s, %s]" % (ci_job("E2E / opensuse", "FAILURE"), ci_running("E2E / ubuntu")),
    )
    got = ci_run(wl)
    assert "retry allowlist" in got.out, "priority did not beat FIFO: %s" % got.out[:400]
    assert "nothing open for this session" not in got.out, (
        "priority did not beat FIFO: %s" % got.out[:400]
    )
    # CONTROL: with the run green there is no class-0 section, and the advisory that was passed over is released on the very next stop. It is also what makes the leg above non-vacuous: the section really was queued and waiting.
    ci_rollup(wl, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    got = ci_run(wl)
    assert "nothing open for this session" in got.out, (
        "CONTROL: the advisory was lost, not delayed: %s" % got.out[:400]
    )


def test_176_a_one_shot_is_never_dropped_only_delayed(wl):  # noqa: F811
    """The property that decides the whole design, so the fixture makes the one-shot LOSE its first stop.

    escalate_requests() spends its budget at COMPUTE time: it appends the escalate event and the `[?]` exactly once, so nothing can regenerate that note and a report with no room for it has to keep it.

    The original vehicle was the operator email digest; that channel was removed, and this is the same property on a producer that remains, where the escalation count is the proof exactly as the mail count used to be.

    PLANTED DEFECT, run 2026-07-31: outq_drain's per-entry removal was replaced with `q["items"][:] = []`. Leg 2 failed: the one-shot note was gone for good and a class-2 advisory took its place, while the producer's own count proved no second compute could bring it back.
    """
    ci_setup(wl)
    wl.hand_now()
    wl.env["WORKLIST_REPORT_PER_STOP"] = "1"
    plant_dead_request(wl, "cccc3333")
    ci_rollup(
        wl,
        "PENDING",
        "[%s, %s]" % (ci_job("E2E / opensuse", "FAILURE"), ci_running("E2E / ubuntu")),
    )
    got = ci_run(wl, message=CIMSG_176)
    assert "retry allowlist" in got.out, "leg 1 shape wrong: %s" % got.out[:400]
    assert "ESCALATED" not in got.out, "leg 1 shape wrong: %s" % got.out[:400]
    assert escalations(wl) == 1, "leg 1 escalations=%d" % escalations(wl)

    ci_rollup(wl, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    got = ci_run(wl, message=CIMSG_176)
    assert "ESCALATED" in got.out, "the one-shot was DROPPED, not delayed: %s" % got.out[:400]
    assert escalations(wl) == 1, (
        "a second escalation was computed, so the note was regenerated rather than queued: %d"
        % escalations(wl)
    )

    ci_run(wl, message=CIMSG_176)
    got = ci_run(wl, message=CIMSG_176)
    assert "more report section(s) queued" not in got.out, (
        "entries still queued after every section was released: %s" % got.out[:400]
    )


def test_176_control_with_nothing_outranking_it_the_escalation_lands_on_stop_1(wl):  # noqa: F811
    """CONTROL: the same fixture with no CI trouble at all."""
    ci_setup(wl)
    wl.hand_now()
    plant_dead_request(wl, "dddd4444")
    ci_rollup(wl, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    got = ci_run(wl, message=CIMSG_176)
    assert "ESCALATED" in got.out, "the note did not land unopposed either: %s" % got.out[:400]


def test_177_the_judge_line_is_a_stamp_unless_the_context_is_fresh_or_the_reason_changed(wl):  # noqa: F811
    """Operator, 2026-07-31: the approval reason was reprinted on every stop.

    It now rides a stop whose context was just rebuilt (SessionStart, PostCompact) or whose reason genuinely changed, and every other stop gets the bare stamp. The verdict cache is pinned OFF so every stop pays a fresh call: a cached verdict would make the cache, not the signature latch, the thing under test.
    """
    wl.env["WORKLIST_JUDGE_CACHE_MIN"] = "0"
    # Six stops on an unchanged world would otherwise trip stuck detection, which has nothing to do with what this case measures.
    wl.env["WORKLIST_STUCK_ROUNDS"] = "99"
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "merge the chain")
    judge_turn(wl)
    shim_judge_out(
        wl,
        {
            "verdict": "stop",
            "reason": "MARKER_REASON_ONE waiting on the run",
            "next_action": "none",
        },
    )
    ctx_event(wl, "--session-start")
    got = wl.runj()
    assert "MARKER_REASON_ONE" in got.out, (
        "the fresh-context reason was withheld: %s" % got.out[:400]
    )

    judge_turn(wl)
    got = wl.runj()
    assert "Stop-gate judge" in got.out, got.out[:400]
    assert "MARKER_REASON_ONE" not in got.out, (
        "CONTROL: the reason was reprinted on an ordinary stop: %s" % got.out[:400]
    )

    # PostCompact is the case the marker is load-bearing for: the state doc SURVIVES a compaction, so the reason signature still matches and only the marker can bring the full statement back.
    ctx_event(wl, "--post-compact")
    judge_turn(wl)
    got = wl.runj()
    assert "MARKER_REASON_ONE" in got.out, (
        "a compacted session got the bare stamp: %s" % got.out[:400]
    )

    # The signature arm on its own: no marker anywhere, but a genuinely different reason still fires, and a repeat of it does not.
    shim_judge_out(
        wl,
        {"verdict": "stop", "reason": "MARKER_REASON_TWO the gate changed", "next_action": "none"},
    )
    judge_turn(wl)
    got = wl.runj()
    assert "MARKER_REASON_TWO" in got.out, (
        "a new reason was swallowed by the latch: %s" % got.out[:400]
    )

    judge_turn(wl)
    got = wl.runj()
    assert "Stop-gate judge" in got.out, got.out[:400]
    assert "MARKER_REASON_TWO" not in got.out, (
        "the changed reason kept reprinting: %s" % got.out[:400]
    )


def test_178_the_poll_baseline_is_session_scoped_not_repo_scoped(wl):  # noqa: F811
    """v17. THE BUG this fixes: world_sig hashed the BYTES of the shared markdown, event log and requests file, so one teammate's --add broke every other session's baseline and forfeited their silent poll. Measured on the live store before the fix: 32 of 32 events in a 3-hour window were foreign, polluting 18 of 36 five-minute windows."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    wl.check("allow", "operator may answer", "178 baseline: the full stop banks the poll baseline")

    # A DIFFERENT session tracks its own work. Nothing about this session moved.
    peer = wl.cli_as("cafe1234", "--add", "cafe1234", "a teammate's own finding")
    assert peer.rc == 0, "FIXTURE BROKEN: the peer's own --add was refused: %s" % peer.out[:200]
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out.strip() == "", "a foreign event paid the full battery: %s" % got.out[:200]

    # CONTROL: the signature is not simply dead, this session's OWN store write still forfeits, which is the whole point of having a baseline.
    wl.cli("--add", "deadbeef", "my own new finding")
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out.strip(), "CONTROL: an own item went silent"
    assert "OPEN worklist item" in got.out, "CONTROL: an own item went silent: %s" % got.out[:200]


def test_178b_a_foreign_request_to_someone_else_is_invisible_to_me_it_is_not(wl):  # noqa: F811
    """The request half of the same baseline.

    THE BASH ASSERTION ON THE FOREIGN ARM COULD NOT FAIL, and the repair is the second `brief_other` below. `askid_as cafe1234 beefcafe ...` discarded its output, and `beefcafe` had never briefed in the fixture store, so the ask was REFUSED by the roster rule case 187 pins (measured: rc=1, "REFUSED: beefcafe has never briefed in this store"). Nothing was ever posted, so the
    silence that followed was the silence of an empty request log rather than of a baseline declining to forfeit. Briefing the recipient makes the request real, and the posted id is asserted rather than discarded.
    """
    wl.brief_now()
    wl.brief_other("beefcafe")
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    wl.check("allow", "operator may answer", "178b baseline")

    rid = wl.askid_as("cafe1234", "cafe1234", "beefcafe", "a question between two OTHER sessions")
    assert rid, "FIXTURE BROKEN: the foreign ask posted nothing, so the silence proves nothing"
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out.strip() == "", "a foreign request forfeited: %s" % got.out[:200]

    mine = wl.askid_as("cafe1234", "cafe1234", "deadbeef", "please rebuild the docs index")
    assert mine, "FIXTURE BROKEN: the ask addressed to this session posted nothing"
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out.strip(), "CONTROL: a request to me was swallowed"
    assert "rebuild the docs index" in got.out, (
        "CONTROL: a request to me was swallowed: %s" % got.out[:200]
    )


def test_179_the_bgwait_latch_resets_when_the_wait_ends(wl):  # noqa: F811
    """v17. THE BUG: the clock was only written inside the wait state, so leaving it froze the stamp. Re-entering an hour later found it 60 minutes old and fired the roster demand on the FIRST stop back, which is the exact thing the silent seed exists to prevent."""
    wl.brief_now()
    wl.hand_now()
    watching = bg_watch(wl, "bw9")
    wl.bg = watching
    wl.task(7, "in_progress", "waiting on the nightly")
    wl.say("answer\n\n## Remaining\n- #7 waiting on the nightly (in_progress)")
    wl.run()  # seeds the wait clock
    age_bgwait(wl)

    # The wait ENDS: the workers are gone.
    wl.bg = "[]"
    wl.newturn()
    wl.say("the watch finished\n\n## Remaining\n- #7 waiting on the nightly (in_progress)")
    wl.run()
    assert has_bgwait(wl) == "absent", "the stale clock survived the end of the wait"

    # And a LATER wait re-seeds silently instead of firing on arrival.
    wl.bg = watching
    wl.newturn()
    wl.say("started a new watch\n\n## Remaining\n- #7 waiting on the nightly (in_progress)")
    got = wl.run()
    assert "PURE BACKGROUND WAIT" not in got.out, (
        "the check-in fired on the first stop of a NEW wait: %s" % got.out[:250]
    )

    # CONTROL: the latch is not simply disabled, aged INSIDE a live wait it fires.
    age_bgwait(wl)
    wl.newturn()
    wl.say("still waiting\n\n## Remaining\n- #7 waiting on the nightly (in_progress)")
    got = wl.run()
    assert "PURE BACKGROUND WAIT" in got.out, (
        "CONTROL: the check-in never fires at all now: %s" % got.out[:250]
    )
    # v17 requirement 3: the bound is VISIBLE, so a reader can verify the latch from the message alone.
    assert "Last delivered:" in got.out, (
        "the check-in still only CLAIMS a bound: %s" % got.out[:300]
    )
    assert "Next one no earlier than" in got.out, (
        "the check-in still only CLAIMS a bound: %s" % got.out[:300]
    )


def test_180_three_no_op_wakes_collapse_the_whole_stop_to_one_line(wl):  # noqa: F811
    """v17: the quiet-wake collapse, its focus requirement, and the two controls that keep the streak honest."""
    wl.brief_now()
    wl.hand_now()
    wl.bg = bg_watch(wl, "bwq")
    wl.task(7, "in_progress", "waiting on the nightly")
    # A real deferral, so the NON-collapsed report has a guide in it. Since v18 an empty guide is silent, and the reset control below needs a full report it can actually see coming back.
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")

    def quiet_turn() -> None:
        wl.newturn()
        wl.say(
            "still waiting on the nightly\n\n## Remaining\n"
            "- #7 waiting on the nightly (in_progress)\n"
            "- the flag decision, deferred with a default"
        )

    quiet_turn()
    out1 = wl.run().out
    quiet_turn()
    out2 = wl.run().out
    quiet_turn()
    out3 = wl.run().out

    assert "CONSECUTIVE QUIET WAKES" in out3, "no collapse after three quiet wakes: %s" % out3[:300]
    assert "CONSECUTIVE QUIET WAKES" not in out1, "fired too early: %s" % out1[:120]
    assert "CONSECUTIVE QUIET WAKES" not in out2, "fired too early: %s" % out2[:120]
    assert "*/10 * * * *" in out3, "no next rung in the message: %s" % out3[:300]
    # THE FOCUS REQUIREMENT: this is the ENTIRE output. The worker roster, the guide and the advisory sections are all gone.
    assert "PURE BACKGROUND WAIT" not in out3, (
        "the collapsed stop still carried other sections: %s" % out3[:400]
    )
    assert "bwq (long watch)" not in out3, (
        "the collapsed stop still carried other sections: %s" % out3[:400]
    )
    assert "WORKLIST GUIDE" not in out3, (
        "the collapsed stop still carried other sections: %s" % out3[:400]
    )

    # CONTROL: a real event, new bytes on a worker's stream, resets the streak.
    with (wl.base / "bgout" / "bwq.output").open("a", encoding="utf-8") as handle:
        handle.write("the worker printed something new\n")
    quiet_turn()
    got = wl.run()
    assert "CONSECUTIVE QUIET WAKES" not in got.out, (
        "CONTROL: the collapse survived a real event: %s" % got.out[:300]
    )
    assert "WORKLIST GUIDE" in got.out, (
        "CONTROL: the full report did not come back: %s" % got.out[:300]
    )

    # ... and the count starts again from zero rather than resuming where it was.
    quiet_turn()
    got = wl.run()
    assert "CONSECUTIVE QUIET WAKES" not in got.out, (
        "CONTROL: the streak resumed after a real event: %s" % got.out[:300]
    )


def test_180b_a_hard_check_is_never_suppressed_by_the_quiet_collapse(wl):  # noqa: F811
    """The whole risk of collapsing output is hiding something that matters. Get a session into the collapsed state, then plant an open item: it must BLOCK."""
    wl.brief_now()
    wl.hand_now()
    wl.bg = bg_watch(wl, "bwh")
    wl.task(7, "pending", "waiting")
    got = None
    for _ in range(3):
        wl.newturn()
        wl.say("still waiting\n\n## Remaining\n- #7 waiting (pending)")
        got = wl.run()
    assert "CONSECUTIVE QUIET WAKES" in got.out, (
        "setup: never reached the collapsed state: %s" % got.out[:250]
    )

    wl.add_item("- [ ] (deadbeef) a real finding that must not be swallowed")
    wl.newturn()
    wl.say("still waiting\n\n## Remaining\n- #7 waiting (pending)")
    wl.check(
        "block",
        "OPEN worklist item",
        "an open item BLOCKS even from inside the quiet collapse",
    )


def test_180c_the_rung_ladder_escalates_and_caps():
    """The 5 to 10 to 20 to 40 to 60 ladder, its cap, and the shapes that decline to collapse at all."""
    checks = wlfix.import_wl("wl_checks")
    want = [
        ("*/5 * * * *", "*/10 * * * *"),
        ("*/10 * * * *", "*/20 * * * *"),
        ("*/20 * * * *", "*/40 * * * *"),
        ("*/40 * * * *", "0 * * * *"),
    ]
    for current, following in want:
        note = checks.quiet_wake_note([{"id": "p", "schedule": current}], 3)
        assert following in note, "rung %s did not recommend %s: %r" % (
            current,
            following,
            note[:120],
        )
    cap = checks.quiet_wake_note([{"id": "p", "schedule": "0 * * * *"}], 9)
    assert "cap" in cap, "the top rung did not cap cleanly: %r" % cap[:160]
    assert "0 * * * *" not in cap.split("cap")[1], (
        "the top rung did not cap cleanly: %r" % cap[:160]
    )
    # No recognisable poll cron means no collapse at all, so the report is never replaced by an instruction the session cannot act on.
    for crons in (
        [],
        [{"id": "p", "schedule": "*/7 * * * *"}],
        [{"id": "p", "schedule": "*/5 * * * *"}, {"id": "q", "schedule": "*/5 * * * *"}],
    ):
        assert checks.quiet_wake_note(crons, 5) == "", "collapsed on an unusable cron shape: %r" % (
            crons,
        )


def test_180d_this_sessions_own_progress_note_is_a_real_event(wl):  # noqa: F811
    """Found by the suite, not by design: with the streak keyed on item STRUCTURE alone, a session dutifully renewing its lease and posting --update notes looked quiet, and case 172's advisory got collapsed away. Doing what the liveness ladder asks is movement."""
    wl.brief_now()
    wl.hand_now()
    wl.bg = bg_watch(wl, "bwu", "the watch")
    added = wl.cli("--add", "deadbeef", "carry the CI watch to green")
    found = re.search(r"#([0-9a-f]+)", added.out)
    item = found.group(1) if found else ""
    assert item, "FIXTURE BROKEN: --add printed no id: %s" % added.out[:200]
    wl.cli("--lease", "deadbeef", item, "+60", "worker:bwu", "watching the run")

    def upd_turn() -> None:
        wl.newturn()
        wl.say("watching.\n\n## Remaining\n- #%s carry the CI watch to green (in flight)" % item)

    got = None
    for _ in range(3):
        upd_turn()
        got = wl.run()
    assert "CONSECUTIVE QUIET WAKES" in got.out, "setup: never collapsed: %s" % got.out[:250]

    wl.cli("--update", "deadbeef", item, "still watching, run pending")
    upd_turn()
    got = wl.run()
    assert "CONSECUTIVE QUIET WAKES" not in got.out, (
        "a progress note was treated as silence: %s" % got.out[:300]
    )


def test_180e_a_worker_dying_is_never_silenced_by_the_streak(wl):  # noqa: F811
    """The one change a byte-level view cannot see: the stream is identical, the event still lists the task as running, and the only difference is that the OS process is gone. If the streak counter could hide that, the collapse would be actively dangerous rather than merely quiet."""
    wl.brief_now()
    wl.hand_now()
    outdir = wl.base / "bgout"
    outdir.mkdir(parents=True, exist_ok=True)
    wl.env["WORKLIST_BG_OUTPUT_DIR"] = str(outdir)
    stream = outdir / "bwd.output"
    stream.write_text("old content\n", encoding="utf-8")
    old = time.time() - 25 * 60
    os.utime(stream, (old, old))

    probe = subprocess.Popen(["sleep", "3717171718"])
    try:
        wl.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
        wl.bg = json.dumps(
            [
                {
                    "id": "bwd",
                    "type": "shell",
                    "status": "running",
                    "description": "silent watch",
                    "command": "sleep 3717171718",
                }
            ]
        )
        wl.task(7, "pending", "thing")

        def dead_turn() -> None:
            wl.newturn()
            wl.say("answer\n\n## Remaining\n- #7 thing (pending)")

        got = None
        for _ in range(4):
            dead_turn()
            got = wl.run()
        assert "CONSECUTIVE QUIET WAKES" in got.out, (
            "setup: never collapsed with a live worker: %s" % got.out[:250]
        )
    finally:
        probe.kill()
        probe.wait()

    # The check-in window is opened too, so this case asserts BOTH halves: the streak breaks, AND the report that the break makes room for actually carries the accusation. Without the ageing it would only ever prove the first half, and a half-proof of a safety property is not one.
    age_bgwait(wl)
    dead_turn()
    got = wl.run()
    assert "CONSECUTIVE QUIET WAKES" not in got.out, (
        "a dead worker stayed hidden behind the streak: %s" % got.out[:400]
    )
    assert "<- POSSIBLY STUCK" in got.out, (
        "a dead worker stayed hidden behind the streak: %s" % got.out[:400]
    )
