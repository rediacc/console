#!/bin/bash
# Both-ways test for CHECK 3 in .ci/scripts/security/check-workflow-gates.sh.
#
# WHY THIS CLASS NEEDS A GATE AT ALL: ubuntu-slim is a 1-vCPU runner with a HARD
# 15-minute job cap enforced by the platform. A job that reaches it is not
# failed, it is CANCELLED with no failed step -- which reads as neither pass nor
# fail. CI Complete is poisoned, the watchdog has no error to classify, and the
# log's last line is a successful post-step. quality-security hit this twice in
# three runs during the 0722-1 wave, and the only clue was a job that "just
# stopped". An explicit timeout-minutes below the cap converts that silent kill
# into an ordinary timeout failure naming the step that hung.
#
# Both directions matter:
#   - Too quiet: a slim job with no timeout, or one whose declared timeout is
#     above the cap, keeps the silent-cancellation failure mode.
#   - Too loud: ubuntu-latest jobs (no such cap) and matrix-expression runners
#     (not resolvable from YAML) must NOT be reported.
#
# The check is driven against fixture trees via WORKFLOWS_DIR, so the test never
# depends on the real .github/workflows census.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

CHECK="$REPO_ROOT/.ci/scripts/security/check-workflow-gates.sh"

LAST_OUT=""

# run_check <fixture-dir> [require-coverage]
# require-coverage defaults to true: these fixtures exist to exercise CHECK 3, so
# a tree with nothing to check must read as blind here even though the real
# script relaxes that for OTHER checks' fixture trees.
run_check() {
    local dir="$1" coverage="${2:-true}" rc=0
    LAST_OUT="$(CI=true WORKFLOWS_DIR="$dir" SLIM_TIMEOUT_REQUIRE_COVERAGE="$coverage" bash "$CHECK" 2>&1)" || rc=$?
    return "$rc"
}

# write_job <dir> <file> <job-id> <runs-on> [timeout-line]
# A minimal single-job workflow. No `needs:` and no reusable-workflow call, so
# CHECK 1 and CHECK 2 are satisfied trivially and only CHECK 3 can fire.
write_job() {
    local d="$1" file="$2" jid="$3" runson="$4" timeout="${5:-}"
    {
        echo "name: $file"
        echo "on: push"
        echo "jobs:"
        echo "  $jid:"
        echo "    runs-on: $runson"
        [[ -n "$timeout" ]] && echo "    timeout-minutes: $timeout"
        echo "    steps:"
        echo "      - run: echo hi"
    } >"$d/$file.yml"
}

test_slim_without_timeout_fails() {
    local dir="$1"
    write_job "$dir" wf slim_job ubuntu-slim
    local rc=0
    run_check "$dir" || rc=$?
    assert_exit_code 1 "$rc" "no-timeout slim job must fail"
    assert_contains "$LAST_OUT" "without timeout-minutes" "names the missing declaration"
    assert_contains "$LAST_OUT" "slim_job" "names the offending job"
    log_pass "slim job with no timeout-minutes is reported"
}

test_slim_over_ceiling_fails() {
    local dir="$1"
    write_job "$dir" wf slow_job ubuntu-slim 30
    local rc=0
    run_check "$dir" || rc=$?
    assert_exit_code 1 "$rc" "timeout-minutes: 30 on slim must fail"
    assert_contains "$LAST_OUT" "above the 14-minute ceiling" "explains the ceiling"
    # The fix is a different runner, not a bigger number. If this wording ever
    # drifts to "raise the timeout", the gate is teaching the wrong lesson.
    assert_contains "$LAST_OUT" "ubuntu-latest" "points at the real fix"
    log_pass "slim job with a timeout above the ceiling is reported"
}

test_slim_at_ceiling_passes() {
    local dir="$1"
    write_job "$dir" wf ok_job ubuntu-slim 14
    local rc=0
    run_check "$dir" || rc=$?
    assert_exit_code 0 "$rc" "timeout-minutes: 14 on slim must pass"
    log_pass "slim job exactly at the ceiling passes"
}

test_non_slim_runner_ignored() {
    local dir="$1"
    # A slim job is required or the anti-vacuity guard fires, so pair the
    # untimed latest job with a compliant slim one.
    write_job "$dir" wf1 fat_job ubuntu-latest
    write_job "$dir" wf2 thin_job ubuntu-slim 5
    local rc=0
    run_check "$dir" || rc=$?
    assert_exit_code 0 "$rc" "ubuntu-latest has no 15-minute cap, so no timeout is required"
    assert_not_contains "$LAST_OUT" "fat_job" "must not report a non-slim job"
    log_pass "ubuntu-latest without a timeout is NOT reported"
}

test_matrix_runner_ignored() {
    local dir="$1"
    write_job "$dir" wf1 matrix_job '${{ matrix.runner }}'
    write_job "$dir" wf2 thin_job ubuntu-slim 5
    local rc=0
    run_check "$dir" || rc=$?
    assert_exit_code 0 "$rc" "an unresolvable runner label cannot be judged here"
    assert_not_contains "$LAST_OUT" "matrix_job" "must not report an expression runner"
    log_pass "matrix-expression runner is NOT reported"
}

test_no_slim_jobs_is_blind() {
    local dir="$1"
    write_job "$dir" wf fat_job ubuntu-latest
    local rc=0
    run_check "$dir" || rc=$?
    # Nothing to check is a failure, not a pass -- the same anti-vacuity rule
    # the rest of this script follows. A renamed runner label must not silently
    # turn this gate into a no-op that still reports success.
    assert_exit_code 1 "$rc" "zero slim jobs must not report success"
    assert_contains "$LAST_OUT" "this check is blind" "says why it refused"
    log_pass "a tree with zero slim jobs fails as blind, not green"
}

test_real_workflows_pass() {
    local rc=0
    LAST_OUT="$(CI=true bash "$CHECK" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "every real ubuntu-slim job declares a compliant timeout"
    log_pass "the repo's own .github/workflows satisfies the rule"
}

log_test "test-slim-timeout"
with_temp_dir test_slim_without_timeout_fails
with_temp_dir test_slim_over_ceiling_fails
with_temp_dir test_slim_at_ceiling_passes
with_temp_dir test_non_slim_runner_ignored
with_temp_dir test_matrix_runner_ignored
with_temp_dir test_no_slim_jobs_is_blind
test_real_workflows_pass
