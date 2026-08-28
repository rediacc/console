#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# Door-parked wave reporting, the session-scoped block counter, and the answer-then-stand-down cadence with its guards.

echo "== 211. a DOOR-PARKED wave is reported, never blocked on =="
# _wave_rows deliberately emits nothing for a wave whose covering items were all
# closed through a door: the work did not happen, no session can make it happen,
# and demanding a tick would be demanding a lie. That reasoning is right, and it
# skipped the wave into TOTAL silence -- no violation, and its item is [x] so it
# has also left --list --open. Nothing surfaced it again, ever.
#
# Found 2026-08-15 when the operator asked why the stop hook had never mentioned
# an unticked w8. The honest answer was that the ONLY thing keeping it visible
# was a session remembering to write it into a report by hand.
setup
say "done for now

## Remaining
- nothing"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: mint the production secrets
MD
IID="$(reqcli --add deadbeef "cl:demo/w1 Wave A: mint the production secrets" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
reqcli --tick deadbeef "$IID" "door:operator-only -- secrets are write-only, exit 0" >/dev/null
OUT="$(run)"
DEC="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)"
if grep -qF "w1 [door:operator-only]" <<<"$OUT" && [[ "$DEC" != "block" ]]; then
    pass "211: a door-parked wave is REPORTED and does not block"
else
    fail "211: door-parked wave decision=$DEC out: ${OUT:0:400}"
fi

echo "== 211b. CONTROL: the same wave TICKED says nothing at all =="
# Without this the advisory could be firing on any unticked wave, or on every
# checklist regardless of state, and would read as noise within a day.
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: mint the production secrets
MD
OUT="$(run)"
if ! grep -qF "door:operator-only]" <<<"$OUT"; then
    pass "211b CONTROL: a ticked wave produces no door advisory"
else
    fail "211b CONTROL: the advisory fired on a TICKED wave: ${OUT:0:300}"
fi

echo "== 211c. CONTROL: closed WITHOUT a door is a different thing entirely =="
# An item ticked by DOING the work leaves the wave genuinely done-but-unticked,
# which is a VIOLATION with its own exit, not a door advisory. If this case ever
# starts printing the advisory, the door detector has stopped reading doors and
# is matching every closed item.
setup
say "done for now

## Remaining
- nothing"
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
MD
IID="$(reqcli --add deadbeef "cl:demo/w1 Wave A: wire the thing" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
reqcli --tick deadbeef "$IID" "wired it, suite green, exit 0" >/dev/null
OUT="$(run)"
if grep -qF "DONE-BUT-UNTICKED" <<<"$OUT" && ! grep -qF "door:" <<<"$OUT"; then
    pass "211c CONTROL: a doorless close is DONE-BUT-UNTICKED, not a door advisory"
else
    fail "211c CONTROL: ${OUT:0:400}"
fi

echo "== 213. the block counter is SESSION-SCOPED =="
# It was a single shared `.blocks` for the whole worktree. With ~48 addressable
# sessions here, one peer's clean allow deleted MY judge streak and one peer's
# block inflated it, so every decision keyed off the streak was reading someone
# else's work. Fixed before the cadence lands, because the cadence's cap is the
# next thing to key off block streaks.
setup
say "done for now"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
run >/dev/null
if [[ -f "${WL%.md}.blocks-deadbeef" ]]; then
    pass "213: the counter is written per-session as .blocks-deadbeef"
else
    fail "213: no per-session counter; found: $(ls "${WL%.md}".blocks* 2>&1)"
fi

echo "== 213b. CONTROL: a PEER's counter is untouched by my stop =="
# The whole point. Plant a peer's streak, take a stop of my own, and it must
# survive byte-for-byte -- under the old shared file my stop would have
# overwritten or deleted it.
printf '7' >"${WL%.md}.blocks-cafe1234"
run >/dev/null
if [[ "$(cat "${WL%.md}.blocks-cafe1234" 2>/dev/null)" == "7" ]]; then
    pass "213b CONTROL: a peer's block streak survives my stop unchanged"
else
    fail "213b CONTROL: peer streak became '$(cat "${WL%.md}.blocks-cafe1234" 2>/dev/null)'"
fi

