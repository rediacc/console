"""Two-key advisory rotation, foreign drift reporting, the judge's advisory limits, dead-worker remedies, and the specialist-agent hint.

Ported from `.claude/hooks/stop/worklist-cases/20-advisories-rotation.sh`, one pytest function per bash case, with the same assertions in the same order against the same hook invocation. A bash leg that continued its predecessor's world with no fresh `setup` stays inside its predecessor's function; a leg that called `setup` again becomes a new function.

`clfile`, `cldeliver`, `additem` and `pyprobe` are IMPORTED from the module 19-checklists.sh became. The bash suite sourced its case files in order and had exactly one definition of each, and an import keeps it that way rather than forking a second copy that drifts.
"""

from __future__ import annotations

import os
import re
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_checklists import additem, cldeliver, clfile, pyprobe
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# --- the checklist bodies the cases plant -----------------------------------

CL_ALPHA_EXECUTING = """# Handoff checklist: alpha
Status: executing

## Deliverables
- [x] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
"""

CL_BETA_EXECUTING = """# Handoff checklist: beta
Status: executing

## Deliverables
- [x] d1 file:docs/beta/README.md

## Waves
- [ ] w1 Wave A: wire the beta thing
"""

CL_ALPHA_PRODUCING_FOREIGN = """# Handoff checklist: alpha
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
"""

CL_BETA_PRODUCING_FOREIGN = """# Handoff checklist: beta
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/beta/README.md

## Waves
- [ ] w1 Wave A: wire the beta thing
"""

CL_DEMO_DRIFT_FOREIGN = """# Handoff checklist: demo
Status: executing
Owner: cafe0000

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
"""

CL_DEMO_DRIFT_MINE = CL_DEMO_DRIFT_FOREIGN.replace("Owner: cafe0000", "Owner: deadbeef")

# --- the specialist-agent hint fixture, defined once in the bash and reused --

HINT_DESC = "Zorbium recalibration and the frobnicator index, including sprocket torque."
HINT_SAY = "done for now, next up is the zorbium frobnicator recalibration"

HINT_BRIEFING = """You are picking up the zorbium frobnicator recalibration, which has been running since the sprocket torque numbers came back wrong on the third pass. Nothing is committed yet and the fixture rig is still wired up the way the last session left it.

## Next action

Re-run the frobnicator index build, then compare the recalibration output against the numbers in the notes."""

BROKEN_AGENT = "---\nname: brokenagent\ntools: Bash\n---\nbody with no description\n"


def hint_fixture(fix) -> None:
    """A clean allow stop whose last message is in the fixture domain."""
    fix.say(HINT_SAY)
    fix.brief_now()
    fix.hand_now()


def hint_n(out: str) -> int:
    """Occurrences of the hint header in one payload.

    A COUNT, not a match: the payload is ONE JSON line, so a line-oriented grep answers 1 for two hints and the double-fire cases below would pass on a feature that fired every stop.
    """
    return out.count("Specialist agent available")


PROBE_207 = """
import os
import sys

sys.path.insert(0, os.environ["HOOKDIR"])
from wl_judge import sanitize_next_action as s

BLOCK = [
    ("a bare merge order", "merge PRs 563, 565 and 566"),
    ("a polite merge order", "You should probably merge 563 now that it is green."),
    ("the literal command", "gh pr merge 567 --rebase"),
    ("push main", "push main with the fix"),
    ("push main, reversed wording", "get this onto main by pushing"),
    ("cut a release", "cut the release once CI is green"),
    # DELIBERATE over-inclusion, pinned so nobody relaxes it into a bypass: asking about merging is
    # harmless, but a carve-out for the question reopens the door for "ask the operator whether to
    # merge, and if CI is green, merge".
    ("even ASKING about merging", "ask the operator whether to merge"),
]
KEEP = [
    ("an ordinary review action", "reply to the review summary on 567 and resolve its threads"),
    ("release as a NOUN", "update the release notes in docs/ before the next wave"),
    ("the release CHANNEL", "check the release channel manifest for edge"),
    ("an ordinary suite action", "run the umbrella suite and tick f1c5d077 with the count"),
    ("an empty next action", ""),
]
for why, text in BLOCK:
    got = s({"next_action": text})["next_action"]
    print(("REJECTED " if got.startswith("[rejected") else "LEAKED ") + why)
for why, text in KEEP:
    got = s({"next_action": text})["next_action"]
    print(("KEPT " if got == text else "CLOBBERED ") + why)
# The VERDICT itself must never be touched: stop-or-continue is the judge's actual job and rewriting
# it here would collide with the no-escape-hatch invariant.
v = s({"verdict": "stop", "reason": "clean", "next_action": "merge 563"})
print("VERDICT-INTACT" if v["verdict"] == "stop" and v["reason"] == "clean" else "VERDICT-MUTATED")
"""


