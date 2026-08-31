#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Two-key advisory rotation, foreign drift reporting, the judge's advisory limits, dead-worker remedies, and the specialist-agent hint.

echo "== 204. two handoffs, two keys: the rotation serves BOTH, one per stop =="
setup
say "done for now"
brief_now
hand_now
cldeliver docs/alpha/README.md "the readme"
cldeliver docs/beta/README.md "the readme"
clfile alpha <<'MD'
# Handoff checklist: alpha
Status: executing

## Deliverables
- [x] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
MD
clfile beta <<'MD'
# Handoff checklist: beta
Status: executing

## Deliverables
- [x] d1 file:docs/beta/README.md

## Waves
- [ ] w1 Wave A: wire the beta thing
MD
OUT1="$(run)"
OUT2="$(run)"
if grep -qF "handoff 'alpha' (agent/programs/alpha/CHECKLIST.md)" <<<"$OUT1$OUT2" &&
    grep -qF "handoff 'beta' (agent/programs/beta/CHECKLIST.md)" <<<"$OUT1$OUT2"; then
    pass "204: two uncovered waves in one check class are both itemized across two stops"
else
    fail "204: one handoff starved the other in the rotation: 1=${OUT1:0:300} 2=${OUT2:0:300}"
fi
if ! grep -qF "handoff 'beta'" <<<"$OUT1" && ! grep -qF "handoff 'alpha'" <<<"$OUT2"; then
    pass "204: and it is still ONE per stop, in battery order -- the block did not widen"
else
    fail "204: the focused block stopped rotating: 1=${OUT1:0:300} 2=${OUT2:0:300}"
fi
as_peer cafe0000 reqcli --add cafe0000 "cl:alpha/w1 Wave A: wire the alpha thing" >/dev/null
as_peer cafe0000 reqcli --add cafe0000 "cl:beta/w1 Wave A: wire the beta thing" >/dev/null
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && ! grep -qF "UNCOVERED" <<<"$OUT" && ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "204 CONTROL: both waves claimed, so neither per-slug key is left outstanding"
else
    fail "204 CONTROL: a per-slug key outlived the wave it belonged to: ${OUT:0:400}"
fi

echo "== 205. two FOREIGN advisories, two keys: the second no longer eats the first =="
# Leg 1 is the needle's own control: with only alpha planted, beta's needle
# must be MISSING. Without it, leg 2 could pass on a grep that matches
# anything, which is the failure mode a two-needle assertion hides best.
#
# EACH LEG GETS ITS OWN FIXTURE, and that is not tidiness. Draining an
# advisory latches it in the queue's `shown` ledger, so planting beta beside an
# ALREADY-SHOWN alpha suppresses alpha through the refresh window -- correct
# behaviour that looks exactly like the overwrite bug and would have made this
# case fire for the wrong reason.
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile alpha <<'MD'
# Handoff checklist: alpha
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
MD
OUT="$(run)"
if grep -qF "agent/programs/alpha/CHECKLIST.md is 'Status: producing'" <<<"$OUT" &&
    ! grep -qF "agent/programs/beta/CHECKLIST.md" <<<"$OUT"; then
    pass "205 CONTROL: one foreign handoff, one advisory, and beta's needle can be absent"
else
    fail "205 CONTROL: the single-checklist baseline is not what it claims: ${OUT:0:400}"
fi
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile alpha <<'MD'
# Handoff checklist: alpha
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/alpha/README.md

## Waves
- [ ] w1 Wave A: wire the alpha thing
MD
clfile beta <<'MD'
# Handoff checklist: beta
Status: producing
Owner: cafe0000

## Deliverables
- [ ] d1 file:docs/beta/README.md

## Waves
- [ ] w1 Wave A: wire the beta thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "agent/programs/alpha/CHECKLIST.md is 'Status: producing'" <<<"$OUT" &&
    grep -qF "agent/programs/beta/CHECKLIST.md is 'Status: producing'" <<<"$OUT"; then
    pass "205: both foreign handoffs ride the report; neither advisory overwrites the other"
else
    fail "205: one foreign advisory replaced the other in the queue: ${OUT:0:600}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 206. a foreign DRIFT advisory reports it; it does not order the reader around =="
