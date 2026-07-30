#!/bin/bash
# Unit test for the supersession verdict in .ci/scripts/ci/watchdog-monitor.cjs.
#
# WHAT BROKE. Measured on real traffic 2026-07-30, watchdog run 30534675663
# monitoring console run 30530991847 on branch 0730-2:
#
#   [0m] Run: in_progress | Jobs: 10 done, 7 running, 0 queued, 0 failed, 2 cancelled
#   [logs] captured the full log for "Quality / Content" (61415 bytes) before any retry
#   Retrying: classifier returned transient at confidence 0.8 -- treating as transient
#   ##[error]Job cancelled (likely manual / supersession): "Quality / Content"
#   [1m] Run: in_progress | Jobs: 19 done, 1 running, 0 queued, 0 failed, 11 cancelled
#   Workflow externally cancelled (11/19 jobs cancelled) - exiting
#
# A push created run 30534726467 fifteen seconds before that first poll, which
# cancelled 30530991847 by concurrency group. The watchdog treated the
# superseded jobs as failures: it spent a billed Workers AI classification and
# called core.setFailed, so step 4 concluded FAILURE for a run nobody broke.
#
# WHY THE EXISTING GUARD COULD NOT SAVE IT. The mass-cancellation check only
# fires once `cancelled >= completed / 2`. During a supersession the jobs flip a
# few at a time, so on the first poll the ratio is nowhere near met (2 of 10
# here), and by the time it is met setFailed has already stuck to the step. A
# ratio cannot express "something newer replaced me".
#
# WHY IT MATTERS. This is the mirror image of the cancel-exemption defect tested
# in test-watchdog-schedule-exemption.sh. That one laundered `failure` into
# `cancelled` and hid twelve red nightlies. This one reports `failure` for the
# most ordinary event in the repo, pushing a new commit, which trains the
# operator to ignore watchdog reds until a real one goes unread.
#
# BOTH DIRECTIONS MATTER, and this gate is deliberately lopsided about which is
# worse:
#   - Too loud (today): every superseded run reports red, and the classifier is
#     billed for it.
#   - Too quiet (the danger the fix introduces): a genuine failure gets waved
#     through as "just a supersession" and nobody ever sees it. That is strictly
#     worse, which is why the verdict requires ALL THREE conditions and why the
#     unreadable-lookup case below must resolve to NOT superseded.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"

# verdict <failedCount> <normalCancelledCount> <newerRunExists:true|false|missing>
#   -> "superseded" | "normal"
verdict() {
    node -e '
const w = require(process.argv[1]);
const newer = process.argv[4] === "missing" ? undefined : process.argv[4] === "true";
const v = w.evaluateSupersession({
  failedCount: Number(process.argv[2]),
  normalCancelledCount: Number(process.argv[3]),
  newerRunExists: newer,
});
process.stdout.write(v.superseded ? "superseded" : "normal");
' "$WATCHDOG" "$2" "$3" "$4"
}

# ---------------------------------------------------------------------------

test_the_predicate_is_real() {
    # Anti-vacuity: if evaluateSupersession were not exported, every `verdict`
    # call below would throw rather than silently pass, but a typo in the export
    # name would make the whole suite meaningless in a quieter way. Read it.
    local typeof
    typeof="$(node -e 'process.stdout.write(typeof require(process.argv[1]).evaluateSupersession)' "$WATCHDOG")"
    assert_eq "$typeof" "function" "watchdog-monitor.cjs must export evaluateSupersession"
    log_pass "reading the real evaluateSupersession from the module"
}

test_the_measured_incident_is_now_quiet() {
    # THE CONTROL, SILENT DIRECTION. These are the exact numbers from the [0m]
    # poll of watchdog run 30534675663: zero failed, two cancelled, and run
    # 30534726467 already existing. Before the fix this reached the classifier
    # and setFailed.
    assert_eq "$(verdict _ 0 2 true)" "superseded" \
        "0 failed + 2 cancelled + a newer run is the measured supersession signature"
    log_pass "the 2026-07-30 incident (run 30530991847) is now recognised as supersession"
}

