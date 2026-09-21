"""The store-derived guide on every stop, `--defer` justification, aged `[?]` demands, and the sitting-on-a-watch backlog forcing.

Ported from `.claude/hooks/stop/worklist-cases/11-guide-and-deferrals.sh`, one pytest function per numbered bash case, and one more wherever a bash block called `setup` again mid-case.

THE OPERATOR'S ASK behind case 146: "--list should be used always on stop hook to output enforced guided instructions". The defect it fixes: v10 stamped every item and the hand-authored Remaining prose never read the store.

THE OPERATOR'S EVIDENCE behind cases 147 and up: 30+ deferrals sat 117 minutes while the session stopped three times with "the run is healthy"; one deferral requested a feature that had ALREADY been built. Every FIRE case is paired with a SILENT control differing by one planted fact, and every demand's solo exit is proven to reach an allowed stop (the anti-deadlock property).
"""

from __future__ import annotations

import json
import re
import stat
import time
from typing import TYPE_CHECKING

from rediacc_hooks.tests.wlfix import wl  # noqa: F401

if TYPE_CHECKING:
    from rediacc_hooks.tests import wlfix


def stamp(minutes_ago: float = 0.0, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    """A UTC stamp `minutes_ago` in the past, in the format the bash `date -u -d` calls produced."""
    return time.strftime(fmt, time.gmtime(time.time() - minutes_ago * 60))


def plant_event(fix, payload: dict) -> None:
    """Append one raw event to the legacy log, which is how every fixture in this file plants store rows."""
    with fix.events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def added_id(result: wlfix.Result) -> str:
    """The item id `--add` printed."""
    found = re.search(r"^added #([0-9a-f]+)", result.out, re.MULTILINE)
    assert found, "--add printed no item id: %r" % result.out[:200]
    return found.group(1)


def shim_judge_out(fix, structured_output: dict) -> None:
    """A canned `claude` serving that exact structured output, plus a CALL COUNTER.

    LOCAL to this module rather than in wlfix, because `wl.shim_judge` hard-codes the stop verdict and writes no counter, and case 151's whole subject is that an untouched item is not re-audited: it needs the number of times the judge was paid.
    """
    payload = {"is_error": False, "structured_output": structured_output}
    body = "#!/bin/bash\necho x >> %s\necho %s\n" % (
        json.dumps(str(fix.base / "judgecalls")),
        json.dumps(json.dumps(payload)),
    )
    script = fix.base / "binonly" / "claude"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def judge_calls(fix) -> int:
    """How many times the shim was invoked."""
    path = fix.base / "judgecalls"
    if not path.is_file():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def test_146a_an_allow_stop_carries_the_guide_with_state_correct_verbs(wl):  # noqa: F811
    """v11: the store-derived GUIDE rides every full stop, bounded. A `[>]` gets `--update`, a fresh `[?]` gets its window."""
    wl.brief_now()
    wl.hand_now()
    now = stamp()
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "cccc1111",
            "at": now,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "delegated build",
        },
    )
    plant_event(
        wl,
        {
            "ev": "lease",
            "id": "cccc1111",
            "at": now,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "cccc1112",
            "at": now,
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "ship the flag? DEFAULT: ship it",
        },
    )
    wl.bg = json.dumps(
        [
            {
                "id": "bw1",
                "type": "shell",
                "status": "running",
                "description": "watch",
                "command": "sleep 999",
            }
        ]
    )
    wl.say("answer\n\n## Remaining\n- the delegated build and the flag question")
    got = wl.run()
    assert got.decision == "allow", got.out[:300]
    assert "WORKLIST GUIDE" in got.out, got.out[:300]
    assert "--update deadbeef cccc1111" in got.out, got.out[:300]
    assert "DEFAULT executes in" in got.out, got.out[:300]


