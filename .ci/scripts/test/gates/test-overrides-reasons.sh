#!/bin/bash
# Integration test for scripts/check-overrides-reasons.ts.
#
# Creates a temp package.json with known overrides + _overridesReasons combinations
# and verifies the validator accepts good reasons and rejects bogus ones.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

VALIDATOR="$REPO_ROOT/scripts/check-overrides-reasons.ts"

run_validator_with_pkg() {
    local pkg_content="$1"
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture TEMP at trap-set time, not at expansion time — we want
    # the specific path bound to the trap
    trap "rm -rf '$TEMP'" RETURN
    echo "$pkg_content" > "$TEMP/package.json"
    # Validator reads package.json relative to its own CONSOLE_ROOT calculation,
    # which is scripts/../ — so we need to copy scripts/ into TEMP.
    cp -r "$REPO_ROOT/scripts" "$TEMP/scripts"
    cd "$TEMP"
    local out rc=0
    out=$(npx tsx scripts/check-overrides-reasons.ts 2>&1) || rc=$?
    cd - >/dev/null
    echo "$out"
    return "$rc"
}

test_accepts_real_package_json() {
    # The actual repo package.json should pass.
    cd "$REPO_ROOT"
    if ! npx tsx scripts/check-overrides-reasons.ts >/dev/null 2>&1; then
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
