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

test_by_design_paths_do_not_fail_the_step() {
    log_test "every BY-DESIGN path must exit 0, not setFailed"
    # Phase 3b, operator-approved 2026-08-26. Three paths were failing the step
    # while the watchdog had worked perfectly: it cancelled the run, it
    # deliberately did NOT cancel an exempt run, or it is holding a pending
    # rerun. 63 of 64 repo-wide `failure` conclusions were these.
    local n
    n="$(grep -c "await signalByDesign(" "$SUT" || true)"
    [[ "$n" -eq 3 ]] ||
        log_fail "expected 3 by-design signal sites, found $n -- a path regressed to setFailed"
    log_pass "all 3 by-design paths signal without failing"
}

test_a_real_error_still_fails() {
    log_test "a REAL error must still setFailed -- 3b must not mute everything"
    # The whole value of 3b is that `failure` regains meaning. If the genuine
    # error path were converted too, the workflow could never report one.
    grep -q "core.setFailed(\`Run \${targetRunId} completed but the pending rerun could not be triggered\`)" "$SUT" ||
        log_fail "the genuine-error setFailed is gone; nothing can report a real watchdog failure"
    local real
    real="$(grep -c "^ *core.setFailed(" "$SUT" || true)"
    [[ "$real" -eq 1 ]] ||
        log_fail "expected exactly 1 real-error setFailed, found $real"
    log_pass "exactly one setFailed remains, and it is the real error"
}

test_summary_failure_does_not_swallow_the_verdict() {
    log_test "a summary that cannot be written must NOT suppress the failure"
    # The write is diagnostics; the annotation is the signal. If a throw from
    # core.summary could escape, the watchdog would exit 0 having cancelled a
    # pipeline -- a false green on the one path that matters most.
    local body
    body="$(awk '/^async function signalByDesign\(/,/^\}/' "$SUT")"
    grep -q 'catch' <<<"$body" ||
        log_fail "the summary write is unguarded; a throw would abort a path that had just worked"
    grep -q "typeof core.notice === 'function'" <<<"$body" ||
        log_fail "core.notice is called unguarded; an older @actions/core would throw"
    log_pass "summary and annotation are both guarded"
}

test_summary_names_the_monitored_run() {
    log_test "the summary must point at the run that actually failed"
    grep -q 'targetRunId' <<<"$(awk '/^async function signalByDesign\(/,/^\}/' "$SUT")" ||
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
    if grep -q "await signalByDesign(" "$mutant"; then
        rm -f "$mutant"
        log_fail "CONTROL DID NOT FIRE: the pre-fix annotation read as marked"
    fi
    rm -f "$mutant"
    log_pass "control: the pre-fix annotation is detectable"
}

test_by_design_paths_do_not_fail_the_step
test_a_real_error_still_fails
test_summary_failure_does_not_swallow_the_verdict
test_summary_names_the_monitored_run
test_retry_sweeper_still_excludes_this_workflow
test_control_marker_removal_is_detectable

echo
log_pass "watchdog by-design failure: 6/6"
echo "  Blind spot: asserts the source, not GitHub's rendering, and deliberately"
echo "  does not pin the prose -- only the by-design claim and the run id."