def test_146b_a_focus_off_block_carries_the_guide_and_the_focused_one_drops_it(wl):  # noqa: F811
    """(b) the guide rides the dump-all block reason and an open item gets `--tick`; (b2) v13's FOCUSED block deliberately drops the guide (operator, 2026-07-31, superseding the v11 every-full-stop mandate) and the noise reduction IS the feature, so the focused variant is asserted guide-FREE while it still names the open item."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) wire the perf fixture")
    wl.say("answer\n\n## Remaining\n- the perf fixture")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    assert '"decision": "block"' in got.out, got.out[:300]
    assert "WORKLIST GUIDE" in got.out, got.out[:300]
    assert "--tick deadbeef" in got.out, got.out[:300]
    assert "do it, then" in got.out, got.out[:300]

    focused = wl.run()
    assert '"decision": "block"' in focused.out, focused.out[:300]
    assert "WORKLIST GUIDE" not in focused.out, (
        "the focused block carried the guide: %s" % focused.out[:300]
    )
    assert "OPEN worklist item" in focused.out, focused.out[:300]


def test_146c_zero_actionable_is_silent_and_one_real_item_brings_the_guide_back(wl):  # noqa: F811
    """(c) ZERO actionable is SILENT since v18.

    This case used to assert the opposite ("a short honest line, never ambiguous silence") and the operator overruled it (2026-08-04, quoting a stop whose whole output was that line plus the wakeup times): "silent when there is nothing to act on... let's go for efficient ai context usage". The ambiguity the old line guarded against is also gone, because the poll fast path already
    exits silently many times an hour, so zero bytes is the session's familiar "nothing to do".
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    got = wl.run()
    wl.check_quiet("no actionable items in the store", "the empty-guide line survived", result=got)
    # This fixture is NOT silent, and it should not be: a repo with no request traffic at all trips the poll-backoff advisory, which is a real thing to act on. Pinning that here keeps the zero-byte case below honest: it proves the silence there comes from having nothing to say, not from a muted report.
    assert "INBOX HAS BEEN QUIET" in got.out, (
        "the backoff advisory was swallowed with the guide: %s" % got.out[:260]
    )

    # NOW the zero-byte case: one fresh request in the log (between two OTHER sessions, so it never reaches this inbox) resets the quiet clock and silences the backoff advisory, leaving a stop with genuinely nothing to report.
    wl.askid_as("cafe1234", "cafe1234", "beefcafe", "a question between two other sessions")
    wl.newturn()
    wl.say("all done")
    silent = wl.run()
    assert silent.rc == 0, "the nothing-to-report stop was not silent (rc=%d): %s" % (
        silent.rc,
        silent.out[:260],
    )
    assert not silent.out, "the nothing-to-report stop was not silent (rc=%d): %s" % (
        silent.rc,
        silent.out[:260],
    )

    # CONTROL, so the silence above is the guide standing down and not the battery being skipped: the SAME fixture plus one real item speaks up immediately.
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.newturn()
    wl.say("all done\n\n## Remaining\n- the flag decision, deferred with a default")
    back = wl.run()
    assert "WORKLIST GUIDE" in back.out, (
        "CONTROL: the guide stayed silent with a real item: %s" % back.out[:260]
    )
    assert "keep the flag?" in back.out, back.out[:260]


def test_146d_truncation_is_loud_twelve_of_fifteen_and_the_three_named(wl):  # noqa: F811
    """(d) 15 open items show 12 and SAY 3 were held back."""
    wl.brief_now()
    wl.hand_now()
    for index in range(1, 16):
        wl.add_item("- [ ] (deadbeef) backlog item number %d" % index)
    wl.say("answer\n\n## Remaining\n- fifteen backlog items")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    # Occurrences, not lines: the hook's output is ONE JSON line, so a line count reads 1.
    shown = got.out.count("do it, then --tick")
    assert shown == 12, "silent or wrong truncation: shown=%d out=%s" % (shown, got.out[:300])
    assert "+3 more actionable" in got.out, got.out[:300]
    assert "HELD BACK by the 12-line cap" in got.out, got.out[:300]


def test_146e_each_broken_shape_carries_its_own_exit(wl):  # noqa: F811
    """(e) VERB-STATE MATCH for the remaining shapes: undefaulted `[?]`, expired window, dead lease, each with its own exit spelled out."""
    wl.brief_now()
    wl.hand_now()
    old = stamp(130)
    past = stamp(5, "%Y-%m-%dT%H:%MZ")
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "cccc2221",
            "at": old,
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "aged choice DEFAULT: option A",
        },
    )
    wl.add_item("- [?] (deadbeef) an undefaulted question")
    wl.add_item("- [>] (deadbeef) until:%s stale delegation" % past)
    wl.say("answer\n\n## Remaining\n- three differently broken items")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    for needle in (
        "execute its DEFAULT now",
        "--defer deadbeef",
        "LEASE DEAD",
        "re-lease: --lease deadbeef",
    ):
        assert needle in got.out, "verb-state mismatch, MISSING %r: %s" % (needle, got.out[:400])