echo "== 214. THE CADENCE: the hook stands down for ONE turn after being answered =="
# Operator's ask: "1 report/update 1 others/order flow". The acceptance test is
# the plan's own sentence -- the cadence must make it easier to be HEARD, not
# easier to STOP -- so every guard below exists because the naive version fails
# it. These are the ONLY cases that exercise the cadence: run() defaults it off.
setup
CADENCE=on
# THE FIXTURE CHANGED ON 2026-08-27 and the change is the case's subject now, so
# read this before "restoring" it. It used to be an OPEN ITEM plus a live worker,
# and it pinned that a session holding open work could be handed its quiet turn.
# The operator asked for the opposite: the pause message fires "too often. It
# should be the last chance, since we usually have lots to do!" So guard (E) --
# `not actionable_remains` -- now refuses the pause whenever there is an open
# item, a pending task or a live [>] lease, and the old fixture can no longer
# pause by construction. Keeping it here would have pinned a behaviour that was
# deliberately removed.
#
# What replaces it is a rotating violation with NOTHING actionable behind it: a
# reported-but-unfixed finding. That is the shape where a stand-down is still
# right -- the session has no work in hand, only a nag outstanding -- so this
# case still pins the cadence itself. Case 214f is the other half, and it is the
# old fixture with the opposite expectation.
FNF='- Agent finding I did not fix: the dead symlink under .ci'
say "answer

$FNF

## Remaining
- nothing outstanding"
brief_now
hand_now
check "214: the first stop still DEMANDS" block "finding(s) you did not fix"
newturn
say "I have now answered the demand

$FNF

## Remaining
- nothing outstanding"
OUT="$(run)"
DEC="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)"
if [[ "$DEC" != "block" ]] && grep -qF "still outstanding" <<<"$OUT"; then
    pass "214: the next stop is PAUSED, and still names what is outstanding"
else
    fail "214: decision=$DEC out: ${OUT:0:220}"
fi

echo "== 214b. GUARD B: an unchanged message buys NOTHING =="
# Without this a session emits an empty turn after every block and gets a free
# allow every other stop, which is the exact regression the cadence must not be.
# No `say` between stops here, so the assistant message is byte-identical.
setup
CADENCE=on
# Same non-actionable fixture as 214, for the same reason: with an open item the
# pause is refused by guard (E) and this case would pass without ever exercising
# guard B -- green, and proving nothing about the thing it is named after.
FNF='- Agent finding I did not fix: the dead symlink under .ci'
say "answer

$FNF

## Remaining
- nothing outstanding"
brief_now
hand_now
check "214b: first stop demands" block "finding(s) you did not fix"
# NO newturn HERE, and that is the correction rather than a shortcut. The old
# fixture called newturn with no say, which does not leave the message
# byte-identical at all: it resets the transcript window, so last_msg becomes
# EMPTY and its signature changes. That worked only because the violation was
# store-derived and survived an empty message; a message-derived one vanishes
# with the window, and the stop went clean. Running again on the same transcript
# is what "the assistant said nothing new" actually looks like to the hook.
check "214b GUARD B: no new say means no pause, it demands again" block "finding(s) you did not fix"

echo "== 214c. GUARD A: the ALWAYS tier defeats the pause =="
# The integrity tier is the reason this machinery exists. A session that just
# answered still does not get a quiet turn while something urgent is outstanding.
setup
CADENCE=on
# Non-actionable fixture, as 214: otherwise guard (E) refuses the pause first and
# this case stops testing guard A at all.
FNF='- Agent finding I did not fix: the dead symlink under .ci'
say "answer

$FNF

## Remaining
- nothing outstanding"
brief_now
hand_now
check "214c: first stop demands" block "finding(s) you did not fix"
newturn
say "answered, and now something urgent is also true

$FNF

## Remaining
- nothing outstanding"
# hook-blind is an always-tier violation: an unparseable event.
printf 'not json at all' >"$BASE/t.jsonl"
# stderr is CAPTURED, not discarded. This case failed once in CI with an EMPTY
# OUT and passed locally at 735/0, and a discarded stderr is precisely why that
# was undiagnosable: an empty stdout looks identical whether the hook decided to
# allow or died before deciding. A test that cannot say WHICH of those happened
# sends its reader guessing at a difference the machine already knew.
_214c_err="$BASE/214c.stderr"
OUT="$(printf 'garbage-not-json' | TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
    WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_AGENT_BRANCH=agenttest \
    WORKLIST_JUDGE=off WORKLIST_CADENCE=on GITHUB_ACTIONS="${GHA:-}" \
    python3 "$HOOK" 2>"$_214c_err")"