setup
say "done for now"
brief_now
hand_now
export WORKLIST_REPORT_PER_STOP=6
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: cafe0000

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "d1 docs/demo/README.md -- MISSING" <<<"$OUT" &&
    grep -qF "Reported, never blocked on." <<<"$OUT" &&
    grep -qF "cafe0000" <<<"$OUT" && ! grep -qF "in this turn" <<<"$OUT"; then
    pass "206: a non-owner is told about the drift and is handed no instruction to act on"
else
    fail "206: the foreign drift advisory still issues the owner's order: rc=$RC ${OUT:0:600}"
fi
if grep -qF "another session's" <<<"$OUT"; then
    pass "206: and it says out loud that repairing it here would overwrite live work"
else
    fail "206: nothing warned the reader off editing a peer's checklist: ${OUT:0:600}"
fi
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: deadbeef

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
MD
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "reality disagrees" <<<"$OUT" &&
    grep -qF "in this turn" <<<"$OUT"; then
    pass "206 CONTROL: the SAME drift under its owner still blocks, imperative intact"
else
    fail "206 CONTROL: ownership stopped deciding who is ordered to repair: ${OUT:0:600}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 207. the judge ADVISES; it does not get to order the operator's three things =="
# Paid for on 2026-08-09: the stop gate read a session sitting on four green
# stacked PRs and returned next_action "merge PRs 563, 565 and 566". The session
# declined, which is the right outcome reached by the WRONG mechanism: it survived
# on the model's judgement at the moment of reading, and this whole program exists
# because judgement at the moment of reading is the faculty that fails. The filter
# is deterministic so a tireder session cannot comply with its own stop gate.
setup
JUDGE_FILTER_OUT="$(
    python3 - "$(dirname "$HOOK")" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from wl_judge import sanitize_next_action as s
BLOCK = [
    ("a bare merge order", "merge PRs 563, 565 and 566"),
    ("a polite merge order", "You should probably merge 563 now that it is green."),
    ("the literal command", "gh pr merge 567 --rebase"),
    ("push main", "push main with the fix"),
    ("push main, reversed wording", "get this onto main by pushing"),
    ("cut a release", "cut the release once CI is green"),
    # DELIBERATE over-inclusion, pinned so nobody relaxes it into a bypass: asking
    # about merging is harmless, but a carve-out for the question reopens the door
    # for "ask the operator whether to merge, and if CI is green, merge".
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
# The VERDICT itself must never be touched: stop-or-continue is the judge's actual
# job and rewriting it here would collide with the no-escape-hatch invariant.
v = s({"verdict": "stop", "reason": "clean", "next_action": "merge 563"})
print("VERDICT-INTACT" if v["verdict"] == "stop" and v["reason"] == "clean" else "VERDICT-MUTATED")
PYEOF
)"
if [[ "$(grep -c '^REJECTED ' <<<"$JUDGE_FILTER_OUT")" == "7" ]] && ! grep -q '^LEAKED ' <<<"$JUDGE_FILTER_OUT"; then
    pass "207 every operator-only order is rejected (7 shapes, including the polite one)"
else
    fail "207 an operator-only order leaked: $(grep '^LEAKED ' <<<"$JUDGE_FILTER_OUT")"
fi
if [[ "$(grep -c '^KEPT ' <<<"$JUDGE_FILTER_OUT")" == "5" ]] && ! grep -q '^CLOBBERED ' <<<"$JUDGE_FILTER_OUT"; then
    pass "207 CONTROL: ordinary next actions survive, including release as a noun"
else
    fail "207 CONTROL: a legitimate next action was clobbered: $(grep '^CLOBBERED ' <<<"$JUDGE_FILTER_OUT")"
fi
if grep -q '^VERDICT-INTACT' <<<"$JUDGE_FILTER_OUT"; then
    pass "207 CONTROL: the verdict and reason are left untouched (no escape hatch)"
else
    fail "207 CONTROL: the filter mutated the verdict itself"
fi

echo "== 208. a DEAD worker gets the remedy that can actually resolve it =="
# Paid for live on 2026-08-10. The 90-minute rung reported "its declared
# worker:X is NOT in the harness background list any more" and printed
# `--update <id>` as the command. A session ran exactly that, with real
# evidence, and the IDENTICAL complaint fired on the next stop: --update
# refreshes the item's text and its liveness clock and leaves the false
# worker:X claim standing. The prose offered three remedies and the one
# printed command was the only one that cannot work. One full round trip lost.
setup
brief_now
hand_now
CID=$(reqcli --add deadbeef "work handed to a worker that then died" | grep -oE '#[0-9a-f]+' | tr -d '#')
# Lease it to a worker the harness DOES know, so the lease is accepted...
printf '{"background_tasks":[{"id":"bw9","type":"shell","status":"running","description":"the watch"}]}\n' \
    >"${WL%.md}.lastevent-deadbeef.json"
