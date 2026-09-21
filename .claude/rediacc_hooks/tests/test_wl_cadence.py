"""Door-parked wave reporting, the session-scoped block counter, and the answer-then-stand-down cadence with its guards, plus the idle-stall and pending-ask gates.

Ported from `.claude/hooks/stop/worklist-cases/21-cadence.sh`, one pytest function per bash case, same assertions in the same order against the same hook invocation. A bash leg that continued its predecessor's world with no fresh `setup` stays inside its predecessor's function; a leg calling `setup` again becomes a new function, which is why bash case 223j becomes seven.

THE BASH FILE LABELS TWO CASES TWICE. `223h` names both the declarative-close control near the top of the pending-ask group and the refusal-ledger case at the bottom, and `223i` names both the standalone announcement that still fires and the empty-ledger control. The numbers are kept below and the names disambiguate by what each one asserts.

`clfile`, `cldeliver`, `additem` and `pyprobe` are IMPORTED from the module 19-checklists.sh became, since the bash suite sourced its case files in order and had exactly one definition of each.
"""

from __future__ import annotations

import datetime
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_checklists import additem, cldeliver, clfile, pyprobe
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# --- the checklist bodies the cases plant -----------------------------------

CL_DEMO_SECRETS = """# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: mint the production secrets
"""

CL_DEMO_SECRETS_TICKED = CL_DEMO_SECRETS.replace("- [ ] w1 Wave A: mint", "- [x] w1 Wave A: mint")

CL_DEMO_WIRE = """# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
"""

CL_DEMO_HANDED = """# Handoff checklist: demo
Status: executing
Owner: deadbeef

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: the thing this session was handed
"""

# --- the messages the cadence cases say -------------------------------------

# A reported-but-unfixed finding: a rotating violation with NOTHING actionable behind it.
FNF = "- Agent finding I did not fix: the dead symlink under .ci"

CADENCE_ANSWER = "answer\n\n%s\n\n## Remaining\n- nothing outstanding" % FNF
CADENCE_ANSWERED = (
    "I have now answered the demand\n\n%s\n\n## Remaining\n- nothing outstanding" % FNF
)
CADENCE_URGENT = (
    "answered, and now something urgent is also true\n\n%s\n\n## Remaining\n- nothing outstanding"
    % FNF
)
CADENCE_FIXED = "all done, and I fixed the symlink rather than reporting it\n\n## Remaining\n- nothing outstanding"
CADENCE_FRESH = "a fresh finding turned up\n\n%s\n\n## Remaining\n- nothing outstanding" % FNF

# PA_MSG IS DEFINED ONCE AND USED BY 223, 223b AND 223c VERBATIM. That is the anti-vacuity floor of this group: 223 blocks and 223b is silent, and the ONLY difference between them is the fixture state (one tool_use record). If the two messages differed as well, the pair would prove nothing about the detector: it would be consistent with a gate that simply matched different prose.
PA_MSG = """Wave 3 landed and the suite is 810/0.

## Remaining
- nothing outstanding

Two questions for you before I pick the branch."""

PROBE_222J = r"""
import os
import sys

sys.path.insert(0, os.environ["HOOKDIR"])
import wl_checks


class Boom:
    @property
    def items(self):
        raise RuntimeError("unreadable store")


assert wl_checks.closed_sig(Boom(), "deadbeef") == ""
assert wl_checks.idle_stall({}, Boom(), "deadbeef", ["x"], [], []) == (False, "no baseline yet")
assert wl_checks.unblocked_claims(None) == []
assert wl_checks.unblocked_claims("## Remaining\n- blocked on: nothing") != []
print("OK")
"""

PROBE_223G = r"""
import os
import sys

sys.path.insert(0, os.environ["HOOKDIR"])
import wl_admit


class Boom:
    @property
    def items(self):
        raise RuntimeError("unreadable store")


assert wl_admit.defer_sig(Boom(), "deadbeef") == ""
assert wl_admit.pending_ask(None, None, False) == (False, "")
assert wl_admit.pending_ask("", [], False) == (False, "")
assert wl_admit.turn_tools("/does/not/exist") == ([], "")
assert wl_admit.ask_refusals("/does/not/exist", "deadbeef")[0] == 0
# The three conditions, each one alone able to keep it quiet.
_msg = "done\n\nTwo questions for you before I pick the branch."
assert wl_admit.pending_ask(_msg, [], False)[0]
assert not wl_admit.pending_ask(_msg, ["AskUserQuestion"], False)[0]
assert not wl_admit.pending_ask(_msg, [], True)[0]
# A restated deferral carries its DEFAULT and is not an announcement.
assert not wl_admit.pending_ask("- [?] which branch? DEFAULT: the open one", [], False)[0]
# A tool_result user record is NOT the operator speaking, so it must not reset the tool window,
# which is the whole reason this does not reuse transcript_tail.
assert not wl_admit._is_operator_turn(
    {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}
)
assert not wl_admit._is_operator_turn({"type": "user", "isMeta": True, "message": {"content": "hi"}})
assert wl_admit._is_operator_turn({"type": "user", "message": {"content": "go"}})
print("OK")
"""