_214c_rc=$?
if grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "214c GUARD A: an always-tier violation blocks even when a pause was owed"
else
    fail "214c GUARD A: the always tier was paused: rc=${_214c_rc} stdout=[${OUT:0:220}] stderr=[$(tr '\n' ' ' <"$_214c_err" 2>/dev/null | tail -c 400)]"
fi

echo "== 214d. a CLEAN stop consumes the debt =="
# The hook owes a quiet turn to a session it just interrupted, not a voucher
# redeemable whenever that session next happens to be blocked. Found by case
# 3619: block, clean allow, new item -- and the new item was silently paused.
setup
CADENCE=on
# Non-actionable fixture, as 214. The debt is now spent by DROPPING the finding
# line rather than by ticking an item, which is the same three-stop shape:
# violation -> clean stop -> violation again.
FNF='- Agent finding I did not fix: the dead symlink under .ci'
say "answer

$FNF

## Remaining
- nothing outstanding"
brief_now
hand_now
check "214d: first stop demands" block "finding(s) you did not fix"
newturn
say "all done, and I fixed the symlink rather than reporting it

## Remaining
- nothing outstanding"
check "214d: the clean stop allows" allow ""
newturn
say "a fresh finding turned up

$FNF

## Remaining
- nothing outstanding"
check "214d: the NEW violation demands, the debt was spent on the clean stop" block "finding(s) you did not fix"

echo "== 214e. WORKLIST_CADENCE=off restores the old behaviour exactly =="
# The kill switch has to work, or there is no way back if this proves wrong in
# daily use.
setup
CADENCE=off
# Non-actionable fixture, as 214: with an open item this stop would block under
# guard (E) whatever the kill switch said, so the case could not tell the switch
# working from the switch being ignored.
FNF='- Agent finding I did not fix: the dead symlink under .ci'
say "answer

$FNF

## Remaining
- nothing outstanding"
brief_now
hand_now
check "214e: first stop demands" block "finding(s) you did not fix"
newturn
say "answered

$FNF

## Remaining
- nothing outstanding"
check "214e: with cadence OFF it demands again immediately" block "finding(s) you did not fix"

echo "== 214f. GUARD E: actionable work in hand REFUSES the pause =="
# The other half of 214, and the operator's actual complaint: "it fires too
# often. It should be the last chance, since we usually have lots to do!"
#
# This is 214's ORIGINAL fixture, verbatim -- an open item plus a live worker,
# so the always-tier idle-stall gate stands down ("a background worker is
# running") and `open-items` is the only outstanding check, rotating and
# therefore pausable under every guard except (E). Before (E) this stop was
# PAUSED, which is the exact turn the operator wanted back. Now it demands.
setup
CADENCE=on
BG='[{"status":"running","description":"agent"}]'
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214f: the first stop demands" block "OPEN worklist item"
newturn
say "I have now answered the demand

## Remaining
- stuff"
# ONE RUN, BOTH FACTS. The demand and the absence of the stand-down text have to
# be read off the SAME stop: a second check() call is a second stop, and after a
# pause the next stop blocks anyway, so a split assertion would pass on a fixture
# that had just paused. (It did, while this case was being written.)
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "OPEN worklist item" <<<"$OUT" &&
    ! grep -qF "but this stop is YOURS" <<<"$OUT"; then
    pass "214f GUARD E: an open item refuses the pause the message alone would earn"
else
    fail "214f GUARD E: the pause survived actionable work: ${OUT:0:300}"
fi

