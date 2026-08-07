#!/bin/bash
# Tests for .ci/scripts/quality/check-dead-case-arms.sh.
#
# The gate is CONTROL-FIRST: it plants its own dead arm and refuses to report
# on the real tree unless its scanner catches that arm. So the single most
# important thing to test is that the control is not itself decorative -- the
# gate's first two runs during development both failed for that reason (an
# extractor that missed `... ) ;;`, then a planted key that was a literal in
# the gate's own file and therefore looked "live").

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$SCRIPT_DIR/../../quality/check-dead-case-arms.sh"
[ -x "$GATE" ] || log_fail "gate not executable: $GATE"

LAST=""
run_gate() {
    local rc=0
    LAST="$(DEAD_CASE_TEST_DIRS="$1" DEAD_CASE_CODE_DIRS="${2:-.ci/scripts scripts}" \
        bash "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

test_real_tree_is_clean_and_the_control_fired() {
    # Seam-free: the real invocation over the real tree. This is the line the
    # manifest's BLOCKER names.
    local rc=0
    LAST="$(bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must have no dead case arms (output: $LAST)"
    assert_contains "$LAST" "control fired" "the verdict must state its control fired, not just 'clean'"
    log_pass "real tree clean, and the gate says its control fired"
}

test_a_dead_arm_is_caught() {
    local d="$1"
    mkdir -p "$d/test"
    # A key that exists in no code directory: the arm can never match.
    printf 'case "$out" in\n    *"zzznosuchfield=20"*)\n        log_fail "x" ;;\nesac\n' \
        >"$d/test/dead.sh"
    local rc=0
    run_gate "$d/test" ".ci/scripts scripts" || rc=$?
    assert_exit_code 1 "$rc" "a case arm globbing for a nonexistent field must fail"
    assert_contains "$LAST" "zzznosuchfield" "names the dead field"
    assert_contains "$LAST" "DEAD" "says the arm is dead"
    log_pass "a dead case arm is caught and named"
}

test_a_live_arm_passes() {
    # CONTROL for the case above. Same shape, but the field DOES exist in the
    # code under test, so the arm can match and must not be reported. Without
    # this, a scanner that flagged every case arm would look correct.
    local d="$1"
    mkdir -p "$d/test" "$d/code"
    printf 'printf "livefield=%%s\\n" "$x"\n' >"$d/code/emit.sh"
    printf 'case "$out" in\n    *"livefield=20"*)\n        log_fail "x" ;;\nesac\n' \
        >"$d/test/live.sh"
    local rc=0
    run_gate "$d/test" "$d/code" || rc=$?
    assert_exit_code 0 "$rc" "an arm whose field is emitted by real code must pass (output: $LAST)"
    log_pass "a live arm is not flagged (the scanner is not a blanket refusal)"
}

test_the_founding_defect_fires() {
    # THE case this gate was built from, kept as a permanent fixture. `cores=`
    # is special precisely because this gate's own header describes the defect
    # in prose, and the first implementation grepped comments too -- so the
    # only two occurrences of `cores=` in the whole tree were its own comment
    # lines, and it ruled the arm live and MISSED the bug it exists to catch.
    # Verified 2026-08-05: exit 0 on this exact fixture before the fix, exit 1
    # after. If key_is_live ever stops filtering comments, this case goes red.
    local d="$1"
    mkdir -p "$d/test"
    printf 'case "$1" in\n    *"cores=20"*)\n        log_fail "host leak" ;;\nesac\n' \
        >"$d/test/founding.sh"
    local rc=0
    run_gate "$d/test" ".ci/scripts scripts" || rc=$?
    assert_exit_code 1 "$rc" "the founding defect (cores= documented only in comments) must FIRE"
    assert_contains "$LAST" "cores" "names the field the dead arm globs for"
    log_pass "the founding defect fires: prose describing a bad pattern no longer immunises the tree"
}

test_comments_are_not_assertions() {
    # A commented-out arm is prose, not a claim, and flagging it would make the
    # gate noisy enough to be suppressed.
    local d="$1"
    mkdir -p "$d/test"
    printf '# case "$out" in\n#     *"zzznosuchfield=20"*)\n' >"$d/test/commented.sh"
    local rc=0
    run_gate "$d/test" ".ci/scripts scripts" || rc=$?
    assert_exit_code 0 "$rc" "a commented arm must not be reported (output: $LAST)"
    log_pass "commented-out arms are prose, not assertions"
}

log_test "test-dead-case-arms"
test_real_tree_is_clean_and_the_control_fired
with_temp_dir test_a_dead_arm_is_caught
with_temp_dir test_a_live_arm_passes
with_temp_dir test_the_founding_defect_fires
with_temp_dir test_comments_are_not_assertions
echo ""
log_pass "all tests passed"