def pa_hook(fix, question: str, header: str) -> subprocess.CompletedProcess:
    """Drive the live pre-ask guard the way `.claude/settings.json` does.

    THE PRE-ASK GUARD IS A PYTHON MODULE SINCE THE W5 P7 CUTOVER, so this goes through the one dispatcher command, named by the guard's module stem. The bash called `../pre-ask/block-settled-questions.sh`, and when that directory stopped existing the `cd` failed, the variable collapsed to a bare script name, bash exited 127 and all three legs reported the guard as broken. Driving
    the thing that actually runs is also the point: a case still pointed at the retired bash file would have kept passing while the live guard went unchecked.
    """
    dispatch = wlfix.STOP_DIR.parents[1] / "rediacc_hooks" / "dispatch.py"
    env = dict(fix.env)
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    payload = '{"session_id":"%s","tool_input":{"questions":[{"question":"%s","header":"%s"}]}}' % (
        fix.sid,
        question,
        header,
    )
    return subprocess.run(
        [sys.executable, str(dispatch), "block_settled_questions"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_211_a_door_parked_wave_is_reported_never_blocked_on(wl):  # noqa: F811
    """`_wave_rows` deliberately emits nothing for a wave whose covering items were all closed through a door: the work did not happen, no session can make it happen, and demanding a tick would be demanding a lie. That reasoning is right, and it skipped the wave into TOTAL silence: no violation, and its item is `[x]` so it has also left `--list --open`. Nothing surfaced it again,
    ever.

    Found 2026-08-15 when the operator asked why the stop hook had never mentioned an unticked w8. The honest answer was that the ONLY thing keeping it visible was a session remembering to write it into a report by hand.

    211b CONTROL continues on the same world: the same wave TICKED says nothing at all. Without it the advisory could be firing on any unticked wave, or on every checklist regardless of state, and would read as noise within a day.
    """
    wl.say("done for now\n\n## Remaining\n- nothing")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_DEMO_SECRETS)
    iid = additem(wl.cli("--add", "deadbeef", "cl:demo/w1 Wave A: mint the production secrets"))
    wl.cli("--tick", "deadbeef", iid, "door:operator-only -- secrets are write-only, exit 0")
    got = wl.run()
    parked = "211: door-parked wave decision=%s out: %s" % (got.decision, got.out[:400])
    assert "w1 [door:operator-only]" in got.out, parked
    assert got.decision != "block", parked

    clfile(wl, "demo", CL_DEMO_SECRETS_TICKED)
    got = wl.run()
    assert "door:operator-only]" not in got.out, (
        "211b CONTROL: the advisory fired on a TICKED wave: %s" % got.out[:300]
    )


def test_211c_control_closed_without_a_door_is_a_different_thing_entirely(wl):  # noqa: F811
    """An item ticked by DOING the work leaves the wave genuinely done-but-unticked, which is a VIOLATION with its own exit, not a door advisory. If this case ever starts printing the advisory, the door detector has stopped reading doors and is matching every closed item."""
    wl.say("done for now\n\n## Remaining\n- nothing")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_DEMO_WIRE)
    iid = additem(wl.cli("--add", "deadbeef", "cl:demo/w1 Wave A: wire the thing"))
    wl.cli("--tick", "deadbeef", iid, "wired it, suite green, exit 0")
    got = wl.run()
    doorless = "211c CONTROL: %s" % got.out[:400]
    assert "DONE-BUT-UNTICKED" in got.out, doorless
    assert "door:" not in got.out, doorless