echo "== 214g. GUARD F: an unfinished MISSION refuses the pause =="
# The operator's sentence, made executable: "There should be list of 'has to
# show with this order' until we check all of them, we should not be able to say
# 'but this stop is YOURS'."
#
# Guard (E) already refuses the pause while there is an open item, a pending
# task or a live lease -- but that is "my queue is non-empty", which is not the
# same fact as "the job is done". The fixture below has an EMPTY board and an
# unticked program wave: nothing actionable in the worklist sense, and the thing
# the session was handed is plainly unfinished. Before (F) this stop was handed
# its quiet turn.
setup
CADENCE=on
brief_now
hand_now
cldeliver docs/demo/README.md "the readme"
clfile demo <<'MD'
# Handoff checklist: demo
Status: executing
Owner: deadbeef

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: the thing this session was handed
MD
say "answer

## Remaining
- nothing outstanding"
check "214g: the first stop demands the unticked wave" block "w1"
newturn
say "I have now answered the demand

## Remaining
- nothing outstanding"
# ONE RUN, BOTH FACTS, for the reason 214f states: after a pause the NEXT stop
# blocks anyway, so a split assertion passes on a fixture that had just paused.
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && ! grep -qF "but this stop is YOURS" <<<"$OUT"; then
    pass "214g GUARD F: an unfinished mission refuses the pause the message alone would earn"
else
    fail "214g GUARD F: the pause survived an unfinished mission: ${OUT:0:300}"
fi

echo "== 214h. CONTROL: the SAME fixture, mission SETTLED, pauses exactly as before =="
# Without this, 214g is satisfied by a hook that had simply stopped pausing.
# The wave is ticked and the checklist flipped done, so the only thing left is a
# rotating nag with nothing actionable behind it -- 214's own shape.
setup
CADENCE=on
brief_now
hand_now
FNF='- Agent finding I did not fix: the dead symlink under .ci'
say "answer

$FNF

## Remaining
- nothing outstanding"
check "214h: the first stop demands" block "finding(s) you did not fix"
newturn
say "I have now answered the demand

$FNF

## Remaining
- nothing outstanding"
OUT="$(run)"
DEC="$(python3 -c 'import json,sys
raw=sys.stdin.read().strip()
print(json.loads(raw).get("decision","allow") if raw else "allow")' <<<"$OUT" 2>/dev/null)"
if [[ "$DEC" != "block" ]] && grep -qF "still outstanding" <<<"$OUT"; then
    pass "214h CONTROL: with the mission settled the stand-down still works"
else
    fail "214h CONTROL: guard F swallowed the ordinary pause: decision=$DEC ${OUT:0:250}"
fi

echo "== 222. THE IDLE-STALL GATE: an open item, nobody carrying it, nothing moved =="
# WHY (operator, 2026-08-26): "it's very annoying that neither you have
# background agent nor running monitor/shell but you do stop even with remaining
# items! I see they're not blocked because of dependencies/questioning to me."
#
# `open-items` already existed and was already a violation -- it is in the
# ROTATING tier, which is what the cadence above is allowed to pause (case 214
# pins exactly that). So the observed loop was legal: block, say something new,
# get a pause, repeat. The v21 gate is the ALWAYS-tier backstop for the one
# shape where a pause is never right, and the controls below are the whole
# point: a gate that fires on every stop with an open item would be worse than
# none, because a session cannot tell an accusation from background noise.
setup
say "answer

## Remaining
- the thing"
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
# FIRST SIGHT NEVER FIRES: with no baseline there is no evidence about the turn.
check_quiet "222: the first stop takes a baseline and does not accuse" "ACTIONABLE WORK IN HAND"
newturn
say "still thinking about it

## Remaining
- the thing"
check "222: the SECOND idle stop is refused" block "YOU ARE STOPPING WITH ACTIONABLE WORK IN HAND"
check "222: and it states the rule positively" block "DONE, LEASED to a live worker, or [?] parked"

echo "== 222b. CONTROL: an item TICKED between the two stops is silent =="
# The single most important control. If this ever starts firing, the gate has
# stopped measuring progress and is just counting open items.
setup
say "answer

## Remaining
- two things"
brief_now
hand_now
reg_repo
echo '- [ ] (deadbeef) first thing' >>"$WL"
echo '- [ ] (deadbeef) second thing' >>"$WL"
run >/dev/null # baseline
sed -i "s|^- \[ \] (deadbeef) first thing|- [x] (deadbeef) first thing proof $(git -C "$BASE/proj" rev-parse --short HEAD)|" "$WL"
newturn
say "closed the first one

