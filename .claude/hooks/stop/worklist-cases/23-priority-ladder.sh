#!/bin/bash
# Part of the worklist v5 control suite. SOURCED by
# `.claude/hooks/stop/test-worklist-v5.sh`, never run on its own: the harness
# (setup, check, run, the PASS/FAIL counters) lives in `_harness.sh` and every
# fixture path comes from the runner. Running this file directly does nothing
# useful and is not how CI reaches it.
#
# THE PRIORITY LADDER (wl_checks.PRIORITY_LADDER): the ordered, mandatory list
# that decides which outstanding check a crowded stop actually surfaces, the
# invariant tier's collapse, and the pr-babysit finish line.
#
# WHY THIS FILE EXISTS. Rotation used to break ties on the position of a `vadd`
# call in a 5,000-line file, and every never-served key ties at -1, so line
# order decided the FIRST pick of every crowded session. Nothing tested that,
# because line order is not a behaviour anyone thinks to assert -- which is how
# "you asked a peer and nothing is listening" came to sort 24th while its
# escalation ladder burned a rung per stop, unseen.

echo "== 230. THE PROVING CASE: a crowded session still hears NOT LISTENING on the FIRST stop =="
# The one case this whole change is for. Before the ladder this FAILED: with an
# open ask plus five unrelated rotating violations, `no-waiter-asked` sorted
# 23rd behind open-items, brief, agent-state and the rest, so the first stop
# surfaced the worklist queue and the ask ladder advanced a rung nobody saw.
#
# Every violation below is planted deliberately, and the count is asserted
# rather than assumed: a "crowded" fixture that turned out to hold two checks
# would pass on the old code too and prove nothing.
setup
# A work loop with NO poll cron: that is `no-poll`, and it is also what makes
# the ask-ladder reachable at all (a poll cron is a listener, just a slower one).
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
brief_other peer1234
# NO brief_now  -> `brief`
# NO hand_now   -> `agent-state`
echo '- [ ] (deadbeef) the thing I was actually asked to do' >>"$WL" # open-items
ASK230="$(askid deadbeef peer1234 'which baseline do we measure against?')"
say "I looked at it.

- Agent finding I did not fix: the dead symlink under .ci"
OUT="$(run)"
N230="$(sed -n 's/.*Stop hook: \([0-9]*\) check(s) outstanding.*/\1/p' <<<"$OUT" | head -1)"
if [[ -n "$ASK230" && "${N230:-0}" -ge 6 ]]; then
    pass "230 premise: the fixture really is crowded ($N230 checks outstanding, ask #$ASK230)"
else
    fail "230 premise: fixture is not crowded (n='$N230' ask='$ASK230'): ${OUT:0:300}"
fi
if grep -qF "NOT LISTENING FOR THE ANSWER" <<<"$OUT"; then
    pass "230 THE PROVING CASE: the ask ladder is heard on the FIRST stop, not the 24th"
else
    fail "230 THE PROVING CASE: buried behind the rotating queue again: ${OUT:0:400}"
fi
# RUNG 1, not rung 5. The old failure was not only that the text was late: the
# counter bumped at COMPUTE time, so by the time a crowded session saw the check
# it was already at the terminal rung claiming "it has now asked 5 times" about a
# question asked once. As an invariant, compute and display coincide.
if grep -qF "YOU ASKED 1 QUESTION AND ARE NOT LISTENING" <<<"$OUT"; then
    pass "230: the FIRST sighting is rung 1, so rungs 2-4 are reachable at all"
else
    fail "230: the first sighting was not rung 1: ${OUT:0:400}"
fi

echo "== 230b. CONTROL: the compliant shape stays silent in the SAME crowd =="
# The check must be silenced by listening, not by the crowd thinning. Identical
# fixture with one difference: a 5-minute poll cron, which V_NO_WAITER's own
# text calls the slower-but-real alternative to a waiter.
setup
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"},{"id":"p","schedule":"*/5 * * * *"}]'
brief_other peer1234
echo '- [ ] (deadbeef) the thing I was actually asked to do' >>"$WL"
askid deadbeef peer1234 'which baseline do we measure against?' >/dev/null
say "I looked at it.