def test_146f_list_open_is_the_same_slice_and_the_full_dump_keeps_history(wl):  # noqa: F811
    """(f) `--list --open` is the SAME slice from the CLI, and the full dump keeps the `[x]` history the slice excludes."""
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.add_item("- [x] (deadbeef) finished thing, exit 0")
    open_slice = wl.cli("--list", "--open", "deadbeef").out
    full = wl.cli("--list").out
    assert "--tick deadbeef" in open_slice, open_slice[:200]
    assert "open thing" in open_slice, open_slice[:200]
    assert "finished thing" not in open_slice, "the slice carried history: %s" % open_slice[:200]
    assert "finished thing" in full, "plain --list lost the history: %s" % full[:200]


def test_146f2_the_cli_slice_is_uncapped(wl):  # noqa: F811
    """(f2) GUIDE_TRUNCATED (case 146d) tells the reader to run this exact command "for the full slice", and until the full= flag the command re-rendered the same 12 rows: advice that looped back onto itself.

    15 open items must all appear here, with NO truncation footer. The 12-line cap stays on the Stop path, which case 146d pins; this case and that one are each other's control, so a regression that lifts the cap everywhere (or restores it here) fails one of the two.
    """
    for index in range(1, 16):
        wl.add_item("- [ ] (deadbeef) uncapped backlog item number %d" % index)
    open_slice = wl.cli("--list", "--open", "deadbeef").out
    shown = len([line for line in open_slice.splitlines() if "do it, then --tick" in line])
    missing = [
        index
        for index in range(1, 16)
        if "uncapped backlog item number %d" % index not in open_slice
    ]
    assert shown == 15, "CLI slice still capped (shown=%d): %s" % (shown, open_slice[:300])
    assert not missing, "CLI slice dropped items %s: %s" % (missing, open_slice[:300])
    assert "HELD BACK" not in open_slice, open_slice[:300]


def test_147_defer_refuses_a_deferral_that_cannot_justify_its_seat(wl):  # noqa: F811
    """v12: deferral justification, with WHY and HOW as real store fields rather than prose."""
    nid = added_id(wl.cli("--add", "deadbeef", "choose the flag default"))

    bare = wl.cli("--defer", "deadbeef", nid, "keep the flag? DEFAULT: keep it")
    both = bare.out + bare.err
    assert bare.rc != 0, "unjustified --defer was accepted: %s" % both[:200]
    assert "WHY:" in both, both[:200]
    assert "HOW:" in both, both[:200]
    assert '"ev":"state"' not in wl.wl_events(), (
        "a refused defer still wrote an event: %s" % wl.wl_events()[-300:]
    )

    vague = wl.cli(
        "--defer",
        "deadbeef",
        nid,
        "keep the flag? DEFAULT: keep it WHY: did not get to it yet HOW: revisit next week",
    )
    assert vague.rc != 0, "the vague-why gate did not fire: %s" % (vague.out + vague.err)[:200]
    assert "avoidance" in vague.out + vague.err, (vague.out + vague.err)[:200]

    good = wl.cli(
        "--defer",
        "deadbeef",
        nid,
        "keep the flag? DEFAULT: keep it WHY: flipping it changes billing for live users, an "
        "operator-only call HOW: operator confirms, or the DEFAULT keeps it TRIED: read the "
        "pricing doc BLOCKED_ON: operator",
    )
    events = wl.wl_events()
    assert good.rc == 0, "justified defer refused: %s" % (good.out + good.err)[:200]
    assert '"j":{' in events, events[-300:]
    assert '"why":"flipping it changes billing' in events, events[-300:]
    assert '"blocked_on":"operator"' in events, events[-300:]


def test_148_an_aged_deferral_with_no_justification_is_demanded(wl):  # noqa: F811
    """An AGED `[?]` with no justification is demanded, bounded, and THE HONEST-ANSWER EXIT is the anti-deadlock property: re-deferring with a WHY and a HOW is completable alone in one turn, and it reaches an allowed stop."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "dddd1111",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "quarantine the leg? DEFAULT: quarantine it",
        },
    )
    wl.say("answer\n\n## Remaining\n- the quarantine decision, deferred")
    wl.check("block", "NO justification on record", "a 60-minute [?] with no WHY/HOW blocks")

    wl.cli(
        "--defer",
        "deadbeef",
        "dddd1111",
        "quarantine the leg? DEFAULT: quarantine it WHY: only the operator can accept the "
        "coverage loss it causes HOW: operator approves, or the DEFAULT quarantines it",
    )
    wl.newturn()
    wl.say(
        "justified the deferral\n\n## Remaining\n- the quarantine decision, deferred with its justification"
    )
    wl.check(
        "allow", "operator may answer", "answering the WHY/HOW honestly reaches an allowed stop"
    )


def test_148_control_the_same_age_with_a_justification_never_fires(wl):  # noqa: F811
    """CONTROL: one planted fact apart from the case above, and it must stay quiet."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "dddd1112",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "price the tier? DEFAULT: keep the price WHY: pricing is an operator-only call "
            "with revenue stakes HOW: operator picks a number",
        },
    )
    wl.say("answer\n\n## Remaining\n- the pricing decision, deferred with its justification")
    got = wl.run()
    assert got.decision == "allow", "justified deferral was nagged: %s" % got.out[:260]
    assert "NO justification on record" not in got.out, got.out[:260]


