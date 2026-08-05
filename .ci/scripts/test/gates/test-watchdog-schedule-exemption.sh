#!/bin/bash
# Unit test for the cancel-exemption in .ci/scripts/ci/watchdog-monitor.cjs.
#
# WHAT BROKE. Cancelling a run REWRITES ITS CONCLUSION. A run whose job genuinely
# failed reports `conclusion: failure`; the same run, force-cancelled by the
# watchdog, reports `conclusion: cancelled` -- and every reader treats
# `cancelled` as "superseded by a newer push, ignore me".
#
# On a PR that is survivable: a human is watching, and the next push supersedes
# the run anyway. On the NIGHTLY it is fatal. `full_suite` is
# `github.event_name != 'push'`, so push-to-main runs no tests at all and the
# nightly is the ONLY thing validating main. Measured 2026-07-27:
#
#   gh run list --workflow ci.yml --event schedule -L 12
#     -> TWELVE cancelled, ZERO success, unbroken back to 2026-07-16
#
# Every one of those nights had a real, fixable gate failure (Stage Artifacts on
# the empty schedule channel; the actions-freshness gate; a dev audit advisory).
# None were noticed, because the rollup said `cancelled`. The gate breaks were
# the symptom. This laundering is why they survived twelve days.
#
# WHY A LABEL COULD NOT SAVE IT. Labels are read from the PR, and a `schedule`
# run has no PR: `prNumber` is null and the whole label block is skipped. The
# nightly is structurally incapable of wearing a PR-side escape hatch, so the
# exemption has to live in code.
#
# WHY A UNIT TEST AND NOT A MIRROR. Re-implementing the boolean here would prove
# nothing about the watchdog. This calls the exported decision, reads the exempt
# list out of the REAL module, and checks the real ci.yml still has the schedule
# trigger the exemption exists for.
#
# Both directions matter:
#   - Too quiet: the nightly keeps laundering failures into `cancelled`.
#   - Too loud: a PR run stops being cancellable, so one red would burn the full
#     E2E fleet instead of being killed at the first failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"

# exempt <run-event> -> "exempt" | "cancel"
exempt() {
    node -e '
const w = require(process.argv[1]);
const v = w.evaluateCancelExemption({ runEvent: process.argv[2] });
process.stdout.write(v.exempt ? "exempt" : "cancel");
' "$WATCHDOG" "$1"
}

# exempt_missing <"null"|"undefined"> -> "exempt" | "cancel"
exempt_missing() {
    node -e '
const w = require(process.argv[1]);
const v = w.evaluateCancelExemption({ runEvent: process.argv[2] === "null" ? null : undefined });
process.stdout.write(v.exempt ? "exempt" : "cancel");
' "$WATCHDOG" "$1"
}

# ---------------------------------------------------------------------------

test_exempt_list_is_real() {
    # Anti-vacuity #1: read the list out of the module. If `schedule` were
    # dropped from it, every case below would pass for the wrong reason.
    local list
    list="$(node -e 'process.stdout.write(require(process.argv[1]).CANCEL_EXEMPT_EVENTS.join(","))' "$WATCHDOG")"
    assert_contains "$list" "schedule" "watchdog-monitor.cjs still exempts the schedule event"
    log_pass "reading the real CANCEL_EXEMPT_EVENTS from the module ($list)"
}

test_ci_still_has_a_schedule_trigger() {
    # Anti-vacuity #2: the exemption is dead code if ci.yml has no nightly. This
    # is the check that would have caught "the nightly was quietly removed" as
    # loudly as it catches "the exemption was quietly removed".
    assert_contains "$(cat "$CI_WORKFLOW")" "schedule:" \
        "ci.yml still has a schedule trigger for the exemption to protect"
    log_pass "ci.yml still defines the nightly the exemption exists for"
}

test_schedule_is_exempt() {
    # The fix. This returned "cancel" before it, on all twelve measured nights.
    assert_eq "$(exempt schedule)" "exempt" \
        "a scheduled run must never be cancelled, so its failure reports as failure"
    log_pass "schedule runs are exempt from force-cancel"
}

test_pull_request_still_cancels() {
    # The PR path must be byte-identical. Force-cancelling a red PR run is what
    # stops a lint error from burning the 44-minute E2E fleet.
    assert_eq "$(exempt pull_request)" "cancel" \
        "pull_request runs must still be cancellable (unchanged behaviour)"
    log_pass "pull_request runs still force-cancel"
}

test_push_still_cancels() {
    assert_eq "$(exempt push)" "cancel" \
        "push-to-main runs must still be cancellable (unchanged behaviour)"
    log_pass "push runs still force-cancel"
}

