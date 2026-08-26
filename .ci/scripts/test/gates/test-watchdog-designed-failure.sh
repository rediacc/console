#!/bin/bash
# The watchdog's by-design failure must SAY it is by design.
#
# THE PROBLEM, measured 2026-08-26 across three days of rediacc/console runs:
# 589 success, 230 skipped, 117 cancelled, 64 failure -- and 63 of those 64
# failures are this one code path. The watchdog cancels the CI run it monitors,
# then core.setFailed()s to signal that it did. That is its SUCCESS mode.
#
# Nothing said so. To a human scanning the Actions tab, to any dashboard, and to
# any sweeper keyed on `conclusion`, a working watchdog and a broken one are
# indistinguishable. It is also the direct reason the nightly retry
# (.ci/scripts/housekeeping/retry-failed-runs.sh) must exclude this workflow by
# path: without that exclusion, 63 of its 64 candidates are deliberate.
#
# WHY THE RUN NAME IS NOT THE FIX, and this is worth recording because the
# obvious design does not work: GitHub evaluates `run-name` at run CREATION from
# the dispatch inputs, before the monitored run's outcome exists. It CANNOT
# carry a verdict decided mid-run. The step summary is the earliest surface that
# can, so that is where the explanation lives.
#
# WHAT THIS GATE CANNOT SEE: it asserts the marker and the ordering in the
# source. It cannot prove GitHub renders the summary, and it deliberately does
# NOT assert the exact prose -- only that the by-design claim and the monitored
# run id are present, so the wording stays editable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

test_annotation_is_self_describing() {
    log_test "the failure annotation must say it is by design"
    grep -q "PIPELINE CANCELLED (watchdog working as designed)" "$SUT" ||
        log_fail "the setFailed annotation no longer marks itself as by-design"
    log_pass "annotation carries the by-design marker"
}

test_summary_is_written_before_setfailed() {
    log_test "the summary must be written BEFORE setFailed, or it is never seen"
    local sum_line fail_line
    sum_line="$(grep -n 'core.summary' "$SUT" | head -1 | cut -d: -f1)"
    fail_line="$(grep -n "PIPELINE CANCELLED (watchdog working as designed)" "$SUT" | head -1 | cut -d: -f1)"
    [[ -n "$sum_line" ]] || log_fail "no step summary is written at the by-design failure"
    [[ -n "$fail_line" ]] || log_fail "the by-design setFailed is gone"
    [[ "$sum_line" -lt "$fail_line" ]] ||
        log_fail "the summary write sits AFTER setFailed, so it never runs"
    log_pass "summary precedes setFailed"
}

test_summary_failure_does_not_swallow_the_verdict() {
    log_test "a summary that cannot be written must NOT suppress the failure"
    # The write is diagnostics; the annotation is the signal. If a throw from
    # core.summary could escape, the watchdog would exit 0 having cancelled a
    # pipeline -- a false green on the one path that matters most.
    local body
    body="$(sed -n '/core.summary/,/PIPELINE CANCELLED (watchdog working as designed)/p' "$SUT")"
    grep -q 'catch' <<<"$body" ||
        log_fail "the summary write is unguarded; a throw would skip setFailed entirely"
    log_pass "summary write is guarded, verdict still reached"
}

test_summary_names_the_monitored_run() {
    log_test "the summary must point at the run that actually failed"
    grep -q 'targetRunId' <<<"$(sed -n '/working as designed/,/setFailed/p' "$SUT")" ||
        log_fail "the summary does not name the monitored run, so a reader cannot follow it"
    log_pass "summary names the monitored run"
}

test_retry_sweeper_still_excludes_this_workflow() {
    log_test "the marker is an explanation, NOT a substitute for the path exclusion"
    # A reader might reasonably think a self-describing failure makes the
    # sweeper's exclusion redundant. It does not: `conclusion` is still
    # `failure`, and that is what the API returns.
    local sweeper="$REPO_ROOT/.ci/scripts/housekeeping/retry-failed-runs.sh"
    [[ -f "$sweeper" ]] || log_fail "the nightly retry sweeper is missing"
    grep -q '.github/workflows/watchdog-monitor.yml' "$sweeper" ||
        log_fail "the sweeper no longer excludes the watchdog by path"
    log_pass "path exclusion still in place alongside the marker"
}

test_control_marker_removal_is_detectable() {
    log_test "CONTROL: a plain annotation must be caught"
    local mutant
    mutant="$(mktemp)"
    # By construction: write the OLD annotation form, not a mutation of the new.
    printf "%s\n" "core.setFailed('PIPELINE CANCELLED: ' + failureMsg);" >"$mutant"
    if grep -q "PIPELINE CANCELLED (watchdog working as designed)" "$mutant"; then
        rm -f "$mutant"
        log_fail "CONTROL DID NOT FIRE: the pre-fix annotation read as marked"
    fi
    rm -f "$mutant"
    log_pass "control: the pre-fix annotation is detectable"
}

test_annotation_is_self_describing
test_summary_is_written_before_setfailed
test_summary_failure_does_not_swallow_the_verdict
test_summary_names_the_monitored_run
test_retry_sweeper_still_excludes_this_workflow
test_control_marker_removal_is_detectable

echo
log_pass "watchdog by-design failure: 6/6"
echo "  Blind spot: asserts the source, not GitHub's rendering, and deliberately"
echo "  does not pin the prose -- only the by-design claim and the run id."