## Remaining
- second thing"
check_quiet "222b CONTROL: real progress leaves the gate silent" "ACTIONABLE WORK IN HAND"

echo "== 222c. CONTROL: an item moved to [?] with a DEFAULT is silent =="
setup
say "answer

## Remaining
- the decision"
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
run >/dev/null # baseline
sed -i 's|^- \[ \] (deadbeef) do the thing|- [?] (deadbeef) do the thing DEFAULT: do it on Monday|' "$WL"
newturn
say "parked it on you

## Remaining
- the decision"
check_quiet "222c CONTROL: parking on the operator is a legitimate stop" "ACTIONABLE WORK IN HAND"

echo "== 222d. CONTROL: every item LEASED to a live worker is silent =="
setup
say "answer

## Remaining
- delegated"
brief_now
hand_now
echo "- [>] (deadbeef) until:$(date -u -d '+30 minutes' +%Y-%m-%dT%H:%MZ) worker:w1 delegated to agent" >>"$WL"
BG='[{"id":"w1","status":"running","description":"agent"}]'
run >/dev/null
newturn
say "still running

## Remaining
- delegated"
check_quiet "222d CONTROL: a live lease is not a stall" "ACTIONABLE WORK IN HAND"

echo "== 222e. CONTROL: an open item WITH a running worker is silent =="
# Narrower than 222d on purpose: the operator's complaint names the absence of a
# background agent, so a session that HAS one is supervising, not stalling.
setup
say "answer

## Remaining
- the thing"
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
BG='[{"status":"running","description":"agent"}]'
run >/dev/null
newturn
say "the worker is on it

## Remaining
- the thing"
check_quiet "222e CONTROL: a running background worker suppresses the gate" "ACTIONABLE WORK IN HAND"

echo "== 222f. THE CADENCE CANNOT PAUSE IT (case 214f's fixture, minus the worker) =="
# The regression this whole gate exists for: an open item with NOBODY carrying
# it. Byte-for-byte case 214f, except no background worker -- which is what
# moves the refusal from the rotating `open-items` check to the always-tier
# idle-stall gate, and that is exactly the needle below. (This comment named
# case 214 until 2026-08-27; 214's fixture is non-actionable now, and 214f
# inherited the open-item-plus-worker shape.)
setup
CADENCE=on
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "222f: the first stop demands" block "OPEN worklist item"
newturn
say "I have now answered the demand

## Remaining
- stuff"
check "222f: saying something new no longer buys the pause" block "YOU ARE STOPPING WITH ACTIONABLE WORK IN HAND"

echo "== 222g. THE TELL: a Remaining line CLAIMING the item is unblocked =="
# The specific admission the operator caught: "Blocked on: nothing", written
# into the very section that is supposed to explain why the work has stopped.
setup
say "answer

## Remaining
- #a1 finish the migration -- blocked on: nothing, next up"
brief_now
hand_now
echo '- [ ] (deadbeef) finish the migration' >>"$WL"
BG='[{"status":"running","description":"agent"}]'
check "222g: the unblocked claim is refused even while a worker runs" block "CLAIMS an item has no blocker"

echo "== 222h. CONTROL: writing ABOUT the phrase does not trip it =="
# The V_FOUND_NOT_FIXED precedent: a gate that cannot survive being described is
# too broad, and every message discussing this check quotes its own trigger.
setup
say "answer

