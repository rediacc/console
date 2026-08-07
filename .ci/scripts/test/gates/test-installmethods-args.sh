#!/bin/bash
# Tests that .ci/scripts/test/test-install-methods.sh cannot report success
# without having accounted for at least one test.
#
# WHY THIS EXISTS. Reproduced live on 2026-08-07:
#
#   .ci/scripts/test/test-install-methods.sh --dry-run --method bogus --version 1.2.17
#   -> "Results: 0 passed, 0 failed, 0 skipped (total 0)"   EXIT=0
#
# Two causes, both fixed and both pinned here. The argument parser ended with a
# bare `*) shift ;;` that swallowed anything it did not recognise, and METHOD
# was never validated, so a typo produced a run that matched no test block. And
# success was defined as `[[ $FAIL -eq 0 ]]`, which is also true of a run that
# did nothing at all.
#
# The rule: every path ends VERIFIED, or in a VISIBLE skip, or in a FAILURE.
# An all-skipped run is deliberately still a success -- each skip is printed
# with its reason and counted -- but a zero-total run is not, because it says
# nothing.
#
# These tests drive the REAL script (in --dry-run, so no Docker and no network),
# and the zero-total backstop is proven to fire by mutating a copy of the script
# until a zero-total run is reachable again.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TARGET="$SCRIPT_DIR/../test-install-methods.sh"
[ -f "$TARGET" ] || log_fail "target not found: $TARGET"

OUT=""
RC=0

# Run the target (or a copy) and capture merged output plus exit code.
run_target() {
    local script="$1"
    shift
    RC=0
    OUT="$("$script" "$@" 2>&1)" || RC=$?
}

test_unknown_method_is_fatal() {
    run_target "$TARGET" --dry-run --method bogus --version 1.2.17
    assert_exit_code 2 "$RC" "an unknown --method must be a hard error"
    assert_contains "$OUT" "unknown --method 'bogus'" "the error must name the bad value"
    assert_contains "$OUT" "valid --method values:" "the error must list the valid values"
    assert_contains "$OUT" "apt" "the valid-value list must actually contain the methods"
    assert_not_contains "$OUT" "total 0" "it must not reach the summary at all"
    log_pass "a typo'd --method stops the run instead of verifying nothing"
}

test_unknown_argument_is_fatal() {
    run_target "$TARGET" --dry-run --nope --version 1.2.17
    assert_exit_code 2 "$RC" "an unrecognised argument must be a hard error"
    assert_contains "$OUT" "unknown argument: '--nope'" "the error must name the bad argument"
    log_pass "an unrecognised argument is no longer swallowed"
}

test_a_flag_without_a_value_is_fatal() {
    for flag in --method --version --platform --arch --local-artifacts; do
        run_target "$TARGET" --dry-run "$flag"
        assert_exit_code 2 "$RC" "$flag with no value must be a hard error"
        assert_contains "$OUT" "$flag requires a value" "the error must name the flag"
    done
    log_pass "every value-taking flag refuses an empty value"
}

test_unknown_platform_and_arch_are_fatal() {
    run_target "$TARGET" --dry-run --method binary --version 1.2.17 --platform solaris
    assert_exit_code 2 "$RC" "an unknown --platform must be a hard error"
    assert_contains "$OUT" "unknown --platform 'solaris'" "the error must name the bad platform"

    run_target "$TARGET" --dry-run --method binary --version 1.2.17 --arch riscv
    assert_exit_code 2 "$RC" "an unknown --arch must be a hard error"
    assert_contains "$OUT" "unknown --arch 'riscv'" "the error must name the bad arch"
    log_pass "a platform or arch that matches no test block stops the run"
}

test_a_valid_run_still_works() {
    # The other direction: the parser must not have become so strict that a
    # legitimate invocation fails. These are the exact flag shapes ci.yml and
    # ct-install-methods.yml use.
    run_target "$TARGET" --dry-run --method apt --version 1.2.17
    assert_exit_code 0 "$RC" "a valid invocation must still succeed"
    assert_contains "$OUT" "total 3" "the three APT distros must be accounted for"

    run_target "$TARGET" --dry-run --method binary --version 1.2.17 --platform linux --arch arm64
    assert_exit_code 0 "$RC" "a valid --platform/--arch invocation must still succeed"
    log_pass "the invocations CI actually uses are still accepted"
}

