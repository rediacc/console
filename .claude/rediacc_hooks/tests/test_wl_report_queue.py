"""The one-section-per-stop report queue (FIFO, priority, one-shots), the judge stamp, poll baselines, and the quiet-wake collapse.

Ported from `.claude/hooks/stop/worklist-cases/17-report-queue.sh`, one pytest function per numbered bash case. A bash block that called `setup` a second time mid-case becomes its own function here, which is what splits 173, 174 and 176 into a FIRE function and a CONTROL function each.

Operator, 2026-07-31: the allow report still emitted every fired section at once. It now releases a fixed 3 of them per stop, highest priority first and randomized within a priority class, and the tail states how many are waiting, because a silent cap reads as "that is everything", the same argument the guide's own truncation carries.
"""

from __future__ import annotations

import json
import os
import random
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


def test_173_three_of_four_sections_are_released_and_the_tail_counts_the_rest(wl):  # noqa: F811
    """FOUR class-2 sections fire, THREE are released (the fixed per-stop budget), and the tail states how many are waiting. Which three release is randomized, so the assertion is a count, robust to whichever three the lottery picks."""
    outq_fixture(wl)
    got = wl.run()
    assert outq_seen(got.out) == 3, "released %d of 4 section(s): %s" % (
        outq_seen(got.out),
        got.out[:400],
    )
    assert "(1 more report section(s) queued" in got.out, got.out[:400]


def test_173_control_the_leftover_releases_on_the_very_next_stop(wl):  # noqa: F811
    """CONTROL: the one section the budget could not fit on stop 1 is not lost, it surfaces on stop 2 with nothing left queued -- proving the cap delays rather than drops."""
    outq_fixture(wl)
    wl.run()
    wl.newturn()
    wl.say("done for now")
    got = wl.run()
    assert outq_seen(got.out) == 1, "leftover count wrong: %s" % got.out[:400]
    assert "more report section(s) queued" not in got.out, got.out[:400]


def test_174_changed_content_re_enqueues_at_a_new_seq_rather_than_keeping_its_place(wl):  # noqa: F811
    """UNIT-LEVEL: the operator's "changed content re-enqueues at its priority" is a property of `outq_add`'s bookkeeping, not of drain order (drain order is now randomized within a class, so a position-based assertion would prove nothing). Touching an already-queued key's body must bump its `seq`, which is
    what sends it to the back of its own class."""
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
        checks.outq_add("wl", "sess", qdoc, "k1", "first body", 2)
        first_seq = qdoc["outq"]["items"][0]["seq"]
        checks.outq_add("wl", "sess", qdoc, "k1", "second body", 2)
        second_seq = qdoc["outq"]["items"][0]["seq"]
        assert second_seq > first_seq, "changed content did not bump seq: %d -> %d" % (
            first_seq,
            second_seq,
        )
        assert qdoc["outq"]["items"][0]["text"] == "second body"
    finally:
        checks.S.save_state = saved_save


def test_175_the_class_0_ci_note_is_released_ahead_of_the_older_class_2_advisory(wl):  # noqa: F811
    """Priority beats the same-class lottery: an actionable CI note is rendered ahead of an older advisory queued at a lower priority, both fitting under the fixed 3-per-stop budget so the assertion is about ORDER, not exclusion.

    PLANTED DEFECT, run 2026-07-31: outq_drain's sort key was changed from (prio, seq) to (seq,). Both legs failed, the first reporting the worklist advisory in the released slot while the CI note was the one left queued, which is the inversion exactly. A priority ladder nobody has watched invert is a ladder nobody knows is wired up.
    """
    ci_setup(wl)
    # The older advisory is another session's item count, NOT its brief: ci_trouble returns "multi-session" the moment a second brief is live, and a fixture that quietly switches off the check it is racing proves nothing. Both are computed on the SAME first stop, so neither one has an
    # earlier chance to drain and get latched -- the only thing deciding which renders first is priority, which is exactly what this case measures.
    wl.add_item("- [ ] (cafe1234) their abandoned item")
    ci_rollup(
        wl,
        "PENDING",
        "[%s, %s]" % (ci_job("E2E / opensuse", "FAILURE"), ci_running("E2E / ubuntu")),
    )
    got = ci_run(wl)
    assert "retry allowlist" in got.out, "the CI note did not render: %s" % got.out[:400]
    assert "nothing open for this session" in got.out, (
        "the older advisory did not render alongside it: %s" % got.out[:400]
    )
    assert got.out.index("retry allowlist") < got.out.index("nothing open for this session"), (
        "priority did not beat the older advisory's position: %s" % got.out[:400]
    )


