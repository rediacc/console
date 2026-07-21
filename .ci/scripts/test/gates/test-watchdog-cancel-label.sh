#!/bin/bash
# Unit test for the `no-cancel-failure` ordering in .ci/scripts/ci/watchdog-monitor.cjs.
#
# WHAT BROKE. The watchdog handles a failed job in numbered branches. Branch 1 is
# "no-retry jobs -- fast fail, no AI" and it force-cancelled and RETURNED. Branch 2
# is the `no-cancel-failure` label. WATCHDOG_NO_RETRY_PATTERNS is 'Quality,Review
# Gate', so branch 1 matched every Quality job and branch 2 was unreachable for
# exactly the class of failure the label exists to hold the run open for.
#
# Worse than silent: the label was fetched live, matched, and logged
# "will not cancel on job failures" two minutes BEFORE the run was force-cancelled
# (run 29825013399). The log asserted the opposite of the behaviour, which is how
# it survived -- an operator reading it would confirm the label was working.
#
# WHY A UNIT TEST AND NOT A MIRROR. It would be easy to re-implement the boolean
# here and assert on the copy; that proves nothing about the watchdog. This calls
# the exported decision and reads WATCHDOG_NO_RETRY_PATTERNS out of the REAL
# ci.yml, so a rename of a pattern or a reordering of the branch fails here.
#
# Both directions matter:
#   - Too quiet: label ignored, one red hides the state of every other job.
#   - Too loud: label lets a Review Gate failure through. CLAUDE.md is explicit
#     that Review Gate fails immediately and force-cancels -- an outstanding
#     review is not something to label past.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"

# The patterns under test are the ones CI actually sets, not a copy: a guard that
# works on invented job names while the real config never matches is the exact
# failure this gate exists to catch.
NO_RETRY_PATTERNS="$(sed -n "s/^ *WATCHDOG_NO_RETRY_PATTERNS: *'\(.*\)'$/\1/p" "$CI_WORKFLOW")"
if [[ -z "$NO_RETRY_PATTERNS" ]]; then
    echo "could not read WATCHDOG_NO_RETRY_PATTERNS from $CI_WORKFLOW" >&2
    exit 1
fi

# verdict <job-name> <is-failure 0|1> <label-on 0|1> -> "cancel" | "continue"
verdict() {
    node -e '
const w = require(process.argv[1]);
const v = w.evaluateNoRetryCancel({
  jobName: process.argv[2],
  isFailure: process.argv[3] === "1",
  skipCancellationOnFailure: process.argv[4] === "1",
  noRetryPatterns: process.argv[5].split(",").map(s => s.trim()),
});
process.stdout.write(v.cancel ? "cancel" : "continue");
' "$WATCHDOG" "$1" "$2" "$3" "$NO_RETRY_PATTERNS"
}

# ---------------------------------------------------------------------------

test_patterns_are_real() {
    # Anti-vacuity: if the pattern list stopped covering Quality, every case
    # below would pass for the wrong reason.
    assert_contains "$NO_RETRY_PATTERNS" "Quality" "ci.yml still lists Quality as no-retry"
    assert_contains "$NO_RETRY_PATTERNS" "Review Gate" "ci.yml still lists Review Gate as no-retry"
    log_pass "reading the real WATCHDOG_NO_RETRY_PATTERNS from ci.yml ($NO_RETRY_PATTERNS)"
}

test_quality_failure_cancels_without_label() {
    assert_eq "$(verdict 'Quality / Shared Package Tests' 1 0)" "cancel" \
        "a Quality failure with no label must force-cancel (unchanged behaviour)"
    log_pass "Quality failure without the label still force-cancels"
}

test_quality_failure_honors_label() {
    # The regression. This returned "cancel" before the fix.
    assert_eq "$(verdict 'Quality / Shared Package Tests' 1 1)" "continue" \
        "no-cancel-failure must hold the run open for a Quality failure"
    log_pass "no-cancel-failure is honoured for Quality (the unreachable branch)"
}

test_review_gate_is_label_immune() {
    assert_eq "$(verdict 'Review Gate' 1 0)" "cancel" "Review Gate cancels without the label"
    assert_eq "$(verdict 'Review Gate' 1 1)" "cancel" \
        "Review Gate must cancel EVEN WITH the label (CLAUDE.md: fails immediately)"
    log_pass "Review Gate is immune to no-cancel-failure, per CLAUDE.md"
}

test_quality_review_gate_substring_is_immune() {
    # `Quality / Review Gate` matches BOTH lists. Immunity must win, or the label
    # would suppress the review gate through the Quality half of its name.
    assert_eq "$(verdict 'Quality / Review Gate' 1 1)" "cancel" \
        "a job matching both lists must stay immune"
    log_pass "a job matching both patterns resolves to immune, not to the label"
}

test_non_no_retry_job_is_unaffected() {
    # A job outside the no-retry list never took this branch either way; it falls
    # through to AI classification downstream.
    assert_eq "$(verdict 'Build (Renet) / Renet (Full)' 1 0)" "continue" \
        "a non-no-retry failure must not be force-cancelled by this branch"
    assert_eq "$(verdict 'Build (Renet) / Renet (Full)' 1 1)" "continue" \
        "same with the label on"
    log_pass "jobs outside the no-retry list fall through unchanged"
}

test_cancellation_is_not_a_failure() {
    # Branch 1 is gated on `failed.includes(job)` on purpose: a non-stuck
    # CANCELLATION of a Quality job is an infra flake, and nuking a 0-failure run
    # for it is wrong.
    assert_eq "$(verdict 'Quality / Shared Package Tests' 0 0)" "continue" \
        "a cancelled (not failed) Quality job must not force-cancel the run"
    log_pass "a cancellation is not treated as a failure"
}

log_test "test-watchdog-cancel-label"
test_patterns_are_real
test_quality_failure_cancels_without_label
test_quality_failure_honors_label
test_review_gate_is_label_immune
test_quality_review_gate_substring_is_immune
test_non_no_retry_job_is_unaffected
test_cancellation_is_not_a_failure
echo ""
log_pass "all tests passed"