reqcli --lease deadbeef "$CID" +120 worker:bw9 "watching the run" >/dev/null 2>&1
# ...then take that worker away, which is exactly what a finished task looks like.
printf '{"background_tasks":[]}\n' >"${WL%.md}.lastevent-deadbeef.json"
BG='[]'
OUT="$(run)"
if grep -qF "NO LONGER EXISTS" <<<"$OUT" && grep -qF "worklist.py --lease deadbeef" <<<"$OUT" && grep -qF "worklist.py --tick deadbeef" <<<"$OUT"; then
    pass "208 the dead-worker block offers --lease and --tick"
else
    fail "208 dead-worker block missing its remedies: ${OUT:0:400}"
fi
# THE ASSERTION THAT WOULD HAVE CAUGHT THE ORIGINAL BUG: the command it prints
# must not be the one that cannot resolve a dead worker.
#
# IT REQUIRES THE BLOCK TO BE PRESENT, and that is not belt-and-braces. The first
# version asserted only the absence of --update, and a mutation that suppressed
# the whole dead-worker block made it PASS: with no block there is no --update in
# the output, so a bare negative is satisfied by the feature not existing. A check
# that passes when the thing it guards is gone is the exact defect this suite
# exists to catch, and only running the mutation revealed it.
if grep -qF "NO LONGER EXISTS" <<<"$OUT" && ! grep -qE "worklist\.py --update deadbeef" <<<"$OUT"; then
    pass "208 the block is present AND does not print --update, the remedy that leaves worker:X standing"
else
    fail "208 block absent, or still printing --update for a dead worker: ${OUT:0:400}"
fi
# CONTROL: a worker the harness still lists is merely quiet, not gone, and must
# NOT be pushed onto the dead-worker path.
setup
brief_now
hand_now
CID=$(reqcli --add deadbeef "work with a live worker" | grep -oE '#[0-9a-f]+' | tr -d '#')
printf '{"background_tasks":[{"id":"bw9","type":"shell","status":"running","description":"the watch"}]}\n' \
    >"${WL%.md}.lastevent-deadbeef.json"
reqcli --lease deadbeef "$CID" +120 worker:bw9 "watching the run" >/dev/null 2>&1
BG='[{"id":"bw9","status":"running","description":"the watch"}]'
OUT="$(run)"
if ! grep -qF "NO LONGER EXISTS" <<<"$OUT"; then
    pass "208 CONTROL: a still-listed worker is never called gone"
else
    fail "208 CONTROL: a live worker was reported as gone: ${OUT:0:300}"
fi

echo "== 209. the specialist-agent hint (wl_agents) =="
# WHY THIS EXISTS. On 2026-08-14 the operator had to hint twice BY HAND ("there
# is bench server deployment", "@.claude/agents/ may help for ops as well")
# because nothing surfaced the seven specialists that already existed: the word
# "bench" appeared ZERO times across all seven `description` fields and exactly
# once in the whole directory, in a BODY. The knowledge existed and the matching
# surface did not. The hook now says so unprompted.
#
# EVERY CASE BELOW USES INVENTED NOUNS against the fixture corpus in
# $BASE/agents (setup pins WORKLIST_AGENTS_DIR at it). A fixture borrowing the
# real agents' vocabulary would go red when somebody edits a description, which
# is prose nobody thinks of as test data.
#
# THE HINT IS PRIORITY 3 and OUTQ_PER_STOP is 1, so on any stop carrying another
# advisory the hint correctly loses the slot. That is the single most important
# noise control in the design (209K proves it), and it is why every case that
# wants to SEE a hint widens the drain first.
HINT_DESC="Zorbium recalibration and the frobnicator index, including sprocket torque."
HINT_SAY="done for now, next up is the zorbium frobnicator recalibration"
hint_fixture() { # a clean allow stop whose last message is in the fixture domain
    say "$HINT_SAY"
    brief_now
    hand_now
}
hint_n() { # occurrences of the hint header in $1
    # A COUNT, not a grep: the payload is ONE JSON line, so `grep -c` answers 1
    # for two hints and the double-fire cases below would pass on a feature
    # that fired every stop.
    python3 -c 'import sys; print(sys.stdin.read().count("Specialist agent available"))' <<<"$1"
}
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
check "209A a matching last message produces the hint on an allow stop" allow \
    "Specialist agent available: fixtureagent"