def test_204_two_handoffs_two_keys_the_rotation_serves_both_one_per_stop(wl):  # noqa: F811
    """Two uncovered waves in one check class are both itemized across two stops, one per stop in battery order, and the CONTROL at the end proves the per-slug key does not outlive the wave it belonged to."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/alpha/README.md", "the readme")
    cldeliver(wl, "docs/beta/README.md", "the readme")
    clfile(wl, "alpha", CL_ALPHA_EXECUTING)
    clfile(wl, "beta", CL_BETA_EXECUTING)
    out1 = wl.run().out
    out2 = wl.run().out
    both = out1 + out2
    starved = "204: one handoff starved the other in the rotation: 1=%s 2=%s" % (
        out1[:300],
        out2[:300],
    )
    assert "handoff 'alpha' (agent/programs/alpha/CHECKLIST.md)" in both, starved
    assert "handoff 'beta' (agent/programs/beta/CHECKLIST.md)" in both, starved
    widened = "204: the focused block stopped rotating: 1=%s 2=%s" % (out1[:300], out2[:300])
    assert "handoff 'beta'" not in out1, widened
    assert "handoff 'alpha'" not in out2, widened

    wl.cli_as("cafe0000", "--add", "cafe0000", "cl:alpha/w1 Wave A: wire the alpha thing")
    wl.cli_as("cafe0000", "--add", "cafe0000", "cl:beta/w1 Wave A: wire the beta thing")
    got = wl.run()
    # CONTROL: both waves claimed, so neither per-slug key is left outstanding.
    outlived = "204 CONTROL: a per-slug key outlived the wave it belonged to: %s" % got.out[:400]
    assert got.rc == 0, outlived
    assert "UNCOVERED" not in got.out, outlived
    assert '"decision": "block"' not in got.out, outlived


def test_205_control_one_foreign_handoff_one_advisory_and_betas_needle_can_be_absent(wl):  # noqa: F811
    """Leg 1 of bash case 205, and it is the needle's own control: with only alpha planted, beta's needle must be MISSING. Without it the main leg could pass on a match that hits anything, which is the failure mode a two-needle assertion hides best.

    EACH LEG GETS ITS OWN FIXTURE, and that is not tidiness. Draining an advisory latches it in the queue's `shown` ledger, so planting beta beside an ALREADY-SHOWN alpha suppresses alpha through the refresh window: correct behaviour that looks exactly like the overwrite bug, and it would have made the main leg fire for the wrong reason.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_REPORT_PER_STOP"] = "6"
    clfile(wl, "alpha", CL_ALPHA_PRODUCING_FOREIGN)
    got = wl.run()
    baseline = (
        "205 CONTROL: the single-checklist baseline is not what it claims: %s" % got.out[:400]
    )
    assert "agent/programs/alpha/CHECKLIST.md is 'Status: producing'" in got.out, baseline
    assert "agent/programs/beta/CHECKLIST.md" not in got.out, baseline