def test_213_the_block_counter_is_session_scoped(wl):  # noqa: F811
    """It was a single shared `.blocks` for the whole worktree. With roughly 48 addressable sessions here, one peer's clean allow deleted another session's judge streak and one peer's block inflated it, so every decision keyed off the streak was reading someone else's work. Fixed before the cadence lands, because the cadence's cap is the next thing to key off block streaks.

    213b CONTROL continues on the same world, and it is the whole point: plant a peer's streak, take one more stop, and it must survive byte for byte. Under the old shared file this stop would have overwritten or deleted it.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.run()
    counter = wl.stem(".blocks-deadbeef")
    assert counter.is_file(), "213: no per-session counter; found: %s" % sorted(
        path.name for path in counter.parent.glob("*.blocks*")
    )

    peer = wl.stem(".blocks-cafe1234")
    peer.write_text("7", encoding="utf-8")
    wl.run()
    survived = peer.read_text(encoding="utf-8") if peer.is_file() else ""
    assert survived == "7", "213b CONTROL: peer streak became %r" % survived


def test_214_the_cadence_stands_down_for_one_turn_after_being_answered(wl):  # noqa: F811
    """The operator's ask was one report or update, then one turn for other work. The acceptance test is the plan's own sentence, that the cadence must make it easier to be HEARD and not easier to STOP, so every guard below exists because the naive version fails it. These are the ONLY cases that exercise the cadence: `run` defaults it off.

    THE FIXTURE CHANGED ON 2026-08-27 and the change is the case's subject now, so read this before "restoring" it. It used to be an OPEN ITEM plus a live worker, and it pinned that a session holding open work could be handed its quiet turn. The operator asked for the opposite, since the pause message fired far too often and should be the last chance rather than the first. Guard
    (E), `not actionable_remains`, now refuses the pause whenever there is an open item, a pending task or a live `[>]` lease, and the old fixture can no longer pause by construction. Keeping it here would have pinned a behaviour that was deliberately removed.

    What replaces it is a rotating violation with NOTHING actionable behind it: a reported-but-unfixed finding. That is the shape where a stand-down is still right, since the session has no work in hand and only a nag outstanding, so this case still pins the cadence itself. Case 214f is the other half, and it is the old fixture with the opposite expectation.
    """
    wl.cadence = "on"
    wl.say(CADENCE_ANSWER)
    wl.brief_now()
    wl.hand_now()
    wl.check("block", "finding(s) you did not fix", "214: the first stop still DEMANDS")
    wl.newturn()
    wl.say(CADENCE_ANSWERED)
    got = wl.run()
    paused = "214: decision=%s out: %s" % (got.decision, got.out[:220])
    assert got.decision != "block", paused
    assert "still outstanding" in got.out, paused


def test_214b_guard_b_an_unchanged_message_buys_nothing(wl):  # noqa: F811
    """Without this a session emits an empty turn after every block and gets a free allow every other stop, which is the exact regression the cadence must not be. No `say` between the two stops here, so the assistant message is byte-identical.

    The same non-actionable fixture as 214, for the same reason: with an open item the pause is refused by guard (E) and this case would pass without ever exercising guard B, green, and proving nothing about the thing it is named after.

    NO `newturn` BETWEEN THE STOPS, and that is the correction rather than a shortcut. The old fixture called `newturn` with no `say`, which does not leave the message byte-identical at all: it resets the transcript window, so the last message becomes EMPTY and its signature changes. That worked only because the violation was store-derived and survived an empty message; a
    message-derived one vanishes with the window, and the stop went clean. Running again on the same transcript is what an assistant saying nothing new actually looks like to the hook.
    """
    wl.cadence = "on"
    wl.say(CADENCE_ANSWER)
    wl.brief_now()
    wl.hand_now()
    wl.check("block", "finding(s) you did not fix", "214b: first stop demands")
    wl.check(
        "block",
        "finding(s) you did not fix",
        "214b GUARD B: no new say means no pause, it demands again",
    )


def test_214c_guard_a_the_always_tier_defeats_the_pause(wl):  # noqa: F811
    """The integrity tier is the reason this machinery exists. A session that just answered still does not get a quiet turn while something urgent is outstanding. Non-actionable fixture, as 214: otherwise guard (E) refuses the pause first and this case stops testing guard A at all.

    STDERR IS CAPTURED, NOT DISCARDED. This case failed once in CI with an EMPTY output and passed locally at 735/0, and a discarded stderr is precisely why that was undiagnosable: an empty stdout looks identical whether the hook decided to allow or died before deciding. A test that cannot say WHICH of those happened sends its reader guessing at a difference the machine already
    knew.
    """
    wl.cadence = "on"
    wl.say(CADENCE_ANSWER)
    wl.brief_now()
    wl.hand_now()
    wl.check("block", "finding(s) you did not fix", "214c: first stop demands")
    wl.newturn()
    wl.say(CADENCE_URGENT)
    # hook-blind is an always-tier violation: an unparseable event.
    wl.transcript.write_text("not json at all", encoding="utf-8")
    got = wl.run(event="garbage-not-json")
    assert '"decision": "block"' in got.out, (
        "214c GUARD A: the always tier was paused: rc=%d stdout=[%s] stderr=[%s]"
        % (got.rc, got.out[:220], got.err[-400:].replace("\n", " "))
    )


def test_214d_a_clean_stop_consumes_the_debt(wl):  # noqa: F811
    """The hook owes a quiet turn to a session it just interrupted, not a voucher redeemable whenever that session next happens to be blocked. Found by case 3619: block, clean allow, new item, and the new item was silently paused.

    Non-actionable fixture, as 214. The debt is spent by DROPPING the finding line rather than by ticking an item, which is the same three-stop shape: violation, clean stop, violation again.
    """
    wl.cadence = "on"
    wl.say(CADENCE_ANSWER)
    wl.brief_now()
    wl.hand_now()
    wl.check("block", "finding(s) you did not fix", "214d: first stop demands")
    wl.newturn()
    wl.say(CADENCE_FIXED)
    wl.check("allow", "", "214d: the clean stop allows")
    wl.newturn()
    wl.say(CADENCE_FRESH)
    wl.check(
        "block",
        "finding(s) you did not fix",
        "214d: the NEW violation demands, the debt was spent on the clean stop",
    )


def test_214e_the_kill_switch_restores_the_old_behaviour_exactly(wl):  # noqa: F811
    """The kill switch has to work, or there is no way back if this proves wrong in daily use. Non-actionable fixture, as 214: with an open item this stop would block under guard (E) whatever the kill switch said, so the case could not tell the switch working from the switch being ignored."""
    wl.cadence = "off"
    wl.say(CADENCE_ANSWER)
    wl.brief_now()
    wl.hand_now()
    wl.check("block", "finding(s) you did not fix", "214e: first stop demands")
    wl.newturn()
    wl.say(CADENCE_ANSWERED)
    wl.check(
        "block", "finding(s) you did not fix", "214e: with cadence OFF it demands again immediately"
    )


def test_214f_guard_e_actionable_work_in_hand_refuses_the_pause(wl):  # noqa: F811
    """The other half of 214, and the operator's actual complaint: the pause fired far too often when there was plenty in hand. This is 214's ORIGINAL fixture, verbatim: an open item plus a live worker, so the always-tier idle-stall gate stands down (a background worker is running) and `open-items` is the only outstanding check, rotating and therefore pausable under every guard
    except (E). Before (E) this stop was PAUSED, which is the exact turn the operator wanted back. Now it demands.

    ONE RUN, BOTH FACTS. The demand and the absence of the stand-down text have to be read off the SAME stop: a second `check` call is a second stop, and after a pause the next stop blocks anyway, so a split assertion would pass on a fixture that had just paused. It did, while this case was being written.
    """
    wl.cadence = "on"
    wl.bg = '[{"status":"running","description":"agent"}]'
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.check("block", "OPEN worklist item", "214f: the first stop demands")
    wl.newturn()
    wl.say("I have now answered the demand\n\n## Remaining\n- stuff")
    got = wl.run()
    survived = "214f GUARD E: the pause survived actionable work: %s" % got.out[:300]
    assert '"decision": "block"' in got.out, survived
    assert "OPEN worklist item" in got.out, survived
    assert "but this stop is YOURS" not in got.out, survived


def test_214g_guard_f_an_unfinished_mission_refuses_the_pause(wl):  # noqa: F811
    """The operator's sentence, made executable: there should be a list of what has to be shown with this order, and until every one of them is checked off no stop may claim the turn for itself.

    Guard (E) already refuses the pause while there is an open item, a pending task or a live lease, but that is a non-empty queue, which is not the same fact as the job being done. The fixture below has an EMPTY board and an unticked program wave: nothing actionable in the worklist sense, and the thing the session was handed is plainly unfinished. Before (F) this stop was handed
    its quiet turn.

    ONE RUN, BOTH FACTS, for the reason 214f states: after a pause the NEXT stop blocks anyway, so a split assertion passes on a fixture that had just paused.
    """
    wl.cadence = "on"
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_DEMO_HANDED)
    wl.say("answer\n\n## Remaining\n- nothing outstanding")
    wl.check("block", "w1", "214g: the first stop demands the unticked wave")
    wl.newturn()
    wl.say("I have now answered the demand\n\n## Remaining\n- nothing outstanding")
    got = wl.run()
    survived = "214g GUARD F: the pause survived an unfinished mission: %s" % got.out[:300]
    assert '"decision": "block"' in got.out, survived
    assert "but this stop is YOURS" not in got.out, survived


def test_214h_control_the_same_fixture_with_the_mission_settled_still_pauses(wl):  # noqa: F811
    """Without this, 214g is satisfied by a hook that had simply stopped pausing. The wave is ticked and the checklist flipped done, so the only thing left is a rotating nag with nothing actionable behind it, which is 214's own shape."""
    wl.cadence = "on"
    wl.brief_now()
    wl.hand_now()
    wl.say(CADENCE_ANSWER)
    wl.check("block", "finding(s) you did not fix", "214h: the first stop demands")
    wl.newturn()
    wl.say(CADENCE_ANSWERED)
    got = wl.run()
    swallowed = "214h CONTROL: guard F swallowed the ordinary pause: decision=%s %s" % (
        got.decision,
        got.out[:250],
    )
    assert got.decision != "block", swallowed
    assert "still outstanding" in got.out, swallowed