# CONTROL, and it leads with a POSITIVE PRESENCE check rather than the absence
# alone. This suite documents the trap at case 208: a mutation that suppressed a
# whole block made an absence-only assertion PASS, because with no feature there
# is nothing to find. So the stop must be shown to have spoken at all first.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
say "done for now, the meeting notes are filed"
brief_now
hand_now
OUT="$(run)"
if grep -qF "INBOX HAS BEEN QUIET" <<<"$OUT" && [[ "$(hint_n "$OUT")" -eq 0 ]]; then
    pass "209A CONTROL: the stop still reports, and neutral text earns no hint"
else
    fail "209A CONTROL: neutral text hinted, or the stop said nothing at all: ${OUT:0:400}"
fi

# B. ADVISORY, NEVER A BLOCK. `vadd` has 46 call sites and every one of them
# stops the session; blocking a session for not consulting a specialist is the
# fastest possible way to get this feature switched off.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)"
RC=$?
if [[ "$RC" -eq 0 ]] && [[ "$(hint_n "$OUT")" -eq 1 ]] &&
    ! grep -qF '"decision"' <<<"$OUT" && ! grep -qF "Do not stop yet" <<<"$OUT"; then
    pass "209B the hint rides an allow: no decision field, no block reason, rc=0"
else
    fail "209B the hint blocked or failed the stop (rc=$RC): ${OUT:0:400}"
fi

# C. A TIE IS SILENCE, BY CONSTRUCTION: a tie makes the margin 0, which is below
# any positive threshold, so there is no tie-break rule to get wrong. Inventing a
# winner is how a matcher starts lying.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent tiealpha "Zorbium recalibration with the widget gearbox lattice."
mk_agent tiebeta "Zorbium recalibration with the sprocket flywheel lattice."
say "done for now, the widget gearbox and the sprocket flywheel both wait on me"
brief_now
hand_now
OUT="$(run)"
if [[ "$(hint_n "$OUT")" -eq 0 ]] && ! grep -qF "Traceback" "$BASE/err.txt"; then
    pass "209C two agents matching equally produce no hint and no error"
else
    fail "209C a tie was broken, or it crashed: ${OUT:0:300} err: $(head -c 200 "$BASE/err.txt")"
fi
# CONTROL: the same two fixtures, a haystack naming only ONE of them. Without
# this, 209C would pass on a matcher that had simply stopped working.
newturn
say "done for now, the widget gearbox waits on me"
OUT="$(run)"
if grep -qF "Specialist agent available: tiealpha" <<<"$OUT"; then
    pass "209C CONTROL: break the tie and the same corpus hints immediately"
else
    fail "209C CONTROL: the corpus could not hint at all, so 209C proved nothing: ${OUT:0:400}"
fi

# D. RATE LIMIT: the same specialist is not suggested twice. A hint that fires
# on every stop is wallpaper, and wallpaper gets ignored.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)"
newturn
say "$HINT_SAY"
OUT2="$(run)"
if [[ "$(hint_n "$OUT")" -eq 1 ]] && [[ $(($(hint_n "$OUT") + $(hint_n "$OUT2"))) -eq 1 ]]; then
    pass "209D two identical stops in a row emit the hint exactly once"
else
    fail "209D hint counts were $(hint_n "$OUT") then $(hint_n "$OUT2")"
fi

# E. A DELETED AGENT CANNOT BE RECOMMENDED. The corpus is re-read from disk on
# every stop for exactly this reason, which is also why there is no cache: a
# cache is what would let a deleted agent keep being recommended.
#
# The second stop matches a DIFFERENT agent on the same text, deliberately. A
# case that merely re-ran the deleted agent's own haystack would pass on the
# refresh window alone, proving nothing about the corpus being re-read.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent gonesoon "$HINT_DESC"
hint_fixture
OUT="$(run)"
rm -f "$BASE/agents/gonesoon.md"
mk_agent stillhere "$HINT_DESC"
newturn
say "$HINT_SAY"
OUT2="$(run)"
if grep -qF "Specialist agent available: gonesoon" <<<"$OUT" &&
    grep -qF "Specialist agent available: stillhere" <<<"$OUT2" &&
    ! grep -qF "gonesoon" <<<"$OUT2" && ! grep -qF "Traceback" "$BASE/err.txt"; then
    pass "209E a deleted agent stops being recommended, and its sibling still is"