def test_148_drain_cap_five_unjustified_arrive_three_at_a_time(wl):  # noqa: F811
    """DRAIN CAP: five aged unjustified deferrals arrive three at a time, never as a wall."""
    wl.brief_now()
    wl.hand_now()
    old = stamp(60)
    for index in range(1, 6):
        plant_event(
            wl,
            {
                "ev": "add",
                "id": "dddd222%d" % index,
                "at": old,
                "by": "deadbeef",
                "s": "?",
                "o": "deadbeef",
                "t": "aged bare question %d DEFAULT: option A" % index,
            },
        )
    wl.say("answer\n\n## Remaining\n- five bare deferrals")
    got = wl.run()
    assert "5 deferred item(s) have sat" in got.out, (
        "justification drain cap wrong: %s" % got.out[:300]
    )
    assert "and 2 more, held back" in got.out, got.out[:300]


def test_149_the_centrepiece_sitting_on_a_ci_watch_forces_the_backlog(wl):  # noqa: F811
    """A CI watch as the ONLY in-flight work demands the aged backlog by id, names its next verb, and doing the demanded work reaches an allowed stop with the same watch still running."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "eeee1111",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator "
            "can accept the storage cost HOW: operator confirms the budget",
        },
    )
    wl.bg = json.dumps(
        [
            {
                "id": "cw1",
                "type": "shell",
                "status": "running",
                "command": ".ci/scripts/ci/ci-trace.py --wait",
                "description": "watch CI run",
            }
        ]
    )
    wl.say("the run is healthy, nothing to do\n\n## Remaining\n- the backfill decision, deferred")
    wl.check(
        "block", "YOU ARE SITTING ON CI", "a CI watch as the only in-flight work forces the backlog"
    )

    named = wl.run()
    assert "#eeee1111" in named.out, "no id in the CI-waiting block: %s" % named.out[:300]
    assert "NEXT:" in named.out, "no next verb in the CI-waiting block: %s" % named.out[:300]

    # ANTI-DEADLOCK: doing the demanded work reaches an allowed stop, with the same watch still running.
    wl.cli("--tick", "deadbeef", "eeee1111", "backfilled, exit 0")
    wl.newturn()
    wl.say(
        "executed the backfill default while the run finished\n\n## Remaining\n"
        "nothing open; the CI watch is still running"
    )
    wl.check("allow", "", "doing the demanded work reaches an allowed stop under the same watch")


def test_149_control_a_non_watch_worker_beside_the_watch_means_not_sitting(wl):  # noqa: F811
    """CONTROL 1, one planted fact: real delegated work runs beside the watch."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "eeee2221",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator "
            "can accept the storage cost HOW: operator confirms the budget",
        },
    )
    wl.bg = json.dumps(
        [
            {
                "id": "cw1",
                "type": "shell",
                "status": "running",
                "command": ".ci/scripts/ci/ci-trace.py --wait",
                "description": "watch CI run",
            },
            {
                "id": "bw2",
                "type": "shell",
                "status": "running",
                "command": "bash scripts/build-embed.sh",
                "description": "rebuild embed assets",
            },
        ]
    )
    wl.say(
        "watching the run while the embed rebuild runs\n\n## Remaining\n- the backfill decision, deferred"
    )
    got = wl.run()
    assert "SITTING ON CI" not in got.out, (
        "the force fired despite real delegated work: %s" % got.out[:260]
    )