def test_205_two_foreign_advisories_two_keys_the_second_no_longer_eats_the_first(wl):  # noqa: F811
    """Both foreign handoffs ride the report; neither advisory overwrites the other."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_REPORT_PER_STOP"] = "6"
    clfile(wl, "alpha", CL_ALPHA_PRODUCING_FOREIGN)
    clfile(wl, "beta", CL_BETA_PRODUCING_FOREIGN)
    got = wl.run()
    replaced = "205: one foreign advisory replaced the other in the queue: %s" % got.out[:600]
    assert got.rc == 0, replaced
    assert "agent/programs/alpha/CHECKLIST.md is 'Status: producing'" in got.out, replaced
    assert "agent/programs/beta/CHECKLIST.md is 'Status: producing'" in got.out, replaced


def test_206_a_foreign_drift_advisory_reports_it_and_issues_no_order(wl):  # noqa: F811
    """A non-owner is told about the drift and is handed no instruction to act on, and it says out loud that repairing it here would overwrite live work. The CONTROL at the end continues on the same world with the owner flipped: the SAME drift under its owner still blocks, imperative intact, so ownership is what decides who is ordered to repair."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_REPORT_PER_STOP"] = "6"
    clfile(wl, "demo", CL_DEMO_DRIFT_FOREIGN)
    got = wl.run()
    ordered = "206: the foreign drift advisory still issues the owner's order: rc=%d %s" % (
        got.rc,
        got.out[:600],
    )
    assert got.rc == 0, ordered
    assert "d1 docs/demo/README.md -- MISSING" in got.out, ordered
    assert "Reported, never blocked on." in got.out, ordered
    assert "cafe0000" in got.out, ordered
    assert "in this turn" not in got.out, ordered
    assert "another session's" in got.out, (
        "206: nothing warned the reader off editing a peer's checklist: %s" % got.out[:600]
    )

    clfile(wl, "demo", CL_DEMO_DRIFT_MINE)
    got = wl.run()
    whose = "206 CONTROL: ownership stopped deciding who is ordered to repair: %s" % got.out[:600]
    assert '"decision": "block"' in got.out, whose
    assert "reality disagrees" in got.out, whose
    assert "in this turn" in got.out, whose


def test_207_the_judge_advises_and_does_not_order_the_operators_three_things(wl):  # noqa: F811
    """Paid for on 2026-08-09: the stop gate read a session sitting on four green stacked PRs and returned a next action of merging three of them. The session declined, which is the right outcome reached by the WRONG mechanism: it survived on the model's judgement at the moment of reading, and this whole program exists because judgement at the moment of reading is the faculty that
    fails. The filter is deterministic so a tireder session cannot comply with its own stop gate.
    """
    probe = pyprobe(wl, PROBE_207, {"HOOKDIR": str(wlfix.STOP_DIR)})
    out = probe.stdout
    leaked = [line for line in out.splitlines() if line.startswith("LEAKED ")]
    assert len(re.findall(r"(?m)^REJECTED ", out)) == 7, "207 an operator-only order leaked: %s" % (
        leaked or (out + probe.stderr)[:300]
    )
    assert not leaked, "207 an operator-only order leaked: %s" % leaked
    # CONTROL: ordinary next actions survive, including release as a noun.
    clobbered = [line for line in out.splitlines() if line.startswith("CLOBBERED ")]
    assert len(re.findall(r"(?m)^KEPT ", out)) == 5, (
        "207 CONTROL: a legitimate next action was clobbered: %s"
        % (clobbered or (out + probe.stderr)[:300])
    )
    assert not clobbered, "207 CONTROL: a legitimate next action was clobbered: %s" % clobbered
    # CONTROL: the verdict and reason are left untouched (no escape hatch).
    assert re.search(r"(?m)^VERDICT-INTACT", out), (
        "207 CONTROL: the filter mutated the verdict itself"
    )