else
    fail "209E stale corpus or crash: ${OUT2:0:400} err: $(head -c 200 "$BASE/err.txt")"
fi

# F. INDEPENDENT OF THE JUDGE. wl_judge spends one haiku call per eventful stop
# at 4.9-20.0s and has BLOCKED a stop on a timeout; a second model call was
# refused. This pins that the hint is deterministic and does not ride that call.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)" # JUDGE_MODE=off, and $BASE/binonly holds no `claude` at all
if [[ "$(hint_n "$OUT")" -eq 1 ]] && ! grep -qF "Stop-gate judge" <<<"$OUT"; then
    pass "209F the hint fires with the judge OFF, so it costs no model call"
else
    fail "209F the hint needed the judge: ${OUT:0:400}"
fi

# G. A MALFORMED CORPUS IS LOUD, AND DEGRADES RATHER THAN DISABLES. A file that
# cannot be parsed is an agent that has silently stopped being reachable, which
# is the exact failure this whole feature exists to end -- so it is reported,
# while every sibling that IS well-formed keeps matching.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent goodagent "$HINT_DESC"
printf -- '---\nname: brokenagent\ntools: Bash\n---\nbody with no description\n' \
    >"$BASE/agents/brokenagent.md"
hint_fixture
OUT="$(run)"
if grep -qF "Agent corpus problem" <<<"$OUT" && grep -qF "brokenagent" <<<"$OUT" &&
    grep -qF "Specialist agent available: goodagent" <<<"$OUT"; then
    pass "209G a description-less agent is REPORTED and its valid sibling still matches"
else
    fail "209G the corpus error was swallowed or it disabled the matcher: ${OUT:0:400}"
fi

# H. POSTCOMPACT, which is the highest-value delivery in the design: a compacted
# session is precisely the one that has forgotten a specialist exists, and
# additionalContext is read rather than skimmed. Once per compaction by
# construction, so it needs no rate limit.
setup
mk_agent fixtureagent "$HINT_DESC"
STATE_SAVE="$STATE_BODY"
STATE_BODY='You are picking up the zorbium frobnicator recalibration, which has been running since the sprocket torque numbers came back wrong on the third pass. Nothing is committed yet and the fixture rig is still wired up the way the last session left it.

## Next action

Re-run the frobnicator index build, then compare the recalibration output against the numbers in the notes.'
hand_now
STATE_BODY="$STATE_SAVE"
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" &&
    grep -qF "Specialist agent available: fixtureagent" <<<"$out"; then
    pass "209H PostCompact hands the compacted session its specialist"
else
    fail "209H PostCompact carried no hint: ${out:0:400}"
fi
# CONTROL: the same corpus, a briefing in no agent's domain. The briefing must
# still arrive -- absence of the hint alone would also describe a broken
# PostCompact.
setup
mk_agent fixtureagent "$HINT_DESC"
hand_now
out="$(printf '{"session_id":"%s","cwd":"%s"}' "$SID" "$BASE/proj" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_AGENT_BRANCH=agenttest \
        python3 "$HOOK" --post-compact 2>/dev/null)"
if grep -qF "picking up an in-progress session" <<<"$out" && [[ "$(hint_n "$out")" -eq 0 ]]; then
    pass "209H CONTROL: an off-domain briefing still arrives, without a hint"
else
    fail "209H CONTROL: the briefing broke, or hinted off-domain: ${out:0:400}"
fi

# I. THE KILL SWITCH. Positive presence first, for the 208 reason.
setup
export WORKLIST_REPORT_PER_STOP=4
export WORKLIST_AGENT_HINT=off
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
OUT="$(run)"
if grep -qF "INBOX HAS BEEN QUIET" <<<"$OUT" && [[ "$(hint_n "$OUT")" -eq 0 ]]; then
    pass "209I WORKLIST_AGENT_HINT=off silences the hint and nothing else"
else
    fail "209I the kill switch did not kill, or it killed the whole report: ${OUT:0:400}"
fi
unset WORKLIST_AGENT_HINT

