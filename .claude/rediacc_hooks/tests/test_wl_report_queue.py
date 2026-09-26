"""The one-section-per-stop report queue (FIFO, priority, one-shots), the judge stamp, and the bgwait latch.

The poll-baseline and quiet-wake cases (178, 178b, 180-180e) and the request-escalation control of 176 were removed with cross-session messaging on 2026-09-24.

Ported from `.claude/hooks/stop/worklist-cases/17-report-queue.sh`, one pytest function per numbered bash case. A bash block that called `setup` a second time mid-case becomes its own function here, which is what splits 173, 174 and 176 into a FIRE function and a CONTROL function each.

Operator, 2026-07-31: the allow report still emitted every fired section at once. It now releases a fixed 3 of them per stop, highest priority first and randomized within a priority class, and the tail states how many are waiting, because a silent cap reads as "that is everything", the same argument the guide's own truncation carries.
"""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_rollup, ci_run, ci_running, ci_setup
from rediacc_hooks.tests.test_wl_guide_and_deferrals import shim_judge_out
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# The four class-2 sections the outq fixture holds on one stop. PLANTED in the queue since 2026-09-24: three of the four producers that used to fire here (`agent-peers`, `others`, `others-items`) were deleted with the peer listing (agent/plans/PLAN-stop-hook-continuity.md P0.3), and what these cases measure is the drain -- its budget, its tail, its priority order -- not any one producer.
OUTQ_SECTIONS = (
    "FIXTURE SECTION ONE",
    "FIXTURE SECTION TWO",
    "FIXTURE SECTION THREE",
    "FIXTURE SECTION FOUR",
)


def stale_peer_transcript(fix) -> None:
    """An orphan needs a dead owner: a transcript for cafe1234 older than WORKLIST_DEAD_HOURS but younger than WORKLIST_ARCHIVE_HOURS."""
    path = fix.base / "cafe1234.jsonl"
    path.write_text("", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(path, (old, old))


def outq_fixture(fix) -> None:
    """Four class-2 sections queued for one clean stop."""
    fix.say("done for now")
    fix.brief_now()
    fix.hand_now()
    fix.run()  # builds the state document the queue lives in
    path = fix.stem(".state-deadbeef.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["outq"] = {
        "seq": 4,
        "shown": {},
        "items": [
            {
                "key": "fixture-%d" % i,
                "prio": 2,
                "sticky": False,
                "sig": "%012x" % i,
                "text": "%s\n  body line" % label,
                "at": "2026-09-24T00:00:00Z",
                "seq": i,
            }
            for i, label in enumerate(OUTQ_SECTIONS, 1)
        ],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    fix.newturn()
    fix.say("done for now")


def outq_seen(out: str) -> int:
    """How many of the four section headers are present."""
    return sum(1 for needle in OUTQ_SECTIONS if needle in out)


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


def test_174_changed_content_re_enqueues_at_a_new_seq_rather_than_keeping_its_place(wl):  # noqa: F811, ARG001
    """UNIT-LEVEL: the operator's "changed content re-enqueues at its priority" is a property of `outq_add`'s bookkeeping, not of drain order (drain order is now randomized within a class, so a position-based assertion would prove nothing). Touching an already-queued key's body must bump its `seq`, which is
    what sends it to the back of its own class."""
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        qdoc: dict[str, Any] = {"outq": {"items": [], "shown": {}, "seq": 0}}
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
    # An ORPHANED item (a dead owner's open item) is the older class-2 advisory: `ci_run` carries no transcript path to derive the projects directory from, so it is pinned to where the stale transcript lives.
    stale_peer_transcript(wl)
    wl.env["WORKLIST_PROJECTS_DIR"] = str(wl.base)
    ci_rollup(
        wl,
        "PENDING",
        "[%s, %s]" % (ci_job("E2E / opensuse", "FAILURE"), ci_running("E2E / ubuntu")),
    )
    got = ci_run(wl)
    assert "retry allowlist" in got.out, "the CI note did not render: %s" % got.out[:400]
    assert "ORPHANED item(s)" in got.out, (
        "the older advisory did not render alongside it: %s" % got.out[:400]
    )
    assert got.out.index("retry allowlist") < got.out.index("ORPHANED item(s)"), (
        "priority did not beat the older advisory's position: %s" % got.out[:400]
    )


def test_176_a_one_shot_that_loses_its_slot_is_never_dropped_only_delayed():
    """UNIT-LEVEL: the claim is a property of the QUEUE, not of any producer pipeline.

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
            "wl", "sess", qdoc, "archived", "Worklist: ONE-SHOT archived #cccc3333", 1, sticky=True
        )
        texts, remaining = checks.outq_drain("wl", "sess", qdoc, 3)
        assert all("ONE-SHOT" not in t for t in texts), (
            "leg 1: the one-shot won a slot it should have lost: %r" % texts
        )
        assert remaining == 1, "leg 1: the one-shot was not left queued: %r" % remaining

        texts2, remaining2 = checks.outq_drain("wl", "sess", qdoc, 3)
        assert any("ONE-SHOT" in t for t in texts2), (
            "leg 2: the one-shot was DROPPED, not delayed: %r" % texts2
        )
        assert remaining2 == 0, remaining2
    finally:
        checks.S.save_state = saved_save


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
    # This session's one post-compact stop-hook retro is recorded as already done: a first compaction orders it, and its tracking item would lead the next stop with open-items (agent/plans/PLAN-stop-hook-retro-20260924.md R20260924.12), which is not what this case measures.
    retro_ledger = wl.proj / "agent" / "ledgers" / "stop-hook-retros.jsonl"
    retro_ledger.parent.mkdir(parents=True, exist_ok=True)
    done_retro = {"session": "deadbeef", "band": "post-compact", "item": "0000d0ne"}
    retro_ledger.write_text(
        "".join(
            json.dumps(dict(done_retro, ev=ev)) + "\n" for ev in ("ordered", "tracked", "saved")
        ),
        encoding="utf-8",
    )
    # The lead's own compaction, in the shape R20260924.16 attributes: its boundary in the lead transcript and the event naming that transcript. A PostCompact nobody can attribute leaves ctx_fresh alone.
    wl.append_transcript(
        {
            "type": "system",
            "subtype": "compact_boundary",
            "isSidechain": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
    )
    wl.python(
        ["--post-compact"],
        stdin=json.dumps(
            {"session_id": wl.sid, "cwd": str(wl.proj), "transcript_path": str(wl.transcript)}
        ),
    )
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