def test_222_the_idle_stall_gate_an_open_item_nobody_carrying_it_nothing_moved(wl):  # noqa: F811
    """WHY (operator, 2026-08-26): stopping with remaining items while there is neither a background agent nor a running monitor or shell is very annoying, and those items were plainly not blocked on a dependency or on a question.

    `open-items` already existed and was already a violation: it is in the ROTATING tier, which is what the cadence above is allowed to pause (case 214 pins exactly that). So the observed loop was legal: block, say something new, get a pause, repeat. The v21 gate is the ALWAYS-tier backstop for the one shape where a pause is never right, and the controls below are the whole point:
    a gate that fires on every stop with an open item would be worse than none, because a session cannot tell an accusation from background noise.

    FIRST SIGHT NEVER FIRES: with no baseline there is no evidence about the turn.
    """
    wl.say("answer\n\n## Remaining\n- the thing")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) do the thing")
    wl.check_quiet(
        "ACTIONABLE WORK IN HAND", "222: the first stop takes a baseline and does not accuse"
    )
    wl.newturn()
    wl.say("still thinking about it\n\n## Remaining\n- the thing")
    wl.check(
        "block",
        "YOU ARE STOPPING WITH ACTIONABLE WORK IN HAND",
        "222: the SECOND idle stop is refused",
    )
    wl.check(
        "block",
        "DONE, LEASED to a live worker, or [?] parked",
        "222: and it states the rule positively",
    )