def test_208_a_dead_worker_gets_the_remedy_that_can_actually_resolve_it(wl):  # noqa: F811
    """Paid for live on 2026-08-10. The 90-minute rung reported that the declared worker is not in the harness background list any more and printed `--update <id>` as the command. A session ran exactly that, with real evidence, and the IDENTICAL complaint fired on the next stop: `--update` refreshes the item's text and its liveness clock and leaves the false `worker:X` claim
    standing. The prose offered three remedies and the one printed command was the only one that cannot work. One full round trip lost.

    THE SECOND ASSERTION IS THE ONE THAT WOULD HAVE CAUGHT THE ORIGINAL BUG, and it REQUIRES THE BLOCK TO BE PRESENT rather than asserting the absence of `--update` alone. The first version asserted only the absence, and a mutation that suppressed the whole dead-worker block made it PASS: with no block there is no `--update` in the output, so a bare negative is satisfied by the
    feature not existing. A check that passes when the thing it guards is gone is the exact defect this suite exists to catch, and only running the mutation revealed it.
    """
    wl.brief_now()
    wl.hand_now()
    cid = additem(wl.cli("--add", "deadbeef", "work handed to a worker that then died"))
    lastevent = wl.stem(".lastevent-deadbeef.json")
    # Lease it to a worker the harness DOES know, so the lease is accepted...
    lastevent.write_text(
        '{"background_tasks":[{"id":"bw9","type":"shell","status":"running","description":"the watch"}]}\n',
        encoding="utf-8",
    )
    wl.cli("--lease", "deadbeef", cid, "+120", "worker:bw9", "watching the run")
    # ...then take that worker away, which is exactly what a finished task looks like.
    lastevent.write_text('{"background_tasks":[]}\n', encoding="utf-8")
    wl.bg = "[]"
    got = wl.run()
    remedies = "208 dead-worker block missing its remedies: %s" % got.out[:400]
    assert "NO LONGER EXISTS" in got.out, remedies
    assert "worklist.py --lease deadbeef" in got.out, remedies
    assert "worklist.py --tick deadbeef" in got.out, remedies

    still = "208 block absent, or still printing --update for a dead worker: %s" % got.out[:400]
    assert "NO LONGER EXISTS" in got.out, still
    assert not re.search(r"worklist\.py --update deadbeef", got.out), still


def test_208_control_a_still_listed_worker_is_never_called_gone(wl):  # noqa: F811
    """CONTROL: a worker the harness still lists is merely quiet, not gone, and must NOT be pushed onto the dead-worker path."""
    wl.brief_now()
    wl.hand_now()
    cid = additem(wl.cli("--add", "deadbeef", "work with a live worker"))
    wl.stem(".lastevent-deadbeef.json").write_text(
        '{"background_tasks":[{"id":"bw9","type":"shell","status":"running","description":"the watch"}]}\n',
        encoding="utf-8",
    )
    wl.cli("--lease", "deadbeef", cid, "+120", "worker:bw9", "watching the run")
    wl.bg = '[{"id":"bw9","status":"running","description":"the watch"}]'
    got = wl.run()
    assert "NO LONGER EXISTS" not in got.out, (
        "208 CONTROL: a live worker was reported as gone: %s" % got.out[:300]
    )


def test_209a_a_matching_last_message_produces_the_hint_on_an_allow_stop(wl):  # noqa: F811
    """WHY THE WHOLE 209 GROUP EXISTS. On 2026-08-14 the operator had to hint twice by hand, naming the bench server deployment and pointing at `.claude/agents/`, because nothing surfaced the seven specialists that already existed: the word "bench" appeared ZERO times across all seven `description` fields and exactly once in the whole directory, in a BODY. The knowledge existed and
    the matching surface did not. The hook now says so unprompted.

    EVERY CASE BELOW USES INVENTED NOUNS against the fixture corpus that `WORKLIST_AGENTS_DIR` pins. A fixture borrowing the real agents' vocabulary would go red when somebody edits a description, which is prose nobody thinks of as test data.

    THE HINT IS PRIORITY 3 and `OUTQ_PER_STOP` is 1, so on any stop carrying another advisory the hint correctly loses the slot. That is the single most important noise control in the design (209K proves it), and it is why every case that wants to SEE a hint widens the drain first.
    """
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("fixtureagent", HINT_DESC)
    hint_fixture(wl)
    wl.check(
        "allow",
        "Specialist agent available: fixtureagent",
        "209A a matching last message produces the hint on an allow stop",
    )