def test_149_control_a_fresh_deferral_is_not_demanded(wl):  # noqa: F811
    """CONTROL 2, one planted fact: the backlog is fresh, so re-justifying is a real exit and there is nothing to force."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "eeee3331",
            "at": stamp(),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "backfill the audit log? DEFAULT: backfill last 30 days WHY: only the operator "
            "can accept the storage cost HOW: operator confirms the budget",
        },
    )
    wl.bg = json.dumps(
        [
            {
                "id": "cw1",
                "type": "shell",
                "status": "running",
                "command": ".ci/scripts/ci/ci-trace.py --wait",
                "description": "watch CI run",
            }
        ]
    )
    wl.say("watching the run\n\n## Remaining\n- the backfill decision, freshly deferred")
    got = wl.run()
    assert "SITTING ON CI" not in got.out, "the force fired on a fresh backlog: %s" % got.out[:260]


def test_150_the_judge_audits_sitting_justifications_and_do_now_reopens_the_item(wl):  # noqa: F811
    """A `do_now` audit verdict blocks with the judge's order, the rejected deferral is REOPENED as ordinary open work, and doing that work reaches an allowed stop."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "ffff1111",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "quarantine the flaky leg? DEFAULT: quarantine it WHY: only the operator can "
            "accept the coverage loss HOW: operator approves the quarantine",
        },
    )
    wl.say("answer\n\n## Remaining\n- the quarantine decision, deferred with its justification")
    shim_judge_out(
        wl,
        {
            "verdict": "stop",
            "reason": "ok",
            "next_action": "none",
            "defer_audit": [
                {
                    "id": "ffff1111",
                    "verdict": "do_now",
                    "reason": "the flake stats are in the tree",
                    "order": "read the flake stats and quarantine it yourself",
                }
            ],
        },
    )
    wl.checkj(
        "block", "DEFERRAL AUDIT REJECTED", "a do_now audit verdict blocks with the judge's order"
    )

    listed = wl.cli("--list").out
    assert "- [ ]" in listed, "no reopened item in the store: %s" % listed[:260]
    assert "REOPENED by the stop-gate judge" in listed, listed[:260]

    # ANTI-DEADLOCK: doing the reopened work reaches an allowed stop.
    wl.cli("--tick", "deadbeef", "ffff1111", "quarantined, exit 0")
    wl.newturn()
    wl.say("quarantined the leg as ordered\n\n## Remaining\nnothing")
    wl.checkj("allow", "", "ticking the reopened item with evidence reaches an allowed stop")


def test_151_a_valid_audit_verdict_is_banked_and_an_untouched_item_is_asked_once(wl):  # noqa: F811
    """The `[?]` item is also an operator-only mail candidate, so the unconfigured email channel queues a class-1 note ahead of the audit note. Both are one-shots and neither is lost; this case asserts the audit note is produced, so it drains wide rather than waiting a stop for its turn."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "ffff2221",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "rotate the org key? DEFAULT: keep the schedule WHY: rotation locks every "
            "teammate out for an hour, an operator-only call HOW: operator names the window",
        },
    )
    wl.say("answer\n\n## Remaining\n- the rotation decision, deferred with its justification")
    shim_judge_out(
        wl,
        {
            "verdict": "stop",
            "reason": "genuinely operator-only",
            "next_action": "none",
            "defer_audit": [
                {
                    "id": "ffff2221",
                    "verdict": "valid",
                    "reason": "locking teammates out is a real operator-only stake",
                    "order": "",
                }
            ],
        },
    )
    wl.checkj(
        "allow", "survived interrogation", "a valid verdict allows and reports the banked reason"
    )
    first = judge_calls(wl)
    wl.checkj("allow", "", "the untouched item is not re-audited (banked per stamp)")
    second = judge_calls(wl)
    assert first == 1, "judge was re-paid for an untouched item: calls=%d then %d" % (first, second)
    assert second == 1, "judge was re-paid for an untouched item: calls=%d then %d" % (
        first,
        second,
    )


def test_151_a_requested_audit_with_no_answer_fails_closed(wl):  # noqa: F811
    """FAIL CLOSED: an audit that was requested and not answered is a judge error."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "ffff3331",
            "at": stamp(60),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "rotate the org key? DEFAULT: keep the schedule WHY: rotation locks every "
            "teammate out for an hour, an operator-only call HOW: operator names the window",
        },
    )
    wl.say("answer\n\n## Remaining\n- the rotation decision, deferred with its justification")
    shim_judge_out(wl, {"verdict": "stop", "reason": "ok", "next_action": "none"})
    wl.checkj(
        "block",
        "no usable defer_audit",
        "a requested audit with no defer_audit answer fails closed",
    )