def test_222b_control_an_item_ticked_between_the_two_stops_is_silent(wl):  # noqa: F811
    """The single most important control. If this ever starts firing, the gate has stopped measuring progress and is just counting open items."""
    wl.say("answer\n\n## Remaining\n- two things")
    wl.brief_now()
    wl.hand_now()
    wl.reg_repo()
    wl.add_item("- [ ] (deadbeef) first thing")
    wl.add_item("- [ ] (deadbeef) second thing")
    wl.run()  # baseline
    head = wl.git("rev-parse", "--short", "HEAD").stdout.strip()
    text = wl.wl.read_text(encoding="utf-8").replace(
        "- [ ] (deadbeef) first thing", "- [x] (deadbeef) first thing proof %s" % head
    )
    wl.wl.write_text(text, encoding="utf-8")
    wl.newturn()
    wl.say("closed the first one\n\n## Remaining\n- second thing")
    wl.check_quiet("ACTIONABLE WORK IN HAND", "222b CONTROL: real progress leaves the gate silent")


def test_222c_control_an_item_moved_to_a_deferral_with_a_default_is_silent(wl):  # noqa: F811
    """Parking a decision on the operator is a legitimate stop."""
    wl.say("answer\n\n## Remaining\n- the decision")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) do the thing")
    wl.run()  # baseline
    text = wl.wl.read_text(encoding="utf-8").replace(
        "- [ ] (deadbeef) do the thing", "- [?] (deadbeef) do the thing DEFAULT: do it on Monday"
    )
    wl.wl.write_text(text, encoding="utf-8")
    wl.newturn()
    wl.say("parked it on you\n\n## Remaining\n- the decision")
    wl.check_quiet(
        "ACTIONABLE WORK IN HAND", "222c CONTROL: parking on the operator is a legitimate stop"
    )


def test_222d_control_every_item_leased_to_a_live_worker_is_silent(wl):  # noqa: F811
    """A live lease is not a stall."""
    wl.say("answer\n\n## Remaining\n- delegated")
    wl.brief_now()
    wl.hand_now()
    until = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=30)).strftime(
        "%Y-%m-%dT%H:%MZ"
    )
    wl.add_item("- [>] (deadbeef) until:%s worker:w1 delegated to agent" % until)
    wl.bg = '[{"id":"w1","status":"running","description":"agent"}]'
    wl.run()
    wl.newturn()
    wl.say("still running\n\n## Remaining\n- delegated")
    wl.check_quiet("ACTIONABLE WORK IN HAND", "222d CONTROL: a live lease is not a stall")


def test_222e_control_an_open_item_with_a_running_worker_is_silent(wl):  # noqa: F811
    """Narrower than 222d on purpose: the operator's complaint names the absence of a background agent, so a session that HAS one is supervising, not stalling."""
    wl.say("answer\n\n## Remaining\n- the thing")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) do the thing")
    wl.bg = '[{"status":"running","description":"agent"}]'
    wl.run()
    wl.newturn()
    wl.say("the worker is on it\n\n## Remaining\n- the thing")
    wl.check_quiet(
        "ACTIONABLE WORK IN HAND", "222e CONTROL: a running background worker suppresses the gate"
    )


def test_222f_the_cadence_cannot_pause_the_idle_stall_gate(wl):  # noqa: F811
    """The regression this whole gate exists for: an open item with NOBODY carrying it. Byte for byte case 214f's fixture, except no background worker, which is what moves the refusal from the rotating `open-items` check to the always-tier idle-stall gate, and that is exactly the needle below. This comment named case 214 until 2026-08-27; 214's fixture is non-actionable now, and
    214f inherited the open-item-plus-worker shape.
    """
    wl.cadence = "on"
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.check("block", "OPEN worklist item", "222f: the first stop demands")
    wl.newturn()
    wl.say("I have now answered the demand\n\n## Remaining\n- stuff")
    wl.check(
        "block",
        "YOU ARE STOPPING WITH ACTIONABLE WORK IN HAND",
        "222f: saying something new no longer buys the pause",
    )


