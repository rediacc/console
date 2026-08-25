#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# The runner no-op, the stuck-stop counter and what counts as movement, and the cited-blocker requirement.

echo "== 46. CONTROL: an open item still blocks off a runner =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
printf -- '- [ ] (deadbeef) an item nobody will ever answer\n' >>"$WL"
check "an open item blocks in a normal session" block "OPEN worklist item"

echo "== 47. and the SAME state no-ops under GITHUB_ACTIONS =="
# Same worklist, same open item, one env var different. Without the control
# above this would pass even if the hook had stopped blocking entirely.
GHA=true check "GITHUB_ACTIONS=true never blocks a runner" allow ""

echo "== 48. a value other than 'true' is NOT a runner =="
GHA=false check "GITHUB_ACTIONS=false still blocks" block "OPEN worklist item"

echo "== 49. CONTROL: two identical stops do NOT trip the stuck check =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "stop 1 of 3 is quiet" allow ""
check "stop 2 of 3 is still quiet" allow ""

echo "== 50. the THIRD identical stop demands an agent =="
check "3 stops with nothing moved blocks" block "EMPLOY A PLANNING OR INVESTIGATION AGENT"

echo "== 51. and it RESETS, so stop 4 is quiet again =="
check "the nag is rate-limited, not every-stop" allow ""

# 51b. THE DEFERRAL BLIND SPOT. The stuck check used to fire on
# `something_remains`, which counts `[?]` deferrals. A `[?]` is BY CONSTRUCTION
# the one shape a session cannot advance -- it is parked on the operator's
# decision or on a capability only they hold -- so "nothing moved" is the
# CORRECT outcome there, not a stall, and the remedy the check prints (delegate
# to a Plan/Explore agent) cannot work: the constraint is authority, not
# knowledge. Measured 2026-08-15, the two survivors were "set four Worker
# secrets with the operator's Cloudflare session" and "delete the last restore
# path once a machine has round-tripped a repo". The only way to satisfy the
# check was to spawn a decorative agent, i.e. to game it.
#
# `[>]` deliberately still counts as actionable (case 53 covers it): work on a
# worker genuinely can stall, and the bg-wait check reports that separately.
echo "== 51b. CONTROL: with ONLY [?] deferrals left, the stuck check stays quiet =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | blocked on the operator | deferred |"
echo '- [?] (deadbeef) set the four Worker secrets DEFAULT: hold, it needs the operator session' >>"$WL"
check "deferral-only stop 1 is quiet" allow ""
check "deferral-only stop 2 is quiet" allow ""
# The third identical stop is where case 50 fires. It must NOT here.
check "deferral-only stop 3 does NOT demand an agent" allow ""

echo "== 51c. and one OPEN item alongside the deferral restores the demand =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
echo '- [?] (deadbeef) a parked question DEFAULT: hold' >>"$WL"
echo '- [ ] (deadbeef) something I can actually do' >>"$WL"
# An open item blocks EVERY stop on its own account, so these two assert the
# OTHER blocker by name -- the point is that the stuck demand is absent until
# the third stop, and then present.
check "mixed stop 1 blocks on the open item, not the stuck check" block "OPEN worklist item"
check "mixed stop 2 blocks on the open item, not the stuck check" block "OPEN worklist item"
check "an actionable item alongside a deferral still trips it" block "EMPLOY A PLANNING OR INVESTIGATION AGENT"

echo "== 52. a task changing status counts as movement =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "fresh signature, stop 1" allow ""
check "fresh signature, stop 2" allow ""
# Same session, but the task moved. The counter must restart, not fire.
task 7 in_progress "thing"
newturn
say "answer

## Remaining
| #7 | thing | ongoing, me |"
check "moving a task resets the stuck counter" allow ""

echo "== 53. a running background task exempts it (an agent IS the remedy) =="
setup
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
BG='[{"status":"running","description":"plan agent"}]'
BG="$BG" check "stop 1" allow ""
BG="$BG" check "stop 2" allow ""
BG="$BG" check "a live agent means the remedy is already running" allow ""

echo "== 54. THE MISSING CONTROL: a COMMIT must move the signature =="
# Its absence is why a dead HEAD leg shipped. The hook resolved the repo from
# the worklist tmp dir, git returned nothing, and every commit was invisible.
setup
git -C "$BASE/proj" init -q 2>/dev/null
git -C "$BASE/proj" config user.email t@t
git -C "$BASE/proj" config user.name t
echo one >"$BASE/proj/f"
git -C "$BASE/proj" add f
git -C "$BASE/proj" commit -qm one
brief_now
hand_now
say "answer

## Remaining
| #7 | thing | pending, me |"
task 7 pending "thing"
check "stop 1" allow ""
check "stop 2" allow ""
# A real commit between stops. If HEAD is wired, this resets tasks+head.
echo two >>"$BASE/proj/f"
git -C "$BASE/proj" commit -qam two
newturn
say "answer

## Remaining
| #7 | thing | pending, me |"
check "a commit resets the tasks+head counter" allow ""