- Agent finding I did not fix: the dead symlink under .ci"
OUT="$(run)"
if grep -qF '"decision": "block"' <<<"$OUT" && ! grep -qF "NOT LISTENING FOR THE ANSWER" <<<"$OUT"; then
    pass "230b CONTROL: with a listener armed the ladder says nothing, and the stop still blocks on the rest"
else
    fail "230b CONTROL: fired at a session that IS listening: ${OUT:0:400}"
fi

echo "== 231. THE LADDER DECIDES THE FIRST PICK, where line order used to =="
# "There should be list of 'has to show with this order' until we check all of
# them."
#
# READ THE SORT KEY IN wl_checks BEFORE CHANGING THIS CASE. Tier sits AFTER
# `served`, not before it, so the ladder is WALKED rather than camped on: on the
# first stop every key is unserved and tier decides, and afterwards the
# least-recently-served wins with tier breaking its ties. Camping on the top
# tier would starve docs drift, a stale PR body and an unpushed submodule
# pointer for as long as one item is open -- which is most of a session. The
# part of the operator's ask that starvation was reaching for is delivered by
# guard (F) instead: T_MISSION defeats the cadence pause, so the session is
# never RELEASED while the job is unfinished (case 214g).
#
# Two rotating checks, one T_MISSION and one T_HYGIENE, both never served. The
# mission one must go first -- under the old tiebreak that was decided by which
# `vadd` call sat earlier in a 5,000-line file.
setup
hand_now                                         # so `agent-state` is not a third check
echo '- [ ] (deadbeef) the mission item' >>"$WL" # T_MISSION: open-items
# no brief_now                 # T_HYGIENE: the session brief
say "status update

## Remaining
- the mission item (mine)"
S1="$(run)"
newturn
say "status update again

## Remaining
- the mission item (mine)"
S2="$(run)"
_m1=$(grep -qF "OPEN worklist item" <<<"$S1" && echo y || echo n)
_m2=$(grep -qF "OPEN worklist item" <<<"$S2" && echo y || echo n)
if [[ "$_m1" == "y" ]]; then
    pass "231: the FIRST pick of a crowded stop is the mission tier, not the earliest vadd"
else
    fail "231: the first pick was not the mission item: ${S1:0:300}"
fi
if [[ "$_m2" == "n" ]]; then
    pass "231 CONTROL: the ladder is WALKED, not camped on -- stop 2 moves down a tier"
else
    fail "231 CONTROL: the mission tier starved the hygiene tier: ${S2:0:300}"
fi

echo "== 231b. the same two checks, ORDER REVERSED by the ladder, not by line number =="
# The assertion above is only meaningful if the opposite arrangement produces
# the opposite first pick for the same reason. `brief` is defined EARLIER in the
# battery than several mission checks, so under the old line-order tiebreak a
# hygiene check could and did win a first pick. Here the only mission member is
# a checklist wave, whose `vadd` sits ~500 lines BELOW `brief` -- so line order
# would pick the brief and the ladder must not.
setup
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
say "status update

## Remaining
- nothing"
OUT="$(run)"
if grep -qF "w1" <<<"$OUT" && ! grep -qF "session brief is missing" <<<"$OUT"; then
    pass "231b: a mission check defined LATER in the battery still wins the first pick"
else
    fail "231b: line order is still deciding the first pick: ${OUT:0:300}"
fi

echo "== 232. THE COLLAPSE: three invariants, two quoted, the third NAMED =="
# The invariant tier buys UN-ROTATABILITY and nothing more. This file's own
# warning -- "a prompt that fires always is a prompt that gets skimmed" -- is the
# constraint, and three promotions in one change is exactly when it bites.
# NOTHING IS DROPPED: the third is named on one line with its opening sentence.
setup
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
brief_now
hand_now
brief_other peer1234
# invariant 1: a peer's request addressed to me.
askid_as peer1234 deadbeef 'please confirm the baseline number' >/dev/null
# invariant 2: my own open ask with nothing listening.
askid deadbeef peer1234 'which baseline do we measure against?' >/dev/null
# invariant 3: an unread teammate report old enough to have graduated.
python3 - "$BASE/reports" <<'PYEOF'
import json, pathlib, sys
store = pathlib.Path(sys.argv[1])
(store / "agenttest").mkdir(parents=True, exist_ok=True)
(store / "agenttest" / "r.md").write_text("A TEAMMATE FINDING NOBODY READ\nbody")
(store / "index.jsonl").write_text(json.dumps({
    "ev": "report", "id": "abcdef123456", "at": "2026-01-01T10:00:00Z",
    "branch": "agenttest", "agent": "some-teammate", "type": "some-teammate",
    "session": "deadbeef", "body": "agenttest/r.md", "bytes": 900,
    "silent": False, "sends": 1, "title": "A TEAMMATE FINDING NOBODY READ",
    "transcript": "", "src": "hook"}) + "\n")