test_workflow_dispatch_is_exempt() {
    # THIS REVERSES AN EARLIER DECISION IN THIS SAME FILE, so the reasoning is
    # recorded rather than silently swapped.
    #
    # The first version asserted the opposite, on two grounds: that a dispatch is
    # something a human just asked for and is watching, so a `cancelled`
    # rehearsal would be read correctly; and that cancelling saves the fleet from
    # burning on a failure the first red already proved.
    #
    # Both are wrong for this pipeline.
    #
    # The second is wrong on its own measured terms: machine-minutes are flat at
    # roughly 500 per run and FREE on a public repo, which the program's own
    # baseline states. They are not the scarce resource. INFORMATION PER ROUND
    # is: the nightly stayed broken for twelve nights partly because each round
    # surfaced one gate at a time. A force-cancel stops the run at the FIRST
    # failure, so a rehearsal would report one broken gate per 70-minute round
    # and re-impose exactly the serialisation the rehearsal exists to remove.
    # Running the full fleet to completion enumerates every nightly breakage in
    # ONE round, and that is the whole point of having a rehearsal at all.
    #
    # The first is wrong because it makes the rehearsal's conclusion mean
    # something different from the nightly's. `ci.yml` calls the dispatch path
    # "schedule-equivalent BY CONSTRUCTION"; a tool built to prove the nightly's
    # conclusion is honest must not launder its own.
    assert_eq "$(exempt workflow_dispatch)" "exempt" \
        "the dispatch rehearsal must report failure as failure, like the nightly it stands in for"
    log_pass "workflow_dispatch (the nightly rehearsal) is exempt from force-cancel"
}

test_unknown_event_fails_closed() {
    # An event nobody anticipated must behave like today, not like the nightly.
    assert_eq "$(exempt merge_group)" "cancel" "an unanticipated event must fail closed"
    assert_eq "$(exempt '')" "cancel" "an empty event must fail closed"
    assert_eq "$(exempt_missing null)" "cancel" "a null event must fail closed"
    assert_eq "$(exempt_missing undefined)" "cancel" "a missing event must fail closed"
    log_pass "unknown, empty, null and missing events all fail closed to cancel"
}

test_matching_is_exact_not_fuzzy() {
    # Guards against somebody "improving" this into a substring or case-
    # insensitive match, which would silently exempt events nobody vetted.
    assert_eq "$(exempt Schedule)" "cancel" "matching is case-sensitive"
    assert_eq "$(exempt schedules)" "cancel" "matching is exact, not a prefix"
    assert_eq "$(exempt pre-schedule)" "cancel" "matching is exact, not a substring"
    log_pass "the exempt match is exact, not fuzzy"
}

test_exemption_is_checked_before_the_cancel_api_call() {
    # THE ORDERING GUARD, and the reason this test is not just a boolean check.
    # The exemption is only worth anything if forceCancel consults it BEFORE it
    # calls the cancel API. The sibling gate test in this directory exists
    # because of a pure ordering bug of exactly this shape: a branch returned
    # before the check that was supposed to govern it, and the log cheerfully
    # asserted the opposite of the behaviour.
    # Anchor on the CALL SITE, not the definition. The first draft of this test
    # grepped `evaluateCancelExemption({ runEvent`, which also matches
    # `function evaluateCancelExemption({ runEvent })` -- so it measured the
    # definition's position and would have passed with the call site AFTER the
    # cancel, i.e. it proved nothing at all. Caught by reading the line number
    # it reported (97, the definition) instead of trusting the green.
    local check_line cancel_line
    check_line="$(grep -n 'const exemption = evaluateCancelExemption(' "$WATCHDOG" | head -1 | cut -d: -f1 || true)"
    cancel_line="$(grep -n 'actions/runs/{run_id}/force-cancel' "$WATCHDOG" | head -1 | cut -d: -f1 || true)"

    if [[ -z "$check_line" || -z "$cancel_line" ]]; then
        log_fail "could not locate both the exemption check and the force-cancel API call in $WATCHDOG"
    fi
    if ((check_line >= cancel_line)); then
        log_fail "the exemption check (line $check_line) must precede the force-cancel API call (line $cancel_line)"
    fi
    log_pass "the exemption is consulted at line $check_line, before the cancel API call at line $cancel_line"
}

test_single_chokepoint() {
    # The exemption lives inside forceCancel precisely so every call site
    # inherits it, including the no-drain Review Gate path. If somebody adds
    # a direct cancel API call elsewhere in the file, it would bypass the
    # exemption entirely -- so assert there is exactly one of each.
    local force_cancels regular_cancels
    force_cancels="$(grep -c 'actions/runs/{run_id}/force-cancel' "$WATCHDOG")"
    regular_cancels="$(grep -c 'cancelWorkflowRun' "$WATCHDOG")"
    assert_eq "$force_cancels" "1" "exactly one force-cancel API call, so the exemption cannot be bypassed"
    assert_eq "$regular_cancels" "1" "exactly one fallback cancel API call, inside the same guarded function"
    log_pass "cancellation has a single chokepoint that the exemption governs"
}

log_test "test-watchdog-schedule-exemption"
test_exempt_list_is_real
test_ci_still_has_a_schedule_trigger
test_schedule_is_exempt
test_pull_request_still_cancels
test_push_still_cancels
test_workflow_dispatch_is_exempt
test_unknown_event_fails_closed
test_matching_is_exact_not_fuzzy
test_exemption_is_checked_before_the_cancel_api_call
test_single_chokepoint
echo ""
log_pass "all tests passed"
