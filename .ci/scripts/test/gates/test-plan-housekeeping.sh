#!/bin/bash
# Drives the REAL .ci/scripts/quality/check-plan-housekeeping.sh against fixture
# git repositories with BACKDATED commits.
#
# THIS FILE IS THE ENTIRE JUSTIFICATION FOR LANDING THAT GATE. Measured over all
# 4001 reachable commits: ZERO plan files fail at 33 days today, and none can --
# `agent/` only became a tracked directory on 2026-08-18, so nothing under it is
# older than 15 days. A gate with no live offenders and no fixture proves exactly
# nothing; every "✓" it prints would be indistinguishable from a broken scan.
#
# The dates are set with GIT_AUTHOR_DATE/GIT_COMMITTER_DATE, the same technique
# .ci/scripts/test/gates/test-age-check.sh already uses. PLAN_HK_ROOT re-points
# the gate at each fixture, and the last case proves that override is not an
# escape hatch.
#
# The two cases no other gate in this repo has are the shallow-clone pair: a
# `git clone --depth 1` of the fixture must REFUSE under CI and must SKIP LOUDLY
# without it. That is the defect the gate was built around -- `git log` on a
# shallow clone answers with the graft date and would make the whole check pass
# vacuously.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-plan-housekeeping.sh"
CFG="$REPO_ROOT/.ci/config/plan-lifecycle.json"