def test_222g_the_tell_a_remaining_line_claiming_the_item_is_unblocked(wl):  # noqa: F811
    """The specific admission the operator caught: a claim that an item has no blocker, written into the very section that is supposed to explain why the work has stopped."""
    wl.say("answer\n\n## Remaining\n- #a1 finish the migration -- blocked on: nothing, next up")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) finish the migration")
    wl.bg = '[{"status":"running","description":"agent"}]'
    wl.check(
        "block",
        "CLAIMS an item has no blocker",
        "222g: the unblocked claim is refused even while a worker runs",
    )


def test_222h_control_writing_about_the_phrase_does_not_trip_it(wl):  # noqa: F811
    """The V_FOUND_NOT_FIXED precedent: a gate that cannot survive being described is too broad, and every message discussing this check quotes its own trigger."""
    wl.say(
        "answer\n\n## Remaining\n- the gate now refuses a line reading `blocked on: nothing` -- see the new case"
    )
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) finish the migration")
    wl.bg = '[{"status":"running","description":"agent"}]'
    wl.check_quiet(
        "CLAIMS an item has no blocker", "222h CONTROL: a backticked mention is not a claim"
    )


def test_222i_control_a_bare_nothing_remaining_is_not_a_claim(wl):  # noqa: F811
    """An empty Remaining LIST is the opposite of asserting that a listed item has no blocker. Matching it would fire the gate on the cleanest report shape in the suite."""
    wl.say("answer\n\n## Remaining\n- nothing")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) finish the migration")
    wl.bg = '[{"status":"running","description":"agent"}]'
    wl.check_quiet(
        "CLAIMS an item has no blocker",
        "222i CONTROL: an empty Remaining list is not an unblocked claim",
    )


def test_222j_the_failure_path_a_raising_gate_must_not_wedge_or_wave_through(wl):  # noqa: F811
    """A check that throws is worse than one that is absent (case 99 makes the same point for the hook as a whole). Both guards are exercised: the wrapper at the call site, and `closed_sig`'s own swallow.

    THE META-CONTROL is the second assertion: the planted raise really was reachable. Without it, this case passes on a rewrite that matched nothing.
    """
    wl.say("answer\n\n## Remaining\n- the thing")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) do the thing")
    crashdir = wl.base / "hookcrash"
    crashdir.mkdir(parents=True, exist_ok=True)
    for source in sorted(wlfix.STOP_DIR.glob("*.py")):
        shutil.copy(str(source), str(crashdir / source.name))
    checks = crashdir / "wl_checks.py"
    planted = re.sub(
        r"(?m)^def idle_stall\(",
        'def idle_stall(*_a, **_k):\n    raise RuntimeError("planted idle_stall crash")\n\n\n'
        "def _idle_stall_unused(",
        checks.read_text(encoding="utf-8"),
    )
    checks.write_text(planted, encoding="utf-8")
    wl.hook = crashdir / "worklist.py"
    got = wl.run()
    wedged = "222j: out=[%s] err=[%s]" % (got.out[:220], got.err[-200:].replace("\n", " "))
    assert '"decision": "block"' in got.out, wedged
    assert "OPEN worklist item" in got.out, wedged
    assert "planted idle_stall crash" not in got.out, wedged

    assert "planted idle_stall crash" in checks.read_text(encoding="utf-8"), (
        "222j META: the rewrite matched nothing, so 222j proved nothing"
    )

    # `closed_sig`'s own swallow, driven directly: an unreadable store must produce "unknown", never an exception and never an accusation.
    probe = pyprobe(wl, PROBE_222J, {"HOOKDIR": str(wlfix.STOP_DIR)})
    assert probe.returncode == 0, (
        "222j: a helper raised on an unreadable store: %s" % (probe.stdout + probe.stderr)[-300:]
    )


