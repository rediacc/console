#!/bin/bash
# Unit test for the binary-exec override in .ci/scripts/ci/watchdog-monitor.cjs.
#
# The classifier prompt allows a non-executable downloaded binary to be called
# transient (CDN flake). The guard exists so a genuinely corrupt cross-platform
# build cannot be auto-retried away: when every install-validation job in the run
# failed that way, the AI verdict is overridden to code-change. While the matrix
# is still running the guard defers, so the first platform to fail cannot spend
# the run's one retry before the other platforms report.

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
INSTALL_PATTERNS="$(sed -n "s/^ *WATCHDOG_INSTALL_VALIDATION_PATTERNS: *'\(.*\)'$/\1/p" "$CI_WORKFLOW")"
if [[ -z "$INSTALL_PATTERNS" ]]; then
    echo "could not read WATCHDOG_INSTALL_VALIDATION_PATTERNS from $CI_WORKFLOW" >&2
    exit 1
fi

# Runs evaluateBinaryExecGuard with a scenario and prints "<override>|<reason>",
# "defer|<reason>" when the guard defers, or "null" when it does not apply.
#
# $1 = name of the failing job
# $2 = log tail
# $3 = JSON array of jobs [{name,status,conclusion}]
run_guard() {
    node -e '
      const guard = require(process.argv[1]).evaluateBinaryExecGuard;
      const result = guard({
        job: { name: process.argv[2] },
        logTail: process.argv[3],
        jobs: JSON.parse(process.argv[4]),
        installPatterns: process.argv[5].split(",").map(s => s.trim()).filter(Boolean),
      });
      if (result === null) console.log("null");
      else if (result.defer) console.log(`defer|${result.reason}`);
      else console.log(`${result.override}|${result.reason}`);
    ' "$WATCHDOG" "$1" "$2" "$3" "$INSTALL_PATTERNS"
}

WINDOWS_LOG='rdc.exe : The term is not recognized
Program rdc.exe is not a valid application for this OS platform.
Error: Process completed with exit code 1.'

LINUX_LOG='+ ./rdc --version
./rdc: cannot execute binary file: Exec format error'

# Mirrors a real run: the six platform legs plus the aggregator, which downloads
# no binary and reports skipped once its needs fail.
ALL_FAILED='[
  {"name":"Validate Install Methods / Linux (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Linux (arm64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Windows (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Windows (arm64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / macOS (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / macOS (ARM64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Install Methods Complete","status":"completed","conclusion":"skipped"},
  {"name":"Quality","status":"completed","conclusion":"success"}
]'

ONE_FAILED='[
  {"name":"Validate Install Methods / Linux (x64)","status":"completed","conclusion":"success"},
  {"name":"Validate Install Methods / Windows (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / macOS (ARM64)","status":"completed","conclusion":"success"}
]'

STILL_RUNNING='[
  {"name":"Validate Install Methods / Linux (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Windows (x64)","status":"in_progress","conclusion":null}
]'

QUEUED_SIBLING='[
  {"name":"Validate Install Methods / Linux (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / macOS (ARM64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Windows (arm64)","status":"queued","conclusion":null}
]'

SKIPPED_SIBLING='[
  {"name":"Validate Install Methods / Linux (x64)","status":"completed","conclusion":"failure"},
  {"name":"Validate Install Methods / Windows (x64)","status":"completed","conclusion":"skipped"}
]'

test_module_still_callable_from_github_script() {
    local shape
    shape=$(node -e 'console.log(typeof require(process.argv[1]))' "$WATCHDOG")
    assert_eq "$shape" "function" "watchdog must still export the github-script entrypoint"
    log_pass "module.exports is still the callable monitor function"
}

