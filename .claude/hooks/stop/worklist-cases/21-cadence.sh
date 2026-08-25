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