def test_209a_control_neutral_text_earns_no_hint(wl):  # noqa: F811
    """CONTROL, and it leads with a POSITIVE PRESENCE check rather than the absence alone. This suite documents the trap at case 208: a mutation that suppressed a whole block made an absence-only assertion PASS, because with no feature there is nothing to find. So the stop must be shown to have spoken at all first."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("fixtureagent", HINT_DESC)
    wl.say("done for now, the meeting notes are filed")
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    neutral = "209A CONTROL: neutral text hinted, or the stop said nothing: %s" % got.out[:400]
    assert "INBOX HAS BEEN QUIET" in got.out, neutral
    assert hint_n(got.out) == 0, neutral


def test_209b_the_hint_rides_an_allow_and_never_blocks(wl):  # noqa: F811
    """ADVISORY, NEVER A BLOCK. `vadd` has 46 call sites and every one of them stops the session; blocking a session for not consulting a specialist is the fastest possible way to get this feature switched off."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("fixtureagent", HINT_DESC)
    hint_fixture(wl)
    got = wl.run()
    blocked = "209B the hint blocked or failed the stop (rc=%d): %s" % (got.rc, got.out[:400])
    assert got.rc == 0, blocked
    assert hint_n(got.out) == 1, blocked
    assert '"decision"' not in got.out, blocked
    assert "Do not stop yet" not in got.out, blocked


def test_209c_a_tie_is_silence_by_construction(wl):  # noqa: F811
    """A TIE IS SILENCE, BY CONSTRUCTION: a tie makes the margin 0, which is below any positive threshold, so there is no tie-break rule to get wrong. Inventing a winner is how a matcher starts lying.

    The CONTROL continues on the same fixture with a haystack naming only ONE of the two agents. Without it, the silence above would pass just as well on a matcher that had simply stopped working.
    """
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("tiealpha", "Zorbium recalibration with the widget gearbox lattice.")
    wl.mk_agent("tiebeta", "Zorbium recalibration with the sprocket flywheel lattice.")
    wl.say("done for now, the widget gearbox and the sprocket flywheel both wait on me")
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    broken = "209C a tie was broken, or it crashed: %s err: %s" % (got.out[:300], got.err[:200])
    assert hint_n(got.out) == 0, broken
    assert "Traceback" not in got.err, broken

    wl.newturn()
    wl.say("done for now, the widget gearbox waits on me")
    got = wl.run()
    assert "Specialist agent available: tiealpha" in got.out, (
        "209C CONTROL: the corpus could not hint at all, so 209C proved nothing: %s" % got.out[:400]
    )


def test_209d_the_same_specialist_is_not_suggested_twice(wl):  # noqa: F811
    """RATE LIMIT: the same specialist is not suggested twice. A hint that fires on every stop is wallpaper, and wallpaper gets ignored."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("fixtureagent", HINT_DESC)
    hint_fixture(wl)
    out = wl.run().out
    wl.newturn()
    wl.say(HINT_SAY)
    out2 = wl.run().out
    counts = "209D hint counts were %d then %d" % (hint_n(out), hint_n(out2))
    assert hint_n(out) == 1, counts
    assert hint_n(out) + hint_n(out2) == 1, counts


def test_209e_a_deleted_agent_cannot_be_recommended(wl):  # noqa: F811
    """A DELETED AGENT CANNOT BE RECOMMENDED. The corpus is re-read from disk on every stop for exactly this reason, which is also why there is no cache: a cache is what would let a deleted agent keep being recommended.

    The second stop matches a DIFFERENT agent on the same text, deliberately. A case that merely re-ran the deleted agent's own haystack would pass on the refresh window alone, proving nothing about the corpus being re-read.
    """
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("gonesoon", HINT_DESC)
    hint_fixture(wl)
    out = wl.run().out
    (wl.base / "agents" / "gonesoon.md").unlink()
    wl.mk_agent("stillhere", HINT_DESC)
    wl.newturn()
    wl.say(HINT_SAY)
    got2 = wl.run()
    stale = "209E stale corpus or crash: %s err: %s" % (got2.out[:400], got2.err[:200])
    assert "Specialist agent available: gonesoon" in out, stale
    assert "Specialist agent available: stillhere" in got2.out, stale
    assert "gonesoon" not in got2.out, stale
    assert "Traceback" not in got2.err, stale


def test_209f_the_hint_is_independent_of_the_judge(wl):  # noqa: F811
    """INDEPENDENT OF THE JUDGE. `wl_judge` spends one haiku call per eventful stop at 4.9 to 20.0 seconds and has BLOCKED a stop on a timeout; a second model call was refused. This pins that the hint is deterministic and does not ride that call: the judge is off and the fixture PATH holds no `claude` at all."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("fixtureagent", HINT_DESC)
    hint_fixture(wl)
    got = wl.run()
    needed = "209F the hint needed the judge: %s" % got.out[:400]
    assert hint_n(got.out) == 1, needed
    assert "Stop-gate judge" not in got.out, needed