test_a_real_failure_still_fires_even_with_a_newer_run() {
    # THE CONTROL, FIRE DIRECTION, and the single most important case in this
    # file. Pushing a fix while the old run is still red is the NORMAL way this
    # situation arises, so "a newer run exists" must never on its own excuse a
    # failure. If this ever returns "superseded", the watchdog has gone blind.
    assert_eq "$(verdict _ 1 2 true)" "normal" \
        "one genuinely failed job must still report, even though a newer run exists"
    log_pass "a real failure is never laundered as supersession"
}

test_cancellations_without_a_newer_run_still_fire() {
    # A manual cancel, or a job hitting its own timeout, produces cancellations
    # with NO newer run. That is not supersession and must behave as it does
    # today.
    assert_eq "$(verdict _ 0 2 false)" "normal" \
        "cancellations with no newer run are not supersession"
    log_pass "cancellation without a newer run still reports normally"
}

test_a_healthy_run_is_not_superseded() {
    # No failures and no cancellations is simply a healthy run. It must not
    # match, or the watchdog would exit early on every poll of every green run.
    assert_eq "$(verdict _ 0 0 true)" "normal" \
        "a run with nothing cancelled is not superseded, however new the neighbour"
    log_pass "a healthy run is never treated as superseded"
}

test_unreadable_lookup_fails_closed() {
    # hasNewerRun returns false on any API error. Prove the predicate treats a
    # missing answer as NOT superseded, so an outage costs a spurious red rather
    # than a swallowed failure.
    assert_eq "$(verdict _ 0 2 missing)" "normal" \
        "an unknown newer-run answer must fail closed to NOT superseded"
    log_pass "an unreadable newer-run lookup fails closed"
}

test_truthiness_is_not_accepted_for_newer_run() {
    # `newerRunExists === true` is a strict comparison on purpose: hasNewerRun
    # returns a real boolean, and a truthy-but-not-true value (a string, an
    # object from a refactored return shape) must not be read as a yes.
    local got
    got="$(node -e '
const w = require(process.argv[1]);
const v = w.evaluateSupersession({ failedCount: 0, normalCancelledCount: 2, newerRunExists: "yes" });
process.stdout.write(v.superseded ? "superseded" : "normal");
' "$WATCHDOG")"
    assert_eq "$got" "normal" "a truthy non-boolean must not satisfy newerRunExists"
    log_pass "newerRunExists is compared strictly, not for truthiness"
}

test_verdict_is_checked_before_classification() {
    # ORDERING IS THE WHOLE FIX. Reaching classifyFailure is what spends the
    # billed AI request and what leads to core.setFailed; a supersession check
    # placed after it would be decorative. Assert the call site ordering in the
    # real file.
    local check_line classify_line
    check_line="$(grep -n 'evaluateSupersession({' "$WATCHDOG" | tail -1 | cut -d: -f1)"
    classify_line="$(grep -n 'classifyFailure(' "$WATCHDOG" | tail -1 | cut -d: -f1)"
    if [[ -z "$check_line" || -z "$classify_line" ]]; then
        log_fail "could not locate both the supersession check and classifyFailure in $WATCHDOG"
        exit 1
    fi
    if [[ "$check_line" -ge "$classify_line" ]]; then
        log_fail "supersession is checked at line $check_line, at or after classifyFailure at line $classify_line"
        exit 1
    fi
    log_pass "supersession is checked at line $check_line, before classifyFailure at line $classify_line"
}

test_the_api_lookup_fails_closed_in_source() {
    # The predicate cannot protect itself from hasNewerRun throwing. Assert the
    # catch arm exists and returns false, because a `throw` escaping there would
    # crash the poll loop and a `return true` would swallow failures wholesale.
    local body
    body="$(sed -n '/^async function hasNewerRun/,/^}/p' "$WATCHDOG")"
    assert_contains "$body" "catch" "hasNewerRun must catch lookup errors"
    assert_contains "$body" "return false" "hasNewerRun must resolve an error to false"
    log_pass "hasNewerRun fails closed on an unreadable lookup"
}

log_test "test-watchdog-supersession"
test_the_predicate_is_real
test_the_measured_incident_is_now_quiet
test_a_real_failure_still_fires_even_with_a_newer_run
test_cancellations_without_a_newer_run_still_fire
test_a_healthy_run_is_not_superseded
test_unreadable_lookup_fails_closed
test_truthiness_is_not_accepted_for_newer_run
test_verdict_is_checked_before_classification
test_the_api_lookup_fails_closed_in_source
echo ""
log_pass "all tests passed"