# The guard can only work if a deferred job is left unhandled: marking it handled
# drops it from newFailures forever, so the matrix never gets re-evaluated and the
# corrupt build slips through on a retry. That lives in the monitor's closure, out
# of reach of the guard unit tests, so pin it at the source level.
test_deferred_job_is_not_marked_handled() {
    local in_defer_block adds
    in_defer_block=$(awk '/if \(guard\?\.defer\)/,/^      \}/' "$WATCHDOG" | grep -c 'handledJobs.add' || true)
    assert_eq "$in_defer_block" "0" "a deferred job must not be added to handledJobs"

    adds=$(grep -c 'handledJobs.add' "$WATCHDOG" || true)
    assert_eq "$adds" "1" "handledJobs.add must have exactly one call site (on the job actually handled)"
    log_pass "deferred jobs stay in newFailures for the next poll"
}

test_all_platforms_failed_overrides_to_code_change() {
    local out
    out=$(run_guard "Validate Install Methods / Windows (x64)" "$WINDOWS_LOG" "$ALL_FAILED")
    assert_contains "$out" "true|" "a fully failed install matrix must override to code-change"
    assert_contains "$out" "corrupt cross-platform build" "override reason names the corrupt build"
    log_pass "every install-validation job failing the same way overrides to code-change"
}

test_one_platform_failed_stays_transient() {
    local out
    out=$(run_guard "Validate Install Methods / Windows (x64)" "$WINDOWS_LOG" "$ONE_FAILED")
    assert_contains "$out" "false|" "a single-platform failure must not override the transient verdict"
    assert_contains "$out" "install-validation job(s) passed" "reason explains that other platforms passed"
    log_pass "one platform failing while others pass stays transient"
}

test_unfinished_matrix_defers() {
    local out
    out=$(run_guard "Validate Install Methods / Linux (x64)" "$LINUX_LOG" "$STILL_RUNNING")
    assert_contains "$out" "defer|" "an unfinished matrix must defer, not settle the verdict"
    assert_contains "$out" "have not finished" "reason explains the missing evidence"
    log_pass "running install sibling defers the decision"
}

test_queued_sibling_defers() {
    local out
    out=$(run_guard "Validate Install Methods / Linux (x64)" "$LINUX_LOG" "$QUEUED_SIBLING")
    assert_contains "$out" "defer|" "a queued install sibling must defer, not settle the verdict"
    log_pass "queued install sibling defers the decision"
}

test_skipped_sibling_stays_transient() {
    local out
    out=$(run_guard "Validate Install Methods / Linux (x64)" "$LINUX_LOG" "$SKIPPED_SIBLING")
    assert_contains "$out" "false|" "a finished-but-not-failed sibling is not evidence of a corrupt build"
    assert_contains "$out" "did not fail" "reason names the non-failing sibling"
    log_pass "completed sibling that did not fail stays transient"
}

test_non_install_job_is_ignored() {
    local out
    out=$(run_guard "Tests / Unit" "$LINUX_LOG" "$ALL_FAILED")
    assert_eq "$out" "null" "the guard must not apply outside install-validation jobs"
    log_pass "non install-validation job is left to the AI verdict"
}

test_other_failure_signature_is_ignored() {
    local out
    out=$(run_guard "Validate Install Methods / Linux (x64)" "curl: (56) Recv failure: Connection reset by peer" "$ALL_FAILED")
    assert_eq "$out" "null" "a download failure without the exec signature must not override"
    log_pass "install job failing without the binary-exec signature is left to the AI verdict"
}

test_workflow_sets_the_required_env_var() {
    local ci="$REPO_ROOT/.github/workflows/ci.yml"
    if ! grep -q "WATCHDOG_INSTALL_VALIDATION_PATTERNS:" "$ci"; then
        log_fail "ci.yml must set WATCHDOG_INSTALL_VALIDATION_PATTERNS (the watchdog throws without it)"
    fi
    log_pass "ci.yml wires WATCHDOG_INSTALL_VALIDATION_PATTERNS"
}

log_test "test-watchdog-binary-exec-guard"
test_module_still_callable_from_github_script
test_deferred_job_is_not_marked_handled
test_all_platforms_failed_overrides_to_code_change
test_one_platform_failed_stays_transient
test_unfinished_matrix_defers
test_queued_sibling_defers
test_skipped_sibling_stays_transient
test_non_install_job_is_ignored
test_other_failure_signature_is_ignored
test_workflow_sets_the_required_env_var
echo ""
log_pass "all tests passed"