def test_223_the_pending_ask_gate_an_ask_announced_and_never_made(wl):  # noqa: F811
    """THE COST, as a sequence rather than an argument. A session writes `two questions for you` and stops. The operator spends a turn saying to ask. The session calls AskUserQuestion, and the pre-ask guard refuses it as something CLAUDE.md already answers. The removable cost is THE OPERATOR'S TURN, and a Stop hook that blocks is the only place in the chain that reaches it: every
    later hook runs after the turn is gone.

    The detector is `wl_admit.pending_ask`; this file holds the controls because the gate is always-tier, exactly like idle-stall above, and for the same reason: a paused stop still ends the turn, so a rotating copy would buy nothing.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say(PA_MSG)
    wl.check(
        "block",
        "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT",
        "223: an announced ask with no AskUserQuestion is refused",
    )
    wl.check(
        "block",
        "Two questions for you before I pick the branch.",
        "223: and it quotes the line it matched",
    )
    wl.check(
        "block",
        "call AskUserQuestion with the question, in this turn",
        "223: it offers asking now as an exit",
    )
    wl.check("block", "worklist.py --defer deadbeef", "223: it offers parking it with a DEFAULT")
    wl.check("block", "answer it yourself from the code", "223: it offers settling it")


def test_223b_control_the_same_message_with_the_ask_actually_made_is_silent(wl):  # noqa: F811
    """One byte of fixture state apart from 223: an assistant record whose only block is a tool_use for AskUserQuestion, in the same turn. `used_tool` exists for this; `say` writes text blocks only, so before it there was no way to fixture a session that called the tool and this control could not have been written."""
    wl.brief_now()
    wl.hand_now()
    wl.used_tool("AskUserQuestion")
    wl.say(PA_MSG)
    wl.check_quiet("YOU ANNOUNCED A QUESTION", "223b CONTROL: asking it satisfies the gate")


def test_223c_control_the_same_message_with_a_defer_this_turn_is_silent(wl):  # noqa: F811
    """The second exit. The baseline stop is deliberate: without it the fixture would be silenced by `defer_created`'s first-sight leniency instead of by the deferral, and the case would pass without exercising the signature at all."""
    wl.brief_now()
    wl.hand_now()
    wl.say(PA_MSG)
    pa_id = additem(wl.cli("--add", "deadbeef", "the branch decision"))
    wl.run()  # baseline: the [?] set is empty and banked as such
    wl.cli(
        "--defer",
        "deadbeef",
        pa_id,
        "which branch should this ride? DEFAULT: the branch of the PR that is already open WHY: a second PR is the operator's call, not a fact in the tree HOW: the operator names the branch, or the DEFAULT lands it on the open one",
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION", "223c CONTROL: parking it with a DEFAULT satisfies the gate"
    )


def test_223d_control_writing_about_the_gate_does_not_trip_it(wl):  # noqa: F811
    """The V_FOUND_NOT_FIXED precedent, and the reason `wl_core.strip_quoted_spans` is shared rather than copied: every message describing this gate quotes its own triggers, and a gate that cannot survive being written about is too broad."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "Wired the new gate. It anchors on announcement, so it matches `two questions for you`, `your call` and `want me to` in the closing span, and ignores them inside backticks.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION", "223d CONTROL: backticked triggers are not an announcement"
    )


def test_223e_control_an_ordinary_completion_report_is_silent(wl):  # noqa: F811
    """A plain report is not an announcement."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "Suite is 810/0. The ledger writes one row per refusal and the Stop advisory names the path.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION", "223e CONTROL: a plain report is not an announcement"
    )


def test_223h_control_a_declarative_your_call_close_is_not_an_announcement(wl):  # noqa: F811
    """Review-found live, twice in one session: a closing sentence saying that merging is the operator's call, and not something to do autonomously, fired this gate, and neither instance was an unasked question. Both are a settled-fact close, not a solicitation. The copula is what makes it declarative."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "PR #579 is green, out of draft, mergeable, and fully reviewed. Stopping here -- merge is your call.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION",
        "223h CONTROL: a declarative close naming whose call it is does not fire",
    )


def test_223i_a_standalone_your_call_announcement_still_fires(wl):  # noqa: F811
    """The regression control for the fix above: narrowing the copula-attached form must not silence the alternative entirely."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "Your call on which branch to use before I continue.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check(
        "block",
        "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT",
        "223i: a standalone lead-in (not preceded by is/was) still fires",
    )


def test_223j_control_a_declarative_decisions_yours_close_does_not_fire(wl):  # noqa: F811
    """SWEEP: the SAME class in `decisions...yours`, `let me know` and `want me to`. Found by sweeping `ASK_ANNOUNCEMENT_RE`'s other alternatives for the exact defect class the declarative close fixed, after a judge demanded the sweep: a phrase that can ALSO be used declaratively (citing an existing fact or rule) rather than as a live solicitation. All three fired on real prose
    before this fix.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "I left both alone since these are decisions that are genuinely yours, not mine to make for you.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION", "223j CONTROL: a declarative close of that shape does not fire"
    )


def test_223j_a_standalone_decisions_yours_lead_in_still_fires(wl):  # noqa: F811
    """The positive half of the sweep: the same alternative, with no copula in front of it, is a live solicitation and still fires."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "Two decisions that are genuinely yours: which vendor, and when to ship.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check(
        "block",
        "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT",
        "223j: a standalone lead-in (not preceded by a copula) still fires",
    )


def test_223j_control_reported_speech_about_a_convention_does_not_fire(wl):  # noqa: F811
    """Reported speech about an existing convention (say, says or said before the trigger) is a citation, not a request."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "The docs already say to let me know if the build breaks, so I did not change that convention.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION", "223j CONTROL: reported speech about an existing convention"
    )


def test_223j_a_genuine_let_me_know_if_request_still_fires(wl):  # noqa: F811
    """The positive half: `let me know if` as a live request still fires."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "Let me know if you want the cluster fixed before I continue.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check(
        "block",
        "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT",
        "223j: a genuine request of that shape still fires",
    )


