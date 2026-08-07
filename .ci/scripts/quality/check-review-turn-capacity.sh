#!/usr/bin/env bash
# Assert the Claude-review turn budget cannot starve a review it is willing to route.
#
# WHY THIS EXISTS. On 2026-08-07 the review of PR #553 died with `error_max_turns` and
# posted ZERO findings, then recorded a SPENT ATTEMPT -- burning a finite allowance while
# claiming nothing about the code. Two samples from that day, same reviewer, same tier:
#
#     PR #552  2270 lines / 39 files  -> completed, full report
#     PR #553  2802 lines / 36 files  -> starved, nothing posted
#
# The 50-turn tier stretched to 5000 lines, so a 4999-line diff was routed with 10 turns
# per 1000 lines while a 2270-line diff got 22. Nothing noticed, because every existing
# gate checked that the tiers EXIST and that routing PICKS one -- never that the picked
# budget is survivable. That is the blind spot this gate closes: capacity, not routing.
#
# WHAT IT CANNOT DO, stated plainly. Whether N turns actually suffices for a given diff is
# empirical and model-dependent; no static check can know it. So this asserts the four
# structural properties that made the incident possible, and pins the one measured fact:
#
#   1. MONOTONIC   -- a larger diff never receives fewer turns than a smaller one.
#   2. TOTAL       -- every routable size yields a positive budget (no gap, no zero).
#   3. DENSITY     -- up to the largest size at which the floor is ACHIEVABLE within the
#                     budget's own ceiling, every size must clear MIN_TURNS_PER_KLOC.
#   4. CEILING     -- past that point the floor is arithmetically impossible, so it is not
#                     demanded; instead the budget must BE the ceiling. This is the half
#                     that catches a huge diff quietly routed to less than the most the
#                     system is willing to spend. The ceiling is read from the function's
#                     own behaviour, so changing MAX_TURNS moves the split automatically
#                     rather than silently widening the exemption.
#   5. REGRESSION  -- the measured failure point stays fixed: a 2802-line diff must receive
#                     strictly more than the 50 turns that starved it.
#
# Properties 3 and 4 exist as a pair because the first fix for this incident was WRONG in a
# way property 3 alone would have missed: replacing the 5000-line rung with a 2000-line one
# left a 2000..29999 tier whose top edge got 2.6 turns/KLOC -- the same hole, fifteen times
# wider. Rungs starve at their top by construction, which is why the budget is now a
# continuous function and this gate probes sizes rather than thresholds.
#
# CONTROL-FIRST. The gate mutates the real function (collapsing turns-per-KLOC to a value
# that cannot sustain any diff) and requires its own assertions to FAIL against that mutant.
# If the planted defect passes, the gate reports ITSELF broken and exits non-zero -- so a
# green run means the checks can fire, not merely that nothing tripped them.

set -euo pipefail

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
GATE_SRC="$REPO_ROOT/.ci/scripts/review/claude-review-gate.sh"

# Worst-case density a bounded tier must clear. Anchored to measurement, not taste:
# 2802 lines starved at 50 turns (17.8/KLOC) and 2270 survived at 50 (22.0/KLOC), so the
# floor sits between them, nearer the survivor. Raising it is safe; lowering it below 17.8
# would re-admit the exact diff that failed.
MIN_TURNS_PER_KLOC="${MIN_TURNS_PER_KLOC:-22}"

# The measured starvation point and the budget that failed it.
STARVED_LINES=2802
STARVED_TURNS=50

fail() {
    echo "${RED}✗${NC} $*" >&2
    exit 1
}

[[ -f "$GATE_SRC" ]] || fail "check-review-turn-capacity: $GATE_SRC not found; the gate cannot judge a function it cannot read"

# ---- extract the real function, or refuse -------------------------------------------
# By anchors, so a rename or rewrite breaks THIS gate loudly instead of silently leaving it
# testing a stale copy pasted in here.
FN="$(awk '/^emit_review_turns\(\) \{/,/^\}/' "$GATE_SRC")"
[[ -n "$FN" ]] || fail "check-review-turn-capacity: could not extract emit_review_turns() from $GATE_SRC (renamed? rewritten?). Refusing to pass while measuring nothing."
grep -q 'review_turns=' <<<"$FN" || fail "check-review-turn-capacity: extracted emit_review_turns() never assigns review_turns; the extraction is wrong"

# turns_for <size> <function-body>  -- runs the REAL function with gh stubbed to <size>
turns_for() {
    local size="$1" fn="$2" out
    out="$(
        FAKE_SIZE="$size" bash -c '
            GITHUB_OUTPUT=$(mktemp); GITHUB_REPOSITORY=x/y
            log_info() { :; }
            gh() { echo "$FAKE_SIZE"; }
            '"$fn"'
            emit_review_turns 1
            # `|| true`: grep exits 1 when the function emitted no review_turns at all, and
            # that must reach the caller as an EMPTY result -- which turns_for maps to 0 and
            # the TOTAL property then reports loudly. Letting the pipeline abort here would
            # hide "the function produced nothing" behind a dead subshell, i.e. the exact
            # silent-failure shape this gate exists to catch, inside the gate itself.
            grep -o "review_turns=[0-9]*" "$GITHUB_OUTPUT" | head -1 | cut -d= -f2 || true
            rm -f "$GITHUB_OUTPUT"
        ' 2>/dev/null
    )" || out=""
    printf '%s' "${out:-0}"
}