test_a_dry_run_is_never_reported_as_a_pass() {
    # A dry run installs nothing and compares no version. It used to be counted
    # as a PASS, which made "3 passed, 0 failed" indistinguishable in the
    # summary from three real verifications.
    run_target "$TARGET" --dry-run --method apt --version 1.2.17
    assert_exit_code 0 "$RC" "a dry run is not a failure"
    assert_contains "$OUT" "0 passed" "a dry run must claim zero passes"
    assert_contains "$OUT" "3 skipped" "a dry run must be counted as skips"
    assert_contains "$OUT" "dry-run, nothing was verified" "the reason must be visible per test"
    log_pass "a dry run reports skips, not passes"
}

test_an_all_skipped_run_is_visible_and_allowed() {
    # `--method verify` with no REPO_CHANNEL is a real CI condition (schedule
    # and workflow_dispatch stage no artifacts). It must succeed, and it must
    # SAY that it verified nothing -- that is the visible-skip half of the rule.
    RC=0
    OUT="$(REPO_CHANNEL="" "$TARGET" --method verify --version 1.2.17 2>&1)" || RC=$?
    assert_exit_code 0 "$RC" "an all-skipped run is a success"
    assert_contains "$OUT" "SKIP: Channel Verify" "the skip must be named"
    assert_contains "$OUT" "no REPO_CHANNEL" "the skip must carry its reason"
    assert_contains "$OUT" "1 skipped" "the skip must be counted, so the total is never zero"
    assert_not_contains "$OUT" "total 0" "a block that matched must never leave the total at zero"
    log_pass "an all-skipped run succeeds loudly rather than silently"
}

# --- the zero-total backstop -------------------------------------------------
#
# With every method, platform and arch validated, and every block registering at
# least a skip, no invocation of the shipped script should be able to reach a
# zero total. That makes the backstop unreachable by argument alone -- and an
# unreachable guard is exactly the kind that rots into a guard that cannot fire.
# So it is proven against a MUTATED copy: widen the valid-method list to admit a
# method that matches no test block, which is the pre-fix parser's behaviour.

TARGET_DIR="$(cd "$(dirname "$TARGET")" && pwd)"

mutate() {
    local dest="$1"
    shift
    cp "$TARGET" "$dest"
    chmod +x "$dest"
    # The copy lives in a temp dir, so pin SCRIPT_DIR back at the real one or it
    # cannot find lib/common.sh. Mutating in place under .ci/ is not an option:
    # this tree is shared with other sessions.
    sed -i "s|^SCRIPT_DIR=.*|SCRIPT_DIR=\"$TARGET_DIR\"|" "$dest"
    local expr
    for expr in "$@"; do
        sed -i "$expr" "$dest"
    done
}

WIDEN='s/^VALID_METHODS="binary/VALID_METHODS="bogus binary/'
DROP_BACKSTOP='/^if ((TOTAL == 0)); then$/,/^fi$/d'

test_the_backstop_fires_on_a_zero_total_run() {
    local tmp
    tmp="$(mktemp -d)"

    # Mutation 1: only the parser is loosened. The backstop must catch it.
    mutate "$tmp/with-backstop.sh" "$WIDEN"
    run_target "$tmp/with-backstop.sh" --dry-run --method bogus --version 1.2.17
    assert_exit_code 1 "$RC" "a run that executed zero tests must FAIL"
    assert_contains "$OUT" "total 0" "the mutation really did produce a zero-total run"
    assert_contains "$OUT" "executed ZERO tests" "the failure must say what went wrong"
    assert_contains "$OUT" "Refusing to report success" "the failure must say why it refuses"

    # Mutation 2: the same loosened parser with the backstop removed, i.e. the
    # code exactly as it stood on 2026-08-07. It must report the incident's
    # signature -- "total 0" with EXIT=0. Without this the test above would not
    # prove that the backstop is what makes the difference.
    mutate "$tmp/without-backstop.sh" "$WIDEN" "$DROP_BACKSTOP"
    run_target "$tmp/without-backstop.sh" --dry-run --method bogus --version 1.2.17
    assert_exit_code 0 "$RC" "the OLD summary must pass a zero-total run, or this test proves nothing"
    assert_contains "$OUT" "0 passed, 0 failed, 0 skipped (total 0)" "the reproduced signature"

    rm -rf "$tmp"
    log_pass "the zero-total backstop fires, and the old summary really did not"
}

log_test "test-installmethods-args"
test_unknown_method_is_fatal
test_unknown_argument_is_fatal
test_a_flag_without_a_value_is_fatal
test_unknown_platform_and_arch_are_fatal
test_a_valid_run_still_works
test_a_dry_run_is_never_reported_as_a_pass
test_an_all_skipped_run_is_visible_and_allowed
test_the_backstop_fires_on_a_zero_total_run
echo ""
log_pass "all tests passed"