# J. THE PER-SESSION CAP, across DIFFERENT agents (the refresh window in 209D
# only bounds one agent; without a cap, eight specialists could each get a turn).
setup
export WORKLIST_REPORT_PER_STOP=4
export WORKLIST_AGENT_HINT_MAX_PER_SESSION=1
mk_agent alphaagent "$HINT_DESC"
mk_agent betaagent "Quixotic pumpjack telemetry and the marlinspike ledger."
hint_fixture
OUT="$(run)"
newturn
say "done for now, the quixotic pumpjack telemetry needs a marlinspike ledger entry"
OUT2="$(run)"
if grep -qF "Specialist agent available: alphaagent" <<<"$OUT" &&
    [[ $(($(hint_n "$OUT") + $(hint_n "$OUT2"))) -eq 1 ]]; then
    pass "209J the per-session cap holds across two different agents"
else
    fail "209J cap leaked: $(hint_n "$OUT") then $(hint_n "$OUT2")"
fi
# CONTROL: one planted fact differs, the cap. The second agent must then land,
# or 209J was measuring a matcher that could only ever hit once.
setup
export WORKLIST_REPORT_PER_STOP=4
export WORKLIST_AGENT_HINT_MAX_PER_SESSION=2
mk_agent alphaagent "$HINT_DESC"
mk_agent betaagent "Quixotic pumpjack telemetry and the marlinspike ledger."
hint_fixture
OUT="$(run)"
newturn
say "done for now, the quixotic pumpjack telemetry needs a marlinspike ledger entry"
OUT2="$(run)"
if grep -qF "Specialist agent available: alphaagent" <<<"$OUT" &&
    grep -qF "Specialist agent available: betaagent" <<<"$OUT2"; then
    pass "209J CONTROL: raise the cap by one and the second specialist lands"
else
    fail "209J CONTROL: the second agent never fired, so the cap proved nothing: ${OUT2:0:400}"
fi
unset WORKLIST_AGENT_HINT_MAX_PER_SESSION
unset WORKLIST_REPORT_PER_STOP

# K. PRIORITY 3 NEVER DISPLACES A REAL SECTION, and this is the case to write
# first: it PROVES the noise control instead of asserting it. Every existing
# advisory is priority 2 or better and outq_drain releases one section per stop,
# so a hint reaches the operator only on a stop with nothing more important to
# say. That property costs nothing to obtain and is the whole reason this
# feature is not wallpaper.
setup
mk_agent fixtureagent "$HINT_DESC"
hint_fixture
brief_other cafe1234
touch -d '-48 hours' "$BASE/cafe1234.jsonl"
echo '- [ ] (cafe1234) their abandoned item' >>"$WL"
OUT="$(run)" # WORKLIST_REPORT_PER_STOP unset, so exactly one section is released
if [[ "$(hint_n "$OUT")" -eq 0 ]] &&
    grep -qE "INBOX HAS BEEN QUIET|ORPHANED item\(s\)|Other sessions in this worktree" <<<"$OUT" &&
    grep -qF "more report section(s) queued" <<<"$OUT"; then
    pass "209K a real advisory takes the slot, the hint waits, and the tail says so"
else
    fail "209K the hint displaced a real section, or nothing was queued: ${OUT:0:400}"
fi
# CONTROL, and it is what makes 209K a measurement rather than a coincidence:
# widen the drain on the very next stop and the hint is STILL THERE, so what
# 209K observed was a queued hint being outranked, not a hint that never fired.
export WORKLIST_REPORT_PER_STOP=6
newturn
say "$HINT_SAY"
OUT2="$(run)"
if grep -qF "Specialist agent available: fixtureagent" <<<"$OUT2"; then
    pass "209K CONTROL: the outranked hint was queued all along and drains next"
else
    fail "209K CONTROL: the hint was never queued at all: ${OUT2:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