def test_152_the_silent_poll_forfeits_to_the_justification_demand(wl):  # noqa: F811
    """A poll stop cannot slip past an unjustified aged `[?]`."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "dddd7771",
            "at": stamp(40),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "bare aged question DEFAULT: option A",
        },
    )
    wl.say("answer\n\n## Remaining\n- the bare deferral")
    wl.check(
        "block",
        "NO justification on record",
        "the full stop demands the justification (and banks the poll baseline)",
    )
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out, "the poll fast path swallowed the justification demand"
    assert "NO justification on record" in got.out, got.out[:200]


def test_152_control_the_same_age_with_a_justification_keeps_the_silent_poll(wl):  # noqa: F811
    """CONTROL, one planted fact: the same item, justified, and the poll stays silent."""
    wl.brief_now()
    wl.hand_now()
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "dddd7772",
            "at": stamp(40),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "aged question DEFAULT: option A WHY: only the operator can weigh the trade HOW: operator answers",
        },
    )
    wl.say("answer\n\n## Remaining\n- the justified deferral")
    wl.check("allow", "", "baseline stop allows")
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.rc == 0, "a justified deferral forfeited the fast path: rc=%d %r" % (
        got.rc,
        got.out[:160],
    )
    assert not got.out, "a justified deferral forfeited the fast path: rc=%d %r" % (
        got.rc,
        got.out[:160],
    )


def test_153_a_latched_ladder_rung_must_not_forfeit_the_silent_poll_forever(wl):  # noqa: F811
    """WHAT BROKE. The ladder is latched (fire_once records each rung against the subject's stamp), but poll_fast_path forfeited on RAW AGE and never consulted that latch. So the two disagreed: the report went silent after firing once while the forfeit kept firing on every poll.

    Measured 2026-07-30: task #20 sat in_progress for 298 minutes, legitimately, waiting on an operator decision and a running agent. Its rung had long since fired, yet every five-minute inbox poll paid the full battery and demanded a full report, with no way to discharge it short of finishing or abandoning a task that was not this session's to finish. That is the "a gate that
    cannot be satisfied deadlocks the session" trap the v10 brief warned about, reintroduced by a threshold comparison that looked harmless.

    The task must exist BEFORE the baseline stop banks the poll baseline: task statuses are part of the world signature, so creating it afterwards moves the signature and a DIFFERENT check fires. That fixture bug cost a round here, and it is worth stating because it makes a real fix look broken.
    """
    wl.brief_now()
    wl.hand_now()
    wl.task(20, "in_progress", "wave B acceptance, blocked on the operator")
    wl.say("answer\n\n## Remaining\n| #20 | wave B acceptance | ongoing, the operator |")
    wl.check("allow", "", "baseline stop allows")

    # Its rung ALREADY fired against this exact stamp. Written straight into the state doc (which is NOT part of the world signature, so this is safe after the baseline) because the point is the latch, not how it got set.
    doc_path = wl.stem(".state-deadbeef.json")
    doc = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else {}
    fired_at = "2026-07-30T06:29:37Z"
    doc.setdefault("tasks_seen", {})["20"] = {"status": "in_progress", "since": fired_at}
    doc.setdefault("ladder", {})["task:20"] = {"investigate": fired_at, "resolve": fired_at}
    doc_path.write_text(json.dumps(doc), encoding="utf-8")

    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.rc == 0, "a latched rung still forfeited the fast path: rc=%d %r" % (
        got.rc,
        got.out[:200],
    )
    assert not got.out, "a latched rung still forfeited the fast path: rc=%d %r" % (
        got.rc,
        got.out[:200],
    )


def test_153_control_an_unfired_rung_at_the_same_age_still_forfeits(wl):  # noqa: F811
    """CONTROL, and it is the one that matters: the SAME task at the SAME age with the rung NOT yet fired must still forfeit. Without this the fix could be a blanket "never forfeit on tasks" and the suite would not notice."""
    wl.brief_now()
    wl.hand_now()
    wl.task(20, "in_progress", "wave B acceptance, blocked on the operator")
    wl.say("answer\n\n## Remaining\n| #20 | wave B acceptance | ongoing, the operator |")
    wl.check("allow", "", "baseline stop allows")

    doc_path = wl.stem(".state-deadbeef.json")
    doc = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else {}
    doc.setdefault("tasks_seen", {})["20"] = {
        "status": "in_progress",
        "since": "2026-07-30T06:29:37Z",
    }
    doc["ladder"] = {}  # never fired
    doc_path.write_text(json.dumps(doc), encoding="utf-8")

    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out, "an unfired blocking rung was swallowed by the fast path"