## Remaining
- the gate now refuses a line reading \`blocked on: nothing\` -- see the new case"
brief_now
hand_now
echo '- [ ] (deadbeef) finish the migration' >>"$WL"
BG='[{"status":"running","description":"agent"}]'
check_quiet "222h CONTROL: a backticked mention is not a claim" "CLAIMS an item has no blocker"

echo "== 222i. CONTROL: a bare '- nothing' Remaining is not a claim =="
# "## Remaining / - nothing" means the LIST is empty, which is the opposite of
# asserting that a listed item has no blocker. Matching it would fire the gate
# on the cleanest report shape in the suite.
setup
say "answer

## Remaining
- nothing"
brief_now
hand_now
echo '- [ ] (deadbeef) finish the migration' >>"$WL"
BG='[{"status":"running","description":"agent"}]'
check_quiet "222i CONTROL: an empty Remaining list is not an unblocked claim" "CLAIMS an item has no blocker"

echo "== 222j. THE FAILURE PATH: a raising gate must not wedge or wave through =="
# A check that throws is worse than one that is absent (case 99 makes the same
# point for the hook as a whole). Both guards are exercised: the wrapper at the
# call site, and closed_sig's own swallow.
setup
say "answer

## Remaining
- the thing"
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
CRASHDIR="$BASE/hookcrash"
mkdir -p "$CRASHDIR"
cp "$(dirname "$HOOK")"/*.py "$CRASHDIR/"
sed -i 's|^def idle_stall(|def idle_stall(*_a, **_k):\n    raise RuntimeError("planted idle_stall crash")\n\n\ndef _idle_stall_unused(|' "$CRASHDIR/wl_checks.py"
OUT="$(printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","session_crons":%s,"background_tasks":[]}' \
    "$SID" "$BASE/proj" "$BASE/t.jsonl" "$CRONS" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" WORKLIST_TASKS_DIR="$BASE/tasks" \
        WORKLIST_AGENT_BRANCH=agenttest WORKLIST_JUDGE=off WORKLIST_CADENCE=off \
        GITHUB_ACTIONS="${GHA:-}" python3 "$CRASHDIR/worklist.py" 2>"$BASE/222j.err")"
if grep -qF '"decision": "block"' <<<"$OUT" && grep -qF "OPEN worklist item" <<<"$OUT" &&
    ! grep -qF "planted idle_stall crash" <<<"$OUT"; then
    pass "222j: a raising gate is swallowed; open-items still blocks the stop"
else
    fail "222j: out=[${OUT:0:220}] err=[$(tail -c 200 "$BASE/222j.err" 2>/dev/null | tr '\n' ' ')]"
fi
# ...and the meta-control: the planted raise really was reachable. Without this,
# 222j passes on a sed that matched nothing.
if grep -qF 'planted idle_stall crash' "$CRASHDIR/wl_checks.py"; then
    pass "222j META: the planted crash was actually written into the copy"
else
    fail "222j META: the sed matched nothing, so 222j proved nothing"
fi
# closed_sig's own swallow, driven directly: an unreadable store must produce
# "unknown", never an exception and never an accusation.
if python3 - "$(dirname "$HOOK")" <<'PYEOF'; then
import sys

sys.path.insert(0, sys.argv[1])
import wl_checks


class Boom:
    @property
    def items(self):
        raise RuntimeError("unreadable store")


assert wl_checks.closed_sig(Boom(), "deadbeef") == ""
assert wl_checks.idle_stall({}, Boom(), "deadbeef", ["x"], [], []) == (False, "no baseline yet")
assert wl_checks.unblocked_claims(None) == []
assert wl_checks.unblocked_claims("## Remaining\n- blocked on: nothing") != []
PYEOF
    pass "222j: closed_sig/idle_stall/unblocked_claims survive an unreadable store"
else
    fail "222j: a helper raised on an unreadable store"
fi

echo "== 223. THE PENDING-ASK GATE: an ask ANNOUNCED and never made =="
# THE COST, as a sequence rather than an argument. A session writes "two
# questions for you" and stops. The operator spends a turn saying "ask". The
# session calls AskUserQuestion, and .claude/hooks/pre-ask/block-settled-
# questions.sh refuses it as something CLAUDE.md already answers. The removable
# cost is THE OPERATOR'S TURN, and a Stop hook that blocks is the only place in
# the chain that reaches it -- every later hook runs after the turn is gone.
#
# The detector is wl_admit.pending_ask; this file holds the controls because the
# gate is always-tier, exactly like idle-stall above, and for the same reason: a
# paused stop still ends the turn, so a rotating copy would buy nothing.
#
# PA_MSG IS DEFINED ONCE AND USED BY 223, 223b AND 223c VERBATIM. That is the
# anti-vacuity floor of this group: 223 blocks and 223b is silent, and the ONLY
# difference between them is the fixture state (one tool_use record). If the two
# messages differed as well, the pair would prove nothing about the detector --
# it would be consistent with a gate that simply matched different prose.
PA_MSG='Wave 3 landed and the suite is 810/0.

## Remaining
- nothing outstanding

Two questions for you before I pick the branch.'
setup
brief_now
hand_now
say "$PA_MSG"
check "223: an announced ask with no AskUserQuestion is refused" block "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT"
check "223: and it quotes the line it matched" block "Two questions for you before I pick the branch."
check "223: it offers asking now as an exit" block "call AskUserQuestion with the question, in this turn"
check "223: it offers parking it with a DEFAULT" block "worklist.py --defer deadbeef"
check "223: it offers settling it yourself" block "answer it yourself from the code"

echo "== 223b. CONTROL: the SAME message, with the ask actually made, is silent =="
# One byte of fixture state apart from 223: an assistant record whose only block
# is a tool_use for AskUserQuestion, in the same turn. used_tool() exists for
# this; say() writes text blocks only, so before it there was no way to fixture
# "the session called the tool" and this control could not have been written.
setup
brief_now
hand_now
used_tool AskUserQuestion
say "$PA_MSG"
check_quiet "223b CONTROL: asking it satisfies the gate" "YOU ANNOUNCED A QUESTION"

echo "== 223c. CONTROL: the SAME message, with a --defer this turn, is silent =="
# The second exit. The baseline stop is deliberate: without it the fixture would
# be silenced by defer_created's first-sight leniency instead of by the deferral,
# and the case would pass without exercising the signature at all.
setup
brief_now
hand_now
say "$PA_MSG"
PA_ID=$(reqcli --add deadbeef "the branch decision" | grep -oE '#[0-9a-f]+' | tr -d '#')
run >/dev/null # baseline: my [?] set is empty and banked as such
reqcli --defer deadbeef "$PA_ID" "which branch should this ride? DEFAULT: the branch of the PR that is already open WHY: a second PR is the operator's call, not a fact in the tree HOW: the operator names the branch, or the DEFAULT lands it on the open one" >/dev/null
check_quiet "223c CONTROL: parking it with a DEFAULT satisfies the gate" "YOU ANNOUNCED A QUESTION"

echo "== 223d. CONTROL: writing ABOUT the gate does not trip it =="
# The V_FOUND_NOT_FIXED precedent, and the reason wl_core.strip_quoted_spans is
# shared rather than copied: every message describing this gate quotes its own
# triggers, and a gate that cannot survive being written about is too broad.
setup
brief_now
hand_now
say 'Wired the new gate. It anchors on announcement, so it matches `two questions for you`, `your call` and `want me to` in the closing span, and ignores them inside backticks.

## Remaining
- nothing outstanding'
check_quiet "223d CONTROL: backticked triggers are not an announcement" "YOU ANNOUNCED A QUESTION"

echo "== 223e. CONTROL: an ordinary completion report is silent =="
setup
brief_now
hand_now
say 'Suite is 810/0. The ledger writes one row per refusal and the Stop advisory names the path.

## Remaining
- nothing outstanding'
check_quiet "223e CONTROL: a plain report is not an announcement" "YOU ANNOUNCED A QUESTION"

echo "== 223f. IT IS NOT SHADOWED BY ANOTHER ALWAYS-TIER VIOLATION =="
# Violations are gathered and emitted as ONE block, and the always tier is
# printed in full while everything else becomes a bare count. So a gate that
# computes correctly and is then swallowed by an earlier emit looks green
# forever. This fires the pending-ask gate WHILE idle-stall is live and demands
# BOTH texts -- the only assertion that can tell "computed" from "delivered".
setup
brief_now
hand_now
echo '- [ ] (deadbeef) do the thing' >>"$WL"
say "$PA_MSG"
run >/dev/null # idle-stall needs a baseline before it can accuse
newturn
say "$PA_MSG"
OUT="$(run)"
if grep -qF "YOU ANNOUNCED A QUESTION AND THEN STOPPED WITHOUT ASKING IT" <<<"$OUT" &&
    grep -qF "YOU ARE STOPPING WITH ACTIONABLE WORK IN HAND" <<<"$OUT"; then
    pass "223f: both always-tier texts are delivered, neither shadows the other"
else
    fail "223f: only one always-tier text survived: ${OUT:0:400}"
fi

echo "== 223g. THE FAILURE PATH: the detector's helpers never raise =="
# Same contract as 222j next door: a stall detector that crashes a stop is worse
# than one that is absent. The call site is wrapped; these are the helpers under
# it, driven directly on the inputs that would break a careless implementation.
if python3 - "$(dirname "$HOOK")" <<'PYEOF'; then
import sys

sys.path.insert(0, sys.argv[1])
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
# A tool_result user record is NOT the operator speaking, so it must not reset
# the tool window -- the whole reason this does not reuse transcript_tail.
assert not wl_admit._is_operator_turn(
    {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}
)
assert not wl_admit._is_operator_turn({"type": "user", "isMeta": True, "message": {"content": "hi"}})
assert wl_admit._is_operator_turn({"type": "user", "message": {"content": "go"}})
PYEOF
    pass "223g: defer_sig/pending_ask/turn_tools/ask_refusals survive bad input"
else
    fail "223g: a pending-ask helper raised"
fi

echo "== 223h. THE REFUSAL LEDGER: a refusal is recorded and then surfaced =="
# Before this the pre-ask hook refused questions and left NO trace anywhere the
# operator looks -- .claude/hooks/test-hooks.sh names the consequence itself: "a
# false positive is invisible by construction: the operator never learns what was
# not asked". This drives the real bash hook, then asserts the Stop advisory that
# reads what it wrote.
setup
brief_now
hand_now
say "done

## Remaining
- nothing outstanding"
PA_HOOK="$(cd "$(dirname "$HOOK")/../pre-ask" && pwd)/block-settled-questions.sh"
PA_LEDGER="${WL}.ask-refusals.jsonl"
printf '{"session_id":"%s","tool_input":{"questions":[{"question":"Should I commit this now?","header":"commit"}]}}' "$SID" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" bash "$PA_HOOK" >/dev/null 2>&1
PA_RC=$?
if [[ "$PA_RC" -eq 2 && -s "$PA_LEDGER" ]] &&
    grep -qF '"permission":"should i"' "$PA_LEDGER" && grep -qF '"object":"commit"' "$PA_LEDGER"; then
    pass "223h: a refusal appends one row naming BOTH matched conditions"
else
    fail "223h: rc=$PA_RC ledger=[$(head -c 200 "$PA_LEDGER" 2>/dev/null)]"
fi
# A question that is NOT permission-seeking must pass AND leave the ledger alone,
# or the count the advisory prints is meaningless.
printf '{"session_id":"%s","tool_input":{"questions":[{"question":"Which branch strategy fits this repo?","header":"design"}]}}' "$SID" |
    TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" bash "$PA_HOOK" >/dev/null 2>&1
PA_RC2=$?
if [[ "$PA_RC2" -eq 0 && "$(wc -l <"$PA_LEDGER")" -eq 1 ]]; then
    pass "223h: a design question passes and is NOT ledgered"
else
    fail "223h: rc=$PA_RC2 rows=$(wc -l <"$PA_LEDGER")"
fi
# ONE RUN, BOTH NEEDLES. A queued advisory is drained exactly once, so two
# check() calls would be two stops and the second would assert the absence of
# something it had already consumed -- a green test proving the opposite of what
# it reads like.
export WORKLIST_REPORT_PER_STOP=9
OUT="$(run)"
if grep -qF "were REFUSED by" <<<"$OUT" && grep -qF ".ask-refusals.jsonl" <<<"$OUT" &&
    ! grep -qF '"decision": "block"' <<<"$OUT"; then
    pass "223h: the Stop hook surfaces the ledger by path, advisory and non-blocking"
else
    fail "223h: the ledger advisory did not surface: ${OUT:0:300}"
fi
unset WORKLIST_REPORT_PER_STOP

echo "== 223i. CONTROL: no refusals means no advisory =="
# A surface that speaks when the count is zero is noise, and noise is what the
# rotation exists to prevent.
setup
brief_now
hand_now
say "done

## Remaining
- nothing outstanding"
export WORKLIST_REPORT_PER_STOP=9
check_quiet "223i CONTROL: an empty ledger says nothing" "were REFUSED by"
unset WORKLIST_REPORT_PER_STOP