# A fixture repo with N plans committed `days` ago, plus enough filler plans to
# clear the floor. The filler is committed TODAY so it can never be the thing a
# case is measuring.
make_repo() { # <dir> <days-ago> <name...>
    local d="$1" days="$2"
    shift 2
    mkdir -p "$d/agent"
    git -C "$d" init -q
    git -C "$d" config user.email t@example.com
    git -C "$d" config user.name t
    local i
    for i in $(seq 1 32); do
        printf 'Status: draft\n\n# filler %s\n\n- [ ] a task long enough to parse\n' "$i" \
            >"$d/agent/PLAN-filler-$i.md"
    done
    git -C "$d" add -A
    git -C "$d" -c commit.gpgsign=false commit -qm filler
    local n
    for n in "$@"; do
        printf 'Status: draft\n\n# %s\n\n- [ ] a task long enough to parse\n' "$n" >"$d/agent/$n"
    done
    git -C "$d" add -A
    local when
    when=$(python3 -c "
import datetime as dt,sys
print((dt.datetime.now(dt.UTC) - dt.timedelta(days=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%S+0000'))" "$days")
    GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" \
        git -C "$d" -c commit.gpgsign=false commit -qm "aged plans"
}

run_gate() { # <root> [env...] -> sets LAST_OUT, returns the gate's rc
    local root="$1"
    shift
    local rc=0
    LAST_OUT=$(env PLAN_HK_ROOT="$root" PLAN_HK_CONFIG="$CFG" "$@" bash "$GATE" 2>&1) || rc=$?
    return "$rc"
}

# ── 1. THE PLANT: an over-age plan is reported, and named ──────────────────
test_over_age() {
    local d="$1/r"
    make_repo "$d" 40 PLAN-ancient.md
    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a plan committed 40 days ago must fail"
    assert_contains "$LAST_OUT" "PLAN-ancient.md" "names the offending plan"
    assert_contains "$LAST_OUT" "unchanged for more than" "says what the finding IS"
    log_pass "an over-age plan is reported by name"
}

# ── 2. THE PAIR, and the case that makes the INSTRUMENT choice testable ────
# A plan first committed 40 days ago but AMENDED 2 days ago must PASS. This is
# what distinguishes last-commit from added-date; without it the gate could be
# using either and nobody would know.
test_amended_recently() {
    local d="$1/r"
    make_repo "$d" 40 PLAN-ancient.md
    echo '- [ ] one more task, added today' >>"$d/agent/PLAN-ancient.md"
    git -C "$d" add -A
    git -C "$d" -c commit.gpgsign=false commit -qm "still being worked"
    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "an OLD plan amended today must pass -- last-commit, not added-date"
    log_pass "CONTROL: editing an old plan resets its clock"
}

# ── 3. CONTROL: a young corpus is silent ───────────────────────────────────
test_young_is_silent() {
    local d="$1/r"
    make_repo "$d" 2 PLAN-fresh.md
    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a corpus with nothing over the threshold must pass"
    assert_not_contains "$LAST_OUT" "unchanged for more than" "and say nothing about ages"
    log_pass "CONTROL: a young corpus is silent, so the plant above means something"
}

# ── 4. The WARN band names the date, and does NOT fail ─────────────────────
test_warn_band() {
    local d="$1/r"
    make_repo "$d" 28 PLAN-soon.md
    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a plan inside the warn band must WARN, never fail"
    assert_contains "$LAST_OUT" "PLAN-soon.md" "names it"
    assert_contains "$LAST_OUT" "red on" "and names the exact date it goes red"
    log_pass "the warn band announces the red date a week early"
}

# ── 5-7. The allowlist, and its three liveness rules ───────────────────────
test_allowlist_suppresses() {
    local d="$1/r"
    make_repo "$d" 40 PLAN-ancient.md
    printf '# BLOCKER: this plan is a multi-week migration the operator is still executing daily\n2099-01-01  agent/PLAN-ancient.md\n' \
        >"$d/.plan-housekeeping-allowlist"
    local rc=0
    run_gate "$d" PLAN_HK_ALLOWLIST="$d/.plan-housekeeping-allowlist" || rc=$?
    assert_exit_code 0 "$rc" "an unexpired entry with a real BLOCKER suppresses the finding"
    log_pass "the escape hatch works"
}

test_allowlist_expires() {
    local d="$1/r"
    make_repo "$d" 40 PLAN-ancient.md
    printf '# BLOCKER: this plan is a multi-week migration the operator is still executing daily\n2020-01-01  agent/PLAN-ancient.md\n' \
        >"$d/.plan-housekeeping-allowlist"
    local rc=0
    run_gate "$d" PLAN_HK_ALLOWLIST="$d/.plan-housekeeping-allowlist" || rc=$?
    assert_exit_code 1 "$rc" "an EXPIRED entry stops suppressing, on its own stated date"
    assert_contains "$LAST_OUT" "EXPIRED" "and says so"
    log_pass "an exemption cannot outlive the argument for it"
}

test_allowlist_unnecessary() {
    local d="$1/r"
    make_repo "$d" 2 PLAN-fresh.md
    printf '# BLOCKER: this plan is a multi-week migration the operator is still executing daily\n2099-01-01  agent/PLAN-fresh.md\n' \
        >"$d/.plan-housekeeping-allowlist"
    local rc=0
    run_gate "$d" PLAN_HK_ALLOWLIST="$d/.plan-housekeeping-allowlist" || rc=$?
    assert_exit_code 1 "$rc" "an entry that suppresses NOTHING is refused -- the converse direction"
    assert_contains "$LAST_OUT" "suppresses nothing" "and says which way it is wrong"
    log_pass "an exemption must actually be exempting something"
}

test_allowlist_low_effort_blocker() {
    local d="$1/r"
    make_repo "$d" 40 PLAN-ancient.md
    printf '# BLOCKER: needed\n2099-01-01  agent/PLAN-ancient.md\n' >"$d/.plan-housekeeping-allowlist"
    local rc=0
    run_gate "$d" PLAN_HK_ALLOWLIST="$d/.plan-housekeeping-allowlist" || rc=$?
    assert_exit_code 1 "$rc" "a one-word BLOCKER buys no silence"
    log_pass "the BLOCKER must be substantive, not a word"
}

test_allowlist_dangling() {
    local d="$1/r"
    make_repo "$d" 2 PLAN-fresh.md
    printf '# BLOCKER: this plan is a multi-week migration the operator is still executing daily\n2099-01-01  agent/PLAN-that-never-existed.md\n' \
        >"$d/.plan-housekeeping-allowlist"
    local rc=0
    run_gate "$d" PLAN_HK_ALLOWLIST="$d/.plan-housekeeping-allowlist" || rc=$?
    assert_exit_code 1 "$rc" "an entry naming no tracked plan is refused"
    assert_contains "$LAST_OUT" "not a tracked plan file" "and says the plan is gone"
    log_pass "an exemption cannot outlive the file it names"
}

# ── 8-9. THE SHALLOW PAIR. The defect this gate exists around. ─────────────
test_shallow_refuses_in_ci() {
    local d="$1/r" s="$1/shallow"
    make_repo "$d" 40 PLAN-ancient.md
    git clone -q --depth 1 "file://$d" "$s" 2>/dev/null
    local rc=0
    run_gate "$s" CI=true || rc=$?
    assert_exit_code 1 "$rc" "a SHALLOW checkout in CI must refuse, not answer"
    assert_contains "$LAST_OUT" "SHALLOW" "and say why"
    assert_not_contains "$LAST_OUT" "none over" "and must NOT claim a clean tree"
    log_pass "the graft-date defect is refused in CI rather than answered wrongly"
}

test_shallow_skips_locally() {
    local d="$1/r" s="$1/shallow"
    make_repo "$d" 40 PLAN-ancient.md
    git clone -q --depth 1 "file://$d" "$s" 2>/dev/null
    local rc=0
    run_gate "$s" CI= || rc=$?
    assert_exit_code 0 "$rc" "a shallow checkout locally is a SKIP, not a failure"
    assert_contains "$LAST_OUT" "PARTIAL RUN" "and it says the run was partial, not clean"
    log_pass "locally the age verdict is deferred loudly, never silently"
}

# ── 10. The override is not an escape hatch ────────────────────────────────
test_empty_tree_is_not_a_pass() {
    local d="$1/empty"
    mkdir -p "$d"
    git -C "$d" init -q
    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "an empty tree must fail, or PLAN_HK_ROOT is an escape hatch"
    assert_contains "$LAST_OUT" "VACUOUS INPUT" "and say the corpus was lost"
    log_pass "the fixture override cannot be used to pass vacuously"
}

log_test "test-plan-housekeeping"
with_temp_dir test_over_age
with_temp_dir test_amended_recently
with_temp_dir test_young_is_silent
with_temp_dir test_warn_band
with_temp_dir test_allowlist_suppresses
with_temp_dir test_allowlist_expires
with_temp_dir test_allowlist_unnecessary
with_temp_dir test_allowlist_low_effort_blocker
with_temp_dir test_allowlist_dangling
with_temp_dir test_shallow_refuses_in_ci
with_temp_dir test_shallow_skips_locally
with_temp_dir test_empty_tree_is_not_a_pass

echo ""
log_pass "all tests passed"