# The sizes probed. Deliberately includes every boundary neighbourhood plus the two
# measured PRs, so a moved threshold cannot slip between samples.
PROBE_SIZES=(0 1 500 1999 2000 2001 2269 2270 2802 4999 5000 5001 9999 29999 30000 30001 100000)

# ---- the four properties, as a function so the control can re-run them ---------------
# Prints failures to stdout; empty output means every property held.
evaluate() {
    local fn="$1" prev_size=-1 prev_turns=0 size turns
    for size in "${PROBE_SIZES[@]}"; do
        turns="$(turns_for "$size" "$fn")"

        # 2. TOTAL
        if [[ ! "$turns" =~ ^[0-9]+$ ]] || [[ "$turns" -le 0 ]]; then
            echo "TOTAL: size $size routed to a non-positive budget ('$turns')"
            continue
        fi
        # 1. MONOTONIC
        if [[ "$prev_size" -ge 0 && "$turns" -lt "$prev_turns" ]]; then
            echo "MONOTONIC: size $size got $turns turns, fewer than size $prev_size which got $prev_turns"
        fi
        prev_size="$size"
        prev_turns="$turns"
    done

    # 4. REGRESSION -- the measured starvation point must be strictly better resourced now.
    turns="$(turns_for "$STARVED_LINES" "$fn")"
    if [[ "$turns" -le "$STARVED_TURNS" ]]; then
        echo "REGRESSION: ${STARVED_LINES} lines still routes to $turns turns; ${STARVED_TURNS} is the budget that starved PR #553"
    fi

    # 3. DENSITY, split honestly at the point where the cost ceiling makes it impossible.
    #
    # The observed maximum budget is the ceiling. Below CEIL/floor*1000 lines the floor is
    # ACHIEVABLE, so it is required. Above it, no budget could satisfy the floor without
    # exceeding the ceiling, so requiring it would be demanding the impossible -- but the
    # budget must then be the ceiling itself. That is the real failure this catches: a large
    # diff quietly routed to something LESS than the most the system is willing to spend.
    #
    # The ceiling is derived from the function's own behaviour (its largest observed budget),
    # never hard-coded, so raising or lowering MAX_TURNS moves the split automatically.
    local size turns ceiling=0 dens
    for size in "${PROBE_SIZES[@]}"; do
        turns="$(turns_for "$size" "$fn")"
        [[ "$turns" -gt "$ceiling" ]] && ceiling="$turns"
    done
    local density_max_lines=$((ceiling * 1000 / MIN_TURNS_PER_KLOC))
    for size in "${PROBE_SIZES[@]}"; do
        [[ "$size" -lt 1000 ]] && continue # density is meaningless sub-KLOC
        turns="$(turns_for "$size" "$fn")"
        if [[ "$size" -le "$density_max_lines" ]]; then
            dens=$((turns * 1000 / size))
            if [[ "$dens" -lt "$MIN_TURNS_PER_KLOC" ]]; then
                echo "DENSITY: $size lines gives $turns turns = ${dens}/KLOC, under the ${MIN_TURNS_PER_KLOC}/KLOC floor (achievable here: the ceiling is $ceiling)"
            fi
        elif [[ "$turns" -lt "$ceiling" ]]; then
            echo "CEILING: $size lines is past the density-achievable range (${density_max_lines} lines) yet gets only $turns turns, below the $ceiling the budget is willing to spend"
        fi
    done
}

# ---- the control: a planted defect MUST be caught -----------------------------------
# Restores the pre-incident shape (the 2000 rung pushed back out to 5000). If the
# properties above still pass against that, they are not measuring what they claim.
MUTANT="${FN//per_kloc=25/per_kloc=8}"
if [[ "$MUTANT" == "$FN" ]]; then
    fail "check-review-turn-capacity: the control could not plant its defect (no 'per_kloc=25' in emit_review_turns -- the budget was rewritten). Update the mutant in this gate to match the new shape. Refusing to report a green that proves nothing."
fi
CONTROL_OUT="$(evaluate "$MUTANT")"
if [[ -z "$CONTROL_OUT" ]]; then
    fail "check-review-turn-capacity: CONTROL DID NOT FIRE. The pre-incident tiering passed every property, so this gate cannot detect the defect it exists for."
fi

# ---- the real run --------------------------------------------------------------------
REAL_OUT="$(evaluate "$FN")"
if [[ -n "$REAL_OUT" ]]; then
    echo "${RED}✗${NC} review turn budget can starve a review it routes:" >&2
    printf '  %s\n' "$REAL_OUT" >&2
    echo >&2
    echo "  Fix emit_review_turns() in .ci/scripts/review/claude-review-gate.sh." >&2
    echo "  A starved review burns its whole budget, posts nothing, and still spends an" >&2
    echo "  attempt against a finite allowance -- it is the expensive outcome, not the cheap one." >&2
    exit 1
fi

echo "${GREEN}✓${NC} review turn budget: ${#PROBE_SIZES[@]} sizes monotonic and total; ${MIN_TURNS_PER_KLOC}+ turns/KLOC wherever that is achievable, and the full ceiling beyond"
echo "  control fired on the pre-incident tiering ($(wc -l <<<"$CONTROL_OUT") finding(s)), so this green means the checks can fail"