# L. THE OPERATOR'S OWN SENTENCE, verbatim. REGRESSION 2026-08-15.
#
# "there is bench server deployment. Why you don't utilize it?" is the sentence
# that caused this feature to be built, and when the matcher was first wired up
# it returned NOTHING for it. The corpus carried `deploy`, `deploying` and
# `deploys` -- three variants of one verb, hand-enumerated -- and not
# `deployment`, so the query lost that hit to morphology, landed on `bench`
# alone at 1.0, and died against MIN_SCORE=2. The feature would have shipped
# unable to answer the only query we KNOW a real session needed.
#
# Pinned in the operator's words rather than a tidied paraphrase, because a
# paraphrase is written by the same hand that writes the matcher and drifts
# toward whatever the matcher already does.
#
# THE FIXTURE DESCRIPTION MUST NOT CONTAIN "deployment", and the case ASSERTS
# that rather than trusting it: if some future session "fixes" a red run here by
# pasting the query's word into the description, the assertion below goes red
# instead, which is the hand-maintained-variant-list staleness this fold exists
# to end.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent benchops "The bench rig: deploy the account worker to the bench box and reset its store."
# THE OPERATOR'S SENTENCE IS VERBATIM AND MUST STAY VERBATIM; what changed on
# 2026-08-27 is only the assistant framing around it. As a bare message it is a
# closing line that ends in `?` and addresses the operator, which is exactly the
# shape the v23 pending-ask gate refuses -- and a blocked stop emits no advisory,
# so this case went red on a gate that had nothing to do with agent hints. No
# real assistant message is a quoted operator question with nothing else in it;
# every term this case measures is still in the haystack, in the operator's own
# words and in the same order.
say "The operator asked: there is bench server deployment. Why you don't utilize it? Wiring the bench drill now."
brief_now
hand_now
OUT="$(run)"
if ! grep -qF "deployment" "$BASE/agents/benchops.md" &&
    grep -qF "Specialist agent available: benchops" <<<"$OUT"; then
    pass "209L the operator's literal sentence fires, on a description that never says 'deployment'"
else
    fail "209L the motivating query still does not fire, or the fixture was tautologised: ${OUT:0:400}"
fi
# CONTROL, and it is what makes 209L a measurement of MORPHOLOGY rather than of
# the word `bench`: `bench` on its own scores 1.0, below MIN_SCORE, and stays
# silent. So the hit that carried 209L over the floor can only have come from
# `deployment` folding onto the description's `deploy`.
newturn
say "there is a bench in the corridor and nobody has claimed it"
OUT="$(run)"
if [[ "$(hint_n "$OUT")" -eq 0 ]]; then
    pass "209L CONTROL: one discriminative term alone is still under the floor"
else
    fail "209L CONTROL: a single term cleared MIN_SCORE, so the floor is not holding: ${OUT:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 209M. counting words never route a dismissal to a specialist =="
# WHY THIS EXISTS. The specialist PUSHBACK ("You just claimed <label>, in a
# domain .claude/agents/<name>.md already covers") had no case at all, and it
# misrouted live: a session reporting "33 errors total, 32 pre-existing" about
# TypeScript in packages/www was sent to the LICENSING specialist, matched on
# the single token `total`, because licensing-ops' description happens to say
# "the total tier map" and `discriminative()` hands a term unique to one
# description that description at full weight.
#
# The dismissal DETECTION was right -- the claim was unproven, and pushing back
# on it found a real error in the session's own reporting. Only the routing was
# nonsense, and a hint that names the wrong specialist spends the reader's trust
# in every later hint. `total` is now a stopword; this is the case that keeps it
# one. Same failure class as `while` (media-pipeline) already in the list.
setup
export WORKLIST_REPORT_PER_STOP=4
mk_agent zorbops "Zorbium ledger reconciliation and the total sprocket cap."
newturn
say "the remaining failures are pre-existing: 32 errors total, none of them mine"
OUT="$(run)"
if grep -qF "already covers" <<<"$OUT"; then
    fail "209M a counting word routed a dismissal to a specialist: ${OUT:0:400}"
else
    pass "209M a counting word does not route a dismissal to an unrelated specialist"
fi
# CONTROL, POSITIVE PRESENCE FIRST, per the trap at case 208: an absence-only
# assertion passes just as well when the whole feature is suppressed. So prove
# the pushback still fires for the SAME fixture on genuinely discriminative
# vocabulary before trusting the silence above.
newturn
say "the zorbium ledger reconciliation cannot be tested locally"
OUT="$(run)"
if grep -qF "already covers" <<<"$OUT" && grep -qF "zorbops" <<<"$OUT"; then
    pass "209M CONTROL: the pushback still fires on real domain vocabulary"
else
    fail "209M CONTROL: the pushback is silent for the right claim too, so 209M proves nothing: ${OUT:0:400}"
fi
unset WORKLIST_REPORT_PER_STOP