def test_176_a_one_shot_that_loses_its_slot_is_never_dropped_only_delayed():
    """UNIT-LEVEL: the claim is a property of the QUEUE, not of the CI/request pipeline.

    PLANTED DEFECT, 2026-07-31: outq_drain's per-entry removal was replaced with
    `q["items"][:] = []`. Leg 2 would fail: the one-shot gone for good instead of
    surviving the first drain that had no room for it.
    """
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
        for i in range(3):
            checks.outq_add("wl", "sess", qdoc, "ci-fact-%d" % i, "ci fact %d" % i, 0)
        checks.outq_add(
            "wl", "sess", qdoc, "req-escalated", "Requests ESCALATED: #cccc3333", 1, sticky=True
        )
        texts, remaining = checks.outq_drain("wl", "sess", qdoc, 3)
        assert all("ESCALATED" not in t for t in texts), (
            "leg 1: the one-shot won a slot it should have lost: %r" % texts
        )
        assert remaining == 1, "leg 1: the one-shot was not left queued: %r" % remaining

        texts2, remaining2 = checks.outq_drain("wl", "sess", qdoc, 3)
        assert any("ESCALATED" in t for t in texts2), (
            "leg 2: the one-shot was DROPPED, not delayed: %r" % texts2
        )
        assert remaining2 == 0, remaining2
    finally:
        checks.S.save_state = saved_save


def test_176_control_with_nothing_outranking_it_the_escalation_lands_on_stop_1(wl):  # noqa: F811
    """CONTROL: the same fixture with no CI trouble at all."""
    ci_setup(wl)
    wl.hand_now()
    plant_dead_request(wl, "dddd4444")
    ci_rollup(wl, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    got = ci_run(wl, message=CIMSG_176)
    assert "ESCALATED" in got.out, "the note did not land unopposed either: %s" % got.out[:400]


def test_181_priority_order_across_tiers_is_never_violated_by_the_random_tie_break():
    """However the same-priority lottery lands, a priority-3 item is never released while a priority-1 item still waits. 200 seeds, driven directly against outq_drain."""
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        for seed in range(200):
            qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
            for i in range(5):
                checks.outq_add("wl", "sess", qdoc, "hi-%d" % i, "high %d" % i, 1)
            for i in range(5):
                checks.outq_add("wl", "sess", qdoc, "lo-%d" % i, "low %d" % i, 3)
            texts, _left = checks.outq_drain("wl", "sess", qdoc, 3, rng=random.Random(seed))
            assert all("high" in t for t in texts), (
                "seed %d: a priority-3 item was released while a priority-1 item "
                "still waited: %r" % (seed, texts)
            )
    finally:
        checks.S.save_state = saved_save


def test_181_control_same_tier_selection_is_genuinely_randomized_not_a_fixed_order():
    """The other half: with more same-tier items than the budget, different seeds must produce at least two DIFFERENT releases."""
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        seen = set()
        for seed in range(50):
            qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
            for i in range(6):
                checks.outq_add("wl", "sess", qdoc, "item-%d" % i, "text %d" % i, 2)
            texts, _left = checks.outq_drain("wl", "sess", qdoc, 3, rng=random.Random(seed))
            seen.add(tuple(sorted(texts)))
        assert len(seen) > 1, (
            "50 different seeds produced the same 3-of-6 release every time: %r" % seen
        )
    finally:
        checks.S.save_state = saved_save


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