PYEOF
say "status"
OUT="$(run)"
if grep -qF "ALSO BLOCKING, IN BRIEF" <<<"$OUT"; then
    pass "232: with three invariants outstanding the excess is collapsed, not repeated in full"
else
    fail "232: no collapse block with three invariants: ${OUT:0:400}"
fi
# NOTHING SILENTLY DROPPED. Every one of the three is present, in full or as a
# named line; this is the assertion that separates a collapse from a truncation.
#
# THE NEEDLES ARE HEADLINES, NOT KEYS, and that is not a stylistic choice: a
# QUOTED invariant renders its message, which never contains its own key, so
# grepping for `unread-reports` passed only for whichever one got collapsed --
# an assertion that would have gone green on a hook that dropped the other two.
# A headline matches both ways, because the collapse line is exactly
# "<key>: <that message's first line>".
ok232=1
for needle in "cross-session REQUEST(S) are waiting on you" \
    "NOT LISTENING FOR THE ANSWER" "UNREAD SUB-AGENT REPORTS"; do
    grep -qF "$needle" <<<"$OUT" || {
        ok232=0
        echo "        MISSING: $needle"
    }
done
if [[ "$ok232" == 1 ]]; then
    pass "232: all three invariants are still named on the same stop"
else
    fail "232: the collapse DROPPED an invariant instead of naming it"
fi

echo "== 232b. CONTROL: two invariants are both quoted, with no collapse line =="
# ALWAYS_FULL_MAX is 2, so at the boundary the block must look exactly as it did
# before this change. A collapse that fired at two would be a regression wearing
# the new feature's clothes.
setup
CRONS='[{"id":"c1","schedule":"*/30 * * * *","prompt":"work loop"}]'
brief_now
hand_now
brief_other peer1234
askid_as peer1234 deadbeef 'please confirm the baseline number' >/dev/null
askid deadbeef peer1234 'which baseline do we measure against?' >/dev/null
say "status"
OUT="$(run)"
if grep -qF "NOT LISTENING FOR THE ANSWER" <<<"$OUT" &&
    ! grep -qF "ALSO BLOCKING, IN BRIEF" <<<"$OUT"; then
    pass "232b CONTROL: at exactly ALWAYS_FULL_MAX both are quoted in full and nothing collapses"
else
    fail "232b CONTROL: the boundary is wrong: ${OUT:0:400}"
fi