def test_209g_a_malformed_corpus_is_loud_and_degrades_rather_than_disables(wl):  # noqa: F811
    """A file that cannot be parsed is an agent that has silently stopped being reachable, which is the exact failure this whole feature exists to end, so it is reported, while every sibling that IS well-formed keeps matching."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("goodagent", HINT_DESC)
    (wl.base / "agents" / "brokenagent.md").write_text(BROKEN_AGENT, encoding="utf-8")
    hint_fixture(wl)
    got = wl.run()
    swallowed = "209G the corpus error was swallowed or it disabled the matcher: %s" % got.out[:400]
    assert "Agent corpus problem" in got.out, swallowed
    assert "brokenagent" in got.out, swallowed
    assert "Specialist agent available: goodagent" in got.out, swallowed


def test_209h_postcompact_hands_the_compacted_session_its_specialist(wl):  # noqa: F811
    """POSTCOMPACT, which is the highest-value delivery in the design: a compacted session is precisely the one that has forgotten a specialist exists, and additionalContext is read rather than skimmed. Once per compaction by construction, so it needs no rate limit."""
    wl.mk_agent("fixtureagent", HINT_DESC)
    wl.python(["--state", wlfix.ME], stdin=HINT_BRIEFING)
    got = wl.post_compact()
    carried = "209H PostCompact carried no hint: %s" % got.out[:400]
    assert "picking up an in-progress session" in got.out, carried
    assert "Specialist agent available: fixtureagent" in got.out, carried


def test_209h_control_an_off_domain_briefing_still_arrives_without_a_hint(wl):  # noqa: F811
    """CONTROL: the same corpus, a briefing in no agent's domain. The briefing must still arrive, since absence of the hint alone would also describe a broken PostCompact."""
    wl.mk_agent("fixtureagent", HINT_DESC)
    wl.hand_now()
    got = wl.post_compact()
    broke = "209H CONTROL: the briefing broke, or hinted off-domain: %s" % got.out[:400]
    assert "picking up an in-progress session" in got.out, broke
    assert hint_n(got.out) == 0, broke


def test_209i_the_kill_switch_silences_the_hint_and_nothing_else(wl):  # noqa: F811
    """THE KILL SWITCH. Positive presence first, for the reason case 208 records."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.env["WORKLIST_AGENT_HINT"] = "off"
    wl.mk_agent("fixtureagent", HINT_DESC)
    hint_fixture(wl)
    got = wl.run()
    killed = "209I the kill switch did not kill, or it killed the whole report: %s" % got.out[:400]
    assert "INBOX HAS BEEN QUIET" in got.out, killed
    assert hint_n(got.out) == 0, killed


def test_209j_the_per_session_cap_holds_across_two_different_agents(wl):  # noqa: F811
    """THE PER-SESSION CAP, across DIFFERENT agents. The refresh window in 209D only bounds one agent; without a cap, eight specialists could each get a turn."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.env["WORKLIST_AGENT_HINT_MAX_PER_SESSION"] = "1"
    wl.mk_agent("alphaagent", HINT_DESC)
    wl.mk_agent("betaagent", "Quixotic pumpjack telemetry and the marlinspike ledger.")
    hint_fixture(wl)
    out = wl.run().out
    wl.newturn()
    wl.say("done for now, the quixotic pumpjack telemetry needs a marlinspike ledger entry")
    out2 = wl.run().out
    leaked = "209J cap leaked: %d then %d" % (hint_n(out), hint_n(out2))
    assert "Specialist agent available: alphaagent" in out, leaked
    assert hint_n(out) + hint_n(out2) == 1, leaked