echo "== 55. but a commit buys SLACK, not immunity: tasks-only still fires =="
# Commit every round; the tasks-only signature never moves, so at 2x it fires.
# case 54 already spent 3 stops; tasks-only fires at 2x STUCK_ROUNDS = 6, so
# exactly 3 more land ON the fire rather than past its reset.
for i in 4 5 6; do
    echo "c$i" >>"$BASE/proj/f"
    git -C "$BASE/proj" commit -qam "c$i"
    newturn
    say "answer

## Remaining
| #7 | thing | pending, me |"
    LAST="$(run)"
done
if grep -qF "EMPLOY A PLANNING OR INVESTIGATION AGENT" <<<"$LAST" &&
    grep -qF "Commits do not count as movement here" <<<"$LAST"; then
    echo "  PASS: the commit-trivia treadmill still trips the tasks-only tier"
    PASS=$((PASS + 1))
else
    echo "  FAIL: committing every round escaped the stuck check"
    echo "        out: ${LAST:0:220}"
    FAIL=$((FAIL + 1))
fi

echo "== 56. THE WAVE C REPLAY: an uncited prose blocker blocks =="
setup
brief_now
hand_now
# The exact line that started this, verbatim in shape.
say "answer

## Remaining
| #12 | Wave C autopilot | blocked on Wave B landing |"
task 12 pending "Wave C autopilot"
check "an uncited blocker blocks" block "carries no <path>:<line> citation"

echo "== 57. citing a REAL line clears it =="
setup
brief_now
hand_now
mkdir -p "$BASE/proj/docs"
printf 'a\nb\nc\nd\ne\n' >"$BASE/proj/docs/guide.md"
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/guide.md:3 |"
task 12 pending "Wave C autopilot"
check "a citation that resolves is accepted" allow ""

echo "== 58. CONTROL: a citation past end-of-file is NOT accepted =="
setup
brief_now
hand_now
mkdir -p "$BASE/proj/docs"
printf 'a\nb\nc\nd\ne\n' >"$BASE/proj/docs/guide.md"
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/guide.md:900 |"
task 12 pending "Wave C autopilot"
check "a fabricated line number is caught" block "has only 5 lines"

echo "== 59. CONTROL: a citation to a file that does not exist is NOT accepted =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, docs/nope.md:3 |"
task 12 pending "Wave C autopilot"
check "an invented path is caught" block "which does not exist"

echo "== 60. a live background task exempts the citation requirement =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked on the agent |"
task 12 pending "Wave C autopilot"
BG='[{"status":"running","description":"agent"}]'
check "real machinery needs no prose citation" allow ""

echo "== 61. 'blocked on you' keeps its own check, not this one =="
setup
brief_now
hand_now
say "answer

## Remaining
| #12 | Wave C autopilot | blocked, You (User Thinks So) |"
task 12 pending "Wave C autopilot"
check "an operator blocker is not asked for a file citation" allow ""

echo "== 62. the judge is HANDED the cited text, not just told a path =="
# citation_state only proves a source EXISTS, which any real file satisfies.
# This is the half that lets the judge check whether the source says what the
# session claimed. Tested directly now that the module is importable.
setup
mkdir -p "$BASE/proj/docs"
printf 'alpha\nbravo\nLands with every stage flag off\ndelta\necho\n' >"$BASE/proj/docs/g.md"
OUT=$(cd "$BASE/proj" && python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.cited_excerpts(".", "blocked on Wave B landing, docs/g.md:3"))
' "$HOOK" 2>&1)
if grep -qF "Lands with every stage flag off" <<<"$OUT" && grep -qF ">3|" <<<"$OUT"; then
    echo "  PASS: the cited line is quoted and marked"
    PASS=$((PASS + 1))
else
    echo "  FAIL: excerpt missing or unmarked: ${OUT:0:200}"
    FAIL=$((FAIL + 1))
fi

echo "== 63. CONTROL: importing the hook must NOT run the Stop path =="
# The bare main() call meant any import executed the whole hook. If that
# regresses, case 62 silently tests a hook run instead of a function.
if grep -qF "no such option" <<<"$OUT" || grep -qF '"decision"' <<<"$OUT"; then
    echo "  FAIL: import executed main(); the module is not importable"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: import is side-effect free"
    PASS=$((PASS + 1))
fi

echo "== 64. CONTROL: a citation past EOF yields no excerpt, never a crash =="
OUT2=$(cd "$BASE/proj" && python3 -c '
import importlib.util, sys
spec = importlib.util.spec_from_file_location("wl", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("EXCERPT[" + m.cited_excerpts(".", "blocked, docs/g.md:900 and docs/nope.md:2") + "]")
' "$HOOK" 2>&1)
if grep -qF "EXCERPT[]" <<<"$OUT2"; then
    echo "  PASS: out-of-range and missing files quote nothing"
    PASS=$((PASS + 1))
else
    echo "  FAIL: expected an empty excerpt, got: ${OUT2:0:200}"
    FAIL=$((FAIL + 1))
fi