def test_223j_control_a_negated_want_me_to_citing_a_constraint_does_not_fire(wl):  # noqa: F811
    """A negated `want me to` citing an existing constraint is a citation, not an offer."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "I did not touch main because you do not want me to push there without asking.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet("YOU ANNOUNCED A QUESTION", "223j CONTROL: a negated form citing a constraint")


def test_223j_control_never_want_me_to_citing_a_standing_rule_does_not_fire(wl):  # noqa: F811
    """The same negation in its `never` form, citing a standing rule."""
    wl.brief_now()
    wl.hand_now()
    wl.say(
        "I skipped the merge since the standing rule says you never want me to merge without being asked.\n\n## Remaining\n- nothing outstanding"
    )
    wl.check_quiet(
        "YOU ANNOUNCED A QUESTION", "223j CONTROL: the never form citing a standing rule"
    )


def test_223j_a_genuine_want_me_to_offer_still_fires(wl):  # noqa: F811
    """The positive half: `want me to` with no negation is a live offer and still fires."""
    wl.brief_now()
    wl.hand_now()
    wl.say("Want me to proceed with the merge now.\n\n## Remaining\n- nothing outstanding")
    wl.check(
        "block",
        "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT",
        "223j: a genuine offer with no negation still fires",
    )


def test_223f_the_pending_ask_gate_is_not_shadowed_by_another_always_tier_violation(wl):  # noqa: F811
    """Violations are gathered and emitted as ONE block, and the always tier is printed in full while everything else becomes a bare count. So a gate that computes correctly and is then swallowed by an earlier emit looks green forever. This fires the pending-ask gate WHILE idle-stall is live and demands BOTH texts, the only assertion that can tell computed from delivered."""
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) do the thing")
    wl.say(PA_MSG)
    wl.run()  # idle-stall needs a baseline before it can accuse
    wl.newturn()
    wl.say(PA_MSG)
    got = wl.run()
    shadowed = "223f: only one always-tier text survived: %s" % got.out[:400]
    assert "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT" in got.out, shadowed
    assert "YOU ARE STOPPING WITH ACTIONABLE WORK IN HAND" in got.out, shadowed


def test_223g_the_failure_path_the_detectors_helpers_never_raise(wl):  # noqa: F811
    """Same contract as 222j next door: a stall detector that crashes a stop is worse than one that is absent. The call site is wrapped; these are the helpers under it, driven directly on the inputs that would break a careless implementation."""
    probe = pyprobe(wl, PROBE_223G, {"HOOKDIR": str(wlfix.STOP_DIR)})
    assert probe.returncode == 0, (
        "223g: a pending-ask helper raised: %s" % (probe.stdout + probe.stderr)[-300:]
    )


def test_223h_the_refusal_ledger_records_a_refusal_and_then_surfaces_it(wl):  # noqa: F811
    """Before this the pre-ask hook refused questions and left NO trace anywhere the operator looks, and `.claude/hooks/test-hooks.sh` names the consequence itself: a false positive is invisible by construction, because the operator never learns what was not asked. This drives the real guard, then asserts the Stop advisory that reads what it wrote.

    ONE RUN, BOTH NEEDLES on the last leg. A queued advisory is drained exactly once, so two `check` calls would be two stops and the second would assert the absence of something it had already consumed: a green test proving the opposite of what it reads like.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("done\n\n## Remaining\n- nothing outstanding")
    ledger = pathlib.Path(str(wl.wl) + ".ask-refusals.jsonl")
    refused = pa_hook(wl, "Should I commit this now?", "commit")
    rows = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    recorded = "223h: rc=%d ledger=[%s]" % (refused.returncode, rows[:200])
    assert refused.returncode == 2, recorded
    assert rows.strip(), recorded
    assert '"permission":"should i"' in rows, recorded
    assert '"object":"commit"' in rows, recorded

    # A question that is NOT permission-seeking must pass AND leave the ledger alone, or the count the advisory prints is meaningless.
    passed = pa_hook(wl, "Which branch strategy fits this repo?", "design")
    rows = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    design = "223h: rc=%d rows=%d" % (passed.returncode, rows.count("\n"))
    assert passed.returncode == 0, design
    assert rows.count("\n") == 1, design

    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    got = wl.run()
    surfaced = "223h: the ledger advisory did not surface: %s" % got.out[:300]
    assert "were REFUSED by" in got.out, surfaced
    assert ".ask-refusals.jsonl" in got.out, surfaced
    assert '"decision": "block"' not in got.out, surfaced


def test_223i_control_no_refusals_means_no_advisory(wl):  # noqa: F811
    """A surface that speaks when the count is zero is noise, and noise is what the rotation exists to prevent."""
    wl.brief_now()
    wl.hand_now()
    wl.say("done\n\n## Remaining\n- nothing outstanding")
    wl.env["WORKLIST_REPORT_PER_STOP"] = "9"
    wl.check_quiet("were REFUSED by", "223i CONTROL: an empty ledger says nothing")