def test_209j_control_raise_the_cap_by_one_and_the_second_specialist_lands(wl):  # noqa: F811
    """CONTROL: one planted fact differs, the cap. The second agent must then land, or 209J was measuring a matcher that could only ever hit once."""
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.env["WORKLIST_AGENT_HINT_MAX_PER_SESSION"] = "2"
    wl.mk_agent("alphaagent", HINT_DESC)
    wl.mk_agent("betaagent", "Quixotic pumpjack telemetry and the marlinspike ledger.")
    hint_fixture(wl)
    out = wl.run().out
    wl.newturn()
    wl.say("done for now, the quixotic pumpjack telemetry needs a marlinspike ledger entry")
    out2 = wl.run().out
    never = "209J CONTROL: the second agent never fired, so the cap proved nothing: %s" % out2[:400]
    assert "Specialist agent available: alphaagent" in out, never
    assert "Specialist agent available: betaagent" in out2, never


def test_209k_priority_3_never_displaces_a_real_section(wl):  # noqa: F811
    """This is the case to write first: it PROVES the noise control instead of asserting it. Every existing advisory is priority 2 or better and `outq_drain` releases one section per stop, so a hint reaches the operator only on a stop with nothing more important to say. That property costs nothing to obtain and is the whole reason this feature is not wallpaper.

    The CONTROL is what makes this a measurement rather than a coincidence: widen the drain on the very next stop and the hint is STILL THERE, so what the first leg observed was a queued hint being outranked, not a hint that never fired.
    """
    wl.mk_agent("fixtureagent", HINT_DESC)
    hint_fixture(wl)
    wl.brief_other("cafe1234")
    peer = wl.base / "cafe1234.jsonl"
    peer.write_text("", encoding="utf-8")
    aged = time.time() - 48 * 3600
    os.utime(peer, (aged, aged))
    wl.add_item("- [ ] (cafe1234) their abandoned item")
    # WORKLIST_REPORT_PER_STOP unset, so exactly one section is released.
    got = wl.run()
    displaced = "209K the hint displaced a real section, or nothing was queued: %s" % got.out[:400]
    assert hint_n(got.out) == 0, displaced
    assert re.search(
        r"INBOX HAS BEEN QUIET|ORPHANED item\(s\)|Other sessions in this worktree", got.out
    ), displaced
    assert "more report section(s) queued" in got.out, displaced

    wl.env["WORKLIST_REPORT_PER_STOP"] = "6"
    wl.newturn()
    wl.say(HINT_SAY)
    got2 = wl.run()
    assert "Specialist agent available: fixtureagent" in got2.out, (
        "209K CONTROL: the outranked hint was never queued at all: %s" % got2.out[:400]
    )


