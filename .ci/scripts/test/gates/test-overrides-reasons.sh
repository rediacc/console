#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: node
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Integration test for scripts/gates/check-overrides-reasons.ts
# ---- end gate ----

# Integration test for scripts/gates/check-overrides-reasons.ts.
#
# Creates a temp package.json with known overrides + _overridesReasons combinations
# and verifies the validator accepts good reasons and rejects bogus ones.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

run_validator_with_pkg() {
    local pkg_content="$1"
    local TEMP
    TEMP="$(mktemp -d)"
    # BLOCKER: expanding TEMP now captures the specific temp path into the trap at set-time so RETURN fires the correct rm -rf even if TEMP is reassigned
    # shellcheck disable=SC2064
    # BLOCKER: capture TEMP at trap-set time, not at expansion time — we want
    # the specific path bound to the trap
    trap "rm -rf '$TEMP'" RETURN
    echo "$pkg_content" >"$TEMP/package.json"
    # Validator reads package.json relative to its own CONSOLE_ROOT calculation,
    # which is scripts/../ — so we need to copy scripts/ into TEMP.
    cp -r "$REPO_ROOT/scripts" "$TEMP/scripts"
    cd "$TEMP"
    local out rc=0
    # REDIACC_CI_ROOT POINTS THE COPIED VALIDATOR AT THE REAL PACKAGE. Since
    # 2026-09-09 scripts/lib/blocker-validator.ts is a client of
    # rediacc_ci.core.allowlist and resolves that package two directories above
    # its own file, which here is $TEMP. It refused loudly, which is the designed
    # behaviour and exactly wrong for a fixture: the low-effort case then asserted
    # on a "canonical validator could not be run" traceback instead of on the
    # verdict. Same override, same reason, as test-ci-job-aggregation.sh uses.
    out=$(REDIACC_CI_ROOT="$REPO_ROOT" npx tsx scripts/gates/check-overrides-reasons.ts 2>&1) || rc=$?
    cd - >/dev/null
    echo "$out"
    return "$rc"
}

test_accepts_real_package_json() {
    # The actual repo package.json should pass.
    cd "$REPO_ROOT"
    if ! npx tsx scripts/gates/check-overrides-reasons.ts >/dev/null 2>&1; then
        log_fail "real package.json should pass overrides-reasons validation"
    fi
    log_pass "real package.json passes validation"
}

test_rejects_missing_reason() {
    local out rc=0
    out=$(run_validator_with_pkg '{"overrides":{"somepkg":"^1.0.0"}}') || rc=$?
    assert_exit_code 1 "$rc" "missing reason should fail"
    assert_contains "$out" "has no matching _overridesReasons" "error message names the problem"
    log_pass "missing reason is rejected"
}

test_rejects_low_effort_reason() {
    local out rc=0
    out=$(run_validator_with_pkg '{"overrides":{"somepkg":"^1.0.0"},"_overridesReasons":{"somepkg":"tbd"}}') || rc=$?
    assert_exit_code 1 "$rc" "tbd reason should fail"
    assert_contains "$out" "low-effort placeholder" "error message identifies the issue"
    log_pass "low-effort reason is rejected"
}

test_rejects_stale_reason() {
    local out rc=0
    out=$(run_validator_with_pkg '{"overrides":{},"_overridesReasons":{"ghost":"BLOCKER: this reason has no corresponding override in the tree"}}') || rc=$?
    assert_exit_code 1 "$rc" "stale reason should fail"
    assert_contains "$out" "stale reason" "error message names drift"
    log_pass "stale (orphaned) reason is rejected"
}

log_test "test-overrides-reasons"
test_accepts_real_package_json
test_rejects_missing_reason
test_rejects_low_effort_reason
test_rejects_stale_reason
echo ""
log_pass "all tests passed"