echo "== 233. THE pr-babysit FINISH LINE blocks a GREEN-BUT-UNFINISHED wave =="
# The operator's example, generalised: reaching green is not reaching the finish
# line. `.claude/commands/pr-babysit.md` states it -- "The console PR rides as a
# draft until green; stops at green + Claude-reviewed + threads-resolved PRs" --
# and before this change nothing held the wave open once ci-red went quiet.
ci_setup
mkdir -p "$BASE/projects/reports"
prf_log() { # (re)write the fixture round log -- APPEND ONLY, see the note below
    # `rm` then `>>`, never `>`. block-roundlog-truncate.sh refuses any command
    # that could replace a pr-babysit round log wholesale, and it is right to:
    # a `>` here is byte-for-byte the shape that destroyed a real round history
    # on 2026-08-19. A fixture is not an exception worth carving.
    rm -f "$BASE/projects/reports/pr-babysit-agenttest.md"
    printf '## Wave header\nintent: the thing\n\n## STATUS (round %s)\nwatching\n' \
        "$1" >>"$BASE/projects/reports/pr-babysit-agenttest.md"
}
prf_run() { # a Stop event with the CI check armed AND a projects dir
    python3 -c '
import json, sys
print(json.dumps({"session_id": sys.argv[1], "cwd": sys.argv[2],
                  "last_assistant_message": sys.argv[3], "session_crons": [],
                  "background_tasks": []}))' \
        "$SID" "$BASE/proj" "${CIMSG:-work done}" |
        PATH="$BASE/binonly:$PATH" TMPDIR="$BASE/tmp" CLAUDE_PROJECT_DIR="$BASE/proj" \
            WORKLIST_TASKS_DIR="$BASE/tasks" WORKLIST_PUBLISH_REF=pub \
            WORKLIST_PROJECTS_DIR="$BASE/projects" \
            WORKLIST_JUDGE=off GITHUB_ACTIONS="${GHA:-}" python3 "$HOOK" 2>"$BASE/err.txt"
}
prf_log 3
ci_rollup SUCCESS "[$(ci_job "Quality / Static" SUCCESS)]"
OUT="$(prf_run)"
# `--` before the pattern, deliberately: `grep -qF "- [x] green"` reads the
# leading dash as an option bundle and dies with "invalid option", which prints
# to stderr and returns non-zero -- i.e. it looks exactly like a legitimate
# assertion failure. Every box assertion in this file quotes a markdown checkbox,
# so this is the whole file's hazard, not one line's.
if grep -qF "THE WAVE IS NOT FINISHED" <<<"$OUT" && grep -qF -- "- [x] green" <<<"$OUT" &&
    grep -qF "pr:543/reviewed" <<<"$OUT"; then
    pass "233: a green PR with the review boxes unticked keeps the wave open, as markdown boxes"
else
    fail "233: the finish line did not hold a green-but-unfinished wave: ${OUT:0:500}"
fi

echo "== 233b. CONTROL: no round log for this branch, not one word =="
# The gate that stops this becoming a tax on every session that happens to have
# a PR open. Same PR, same green, no pr-babysit wave.
rm -f "$BASE/projects/reports/pr-babysit-agenttest.md"
OUT="$(prf_run)"
if ! grep -qF "THE WAVE IS NOT FINISHED" <<<"$OUT"; then
    pass "233b CONTROL: without a pr-babysit round log the finish line is silent"
else
    fail "233b CONTROL: fired at a session running no wave at all: ${OUT:0:400}"
fi

echo "== 233c. the last two boxes are TICKED BY EVIDENCE, and then it stops =="
# The hook cannot see a review marker or a resolved thread, and refuses to
# pretend it can: the boxes are closed by ticking a worklist item carrying the
# token, which is the same linkage agent/programs/<slug>/CHECKLIST.md uses.
prf_log 4
R233="$(reqcli --add deadbeef "pr:543/reviewed request the Claude review" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
T233="$(reqcli --add deadbeef "pr:543/threads resolve the review threads" | grep -o '#[0-9a-f]*' | head -1 | tr -d '#')"
# FOCUS=off, and the reason is worth stating: adding the two claim items makes
# `open-items` and the idle-stall gate outstanding too, and the focused block
# surfaces ONE rotating check per stop. Asserting the finish line's text through
# a rotation would be asserting the rotation, not the box. This case is about
# what the finish line SAYS about an open claim, so it reads the dump-all block.
CIMSG="work done" WORKLIST_FOCUS=off
export WORKLIST_FOCUS
OUT="$(prf_run)"
if grep -qF -- "- [ ] Claude-reviewed" <<<"$OUT"; then
    pass "233c: an OPEN item carrying the token is a claim, not a tick"
else
    fail "233c: an open claim ticked the box: ${OUT:0:400}"
fi
reqcli --tick deadbeef "$R233" "https://github.com/fake/repo/pull/543#pullrequestreview-1" >/dev/null
reqcli --tick deadbeef "$T233" "https://github.com/fake/repo/pull/543#discussion_r1 resolved" >/dev/null
OUT="$(prf_run)"
unset WORKLIST_FOCUS
if ! grep -qF "THE WAVE IS NOT FINISHED" <<<"$OUT"; then
    pass "233c: with all four boxes ticked the finish line goes quiet"
else
    fail "233c: still blocking after the wave finished: ${OUT:0:400}"
fi
unset -f prf_run prf_log