def test_209l_the_operators_own_sentence_fires_on_a_description_without_deployment(wl):  # noqa: F811
    """THE OPERATOR'S OWN SENTENCE, verbatim. REGRESSION 2026-08-15. The sentence that caused this feature to be built named the bench server deployment, and when the matcher was first wired up it returned NOTHING for it. The corpus carried `deploy`, `deploying` and `deploys`, three variants of one verb, hand-enumerated, and not `deployment`, so the query lost that hit to
    morphology, landed on `bench` alone at 1.0, and died against MIN_SCORE=2. The feature would have shipped unable to answer the only query a real session is KNOWN to have needed.

    Pinned in the operator's words rather than a tidied paraphrase, because a paraphrase is written by the same hand that writes the matcher and drifts toward whatever the matcher already does.

    THE FIXTURE DESCRIPTION MUST NOT CONTAIN `deployment`, and the case ASSERTS that rather than trusting it: if some future session "fixes" a red run here by pasting the query's word into the description, the assertion below goes red instead, which is the hand-maintained-variant-list staleness this fold exists to end.

    THE OPERATOR'S SENTENCE IS VERBATIM AND MUST STAY VERBATIM; what changed on 2026-08-27 is only the assistant framing around it. As a bare message it is a closing line that ends in a question mark and addresses the operator, which is exactly the shape the v23 pending-ask gate refuses, and a blocked stop emits no advisory, so this case went red on a gate that had nothing to do
    with agent hints. No real assistant message is a quoted operator question with nothing else in it; every term this case measures is still in the haystack, in the operator's own words and in the same order.

    THE CONTROL is what makes this a measurement of MORPHOLOGY rather than of the word `bench`: `bench` on its own scores 1.0, below MIN_SCORE, and stays silent. So the hit that carried the first leg over the floor can only have come from `deployment` folding onto the description's `deploy`.
    """
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent(
        "benchops", "The bench rig: deploy the account worker to the bench box and reset its store."
    )
    wl.say(
        "The operator asked: there is bench server deployment. Why you don't utilize it? Wiring the bench drill now."
    )
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    corpus = (wl.base / "agents" / "benchops.md").read_text(encoding="utf-8")
    silent = (
        "209L the motivating query still does not fire, or the fixture was tautologised: %s"
        % got.out[:400]
    )
    assert "deployment" not in corpus, silent
    assert "Specialist agent available: benchops" in got.out, silent

    wl.newturn()
    wl.say("there is a bench in the corridor and nobody has claimed it")
    got = wl.run()
    assert hint_n(got.out) == 0, (
        "209L CONTROL: a single term cleared MIN_SCORE, so the floor is not holding: %s"
        % got.out[:400]
    )


def test_209m_counting_words_never_route_a_dismissal_to_a_specialist(wl):  # noqa: F811
    """WHY THIS EXISTS. The specialist PUSHBACK (the "already covers" text) had no case at all, and it misrouted live: a session reporting "33 errors total, 32 pre-existing" about TypeScript in packages/www was sent to the LICENSING specialist, matched on the single token `total`, because licensing-ops' description happens to say "the total tier map" and `discriminative()` hands a
    term unique to one description that description at full weight.

    The dismissal DETECTION was right, the claim was unproven, and pushing back on it found a real error in the session's own reporting. Only the routing was nonsense, and a hint that names the wrong specialist spends the reader's trust in every later hint. `total` is now a stopword; this is the case that keeps it one. Same failure class as `while` (media-pipeline) already in the
    list.

    CONTROL, POSITIVE PRESENCE FIRST, per the trap at case 208: an absence-only assertion passes just as well when the whole feature is suppressed. So the pushback is proved to still fire for the SAME fixture on genuinely discriminative vocabulary before the silence above is trusted.
    """
    wl.env["WORKLIST_REPORT_PER_STOP"] = "4"
    wl.mk_agent("zorbops", "Zorbium ledger reconciliation and the total sprocket cap.")
    wl.newturn()
    wl.say("the remaining failures are pre-existing: 32 errors total, none of them mine")
    got = wl.run()
    assert "already covers" not in got.out, (
        "209M a counting word routed a dismissal to a specialist: %s" % got.out[:400]
    )

    wl.newturn()
    wl.say("the zorbium ledger reconciliation cannot be tested locally")
    got = wl.run()
    proves = (
        "209M CONTROL: the pushback is silent for the right claim too, so 209M proves nothing: %s"
        % got.out[:400]
    )
    assert "already covers" in got.out, proves
    assert "zorbops" in got.out, proves
