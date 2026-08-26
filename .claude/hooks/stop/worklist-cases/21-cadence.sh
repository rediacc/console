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
# A LIVE WORKER, added with the v21 idle-stall gate (case 222). That gate is in
# the ALWAYS tier, so an open item with nobody carrying it now defeats the pause
# by design -- which would turn this case into a test of the new gate instead of
# a test of the cadence. A running worker is the shape where a pause is still
# legitimate (someone IS moving the work), so this case keeps pinning the thing
# it was written to pin. Case 222f asserts the other half: strip the worker from
# this exact fixture and the pause is refused.
BG='[{"status":"running","description":"agent"}]'
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214: the first stop still DEMANDS" block "OPEN worklist item"
newturn
say "I have now answered the demand

## Remaining
- stuff"
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
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214b: first stop demands" block "OPEN worklist item"
newturn
check "214b GUARD B: no new say means no pause, it demands again" block "OPEN worklist item"

echo "== 214c. GUARD A: the ALWAYS tier defeats the pause =="
# The integrity tier is the reason this machinery exists. A session that just
# answered still does not get a quiet turn while something urgent is outstanding.
setup
CADENCE=on
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214c: first stop demands" block "OPEN worklist item"
newturn
say "answered, and now something urgent is also true

## Remaining
- stuff"
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
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214d: first stop demands" block "OPEN worklist item"
sed -i 's/^- \[ \] (deadbeef) open thing/- [x] (deadbeef) open thing/' "$WL"
newturn
say "all done

## Remaining
- nothing"
check "214d: the clean stop allows" allow ""
echo '- [ ] (deadbeef) a brand new thing' >>"$WL"
newturn
say "starting the new thing

## Remaining
- the new thing"
check "214d: the NEW item demands, the debt was spent on the clean stop" block "OPEN worklist item"

echo "== 214e. WORKLIST_CADENCE=off restores the old behaviour exactly =="
# The kill switch has to work, or there is no way back if this proves wrong in
# daily use.
setup
CADENCE=off
say "answer

## Remaining
- stuff"
brief_now
hand_now
echo '- [ ] (deadbeef) open thing' >>"$WL"
check "214e: first stop demands" block "OPEN worklist item"
newturn
say "answered

## Remaining
- stuff"
check "214e: with cadence OFF it demands again immediately" block "OPEN worklist item"

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

echo "== 222f. THE CADENCE CANNOT PAUSE IT (case 214's fixture, minus the worker) =="
# The regression this whole gate exists for. Byte-for-byte case 214, except no
# background worker: 214 gets its pause, this must not.
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
