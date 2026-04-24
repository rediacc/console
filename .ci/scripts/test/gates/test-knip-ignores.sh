#!/bin/bash
# Integration test for scripts/run-knip.ts (the wrapper) and .knip-ignores
# (the sidecar). Confirms:
#   1. The sidecar parses and every entry has a BLOCKER-quality reason.
#   2. The real repo run of run-knip.ts exits 0.
#   3. A crafted sidecar with a banned-phrase reason causes the wrapper
#      to exit 1 before invoking knip.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

test_real_repo_passes() {
    cd "$REPO_ROOT"
    if ! npx tsx scripts/run-knip.ts --treat-config-hints-as-errors >/dev/null 2>&1; then
        log_fail "real repo run-knip.ts should exit 0"
    fi
    log_pass "real repo passes run-knip.ts wrapper"
}

test_sidecar_blockers_all_valid() {
    cd "$REPO_ROOT"
    # Run the wrapper in a mode that triggers only BLOCKER validation and
    # then short-circuits. We accomplish this by pointing knip at a config
    # that is known to pass — the current tree does — and confirming the
    # wrapper completes normally.
    local out rc=0
    out=$(npx tsx scripts/run-knip.ts --treat-config-hints-as-errors 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "wrapper must succeed on clean tree"
    # Any validation failure would print "✗ .knip-ignores entries failed".
    assert_not_contains "$out" ".knip-ignores entries failed" "no validation failures emitted"
    log_pass "all .knip-ignores entries pass BLOCKER validation"
}

test_crafted_bad_blocker_is_rejected() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    # Stage a mock tree with the wrapper + a bad sidecar.
    cp -r "$REPO_ROOT/scripts" "$TEMP/scripts"
    cp "$REPO_ROOT/knip.json" "$TEMP/knip.json"
    printf '%s\n%s\n' "# BLOCKER: tbd" "some-package" >"$TEMP/.knip-ignores"
    ln -s "$REPO_ROOT/node_modules" "$TEMP/node_modules"
    ln -s "$REPO_ROOT/packages" "$TEMP/packages"
    cd "$TEMP"
    local out rc=0
    out=$(npx tsx scripts/run-knip.ts --treat-config-hints-as-errors 2>&1) || rc=$?
    cd - >/dev/null
    assert_exit_code 1 "$rc" "bad BLOCKER must cause the wrapper to fail"
    assert_contains "$out" "low-effort placeholder" "error names the issue"
    log_pass "low-effort BLOCKER is rejected before knip runs"
}

log_test "test-knip-ignores"
test_real_repo_passes
test_sidecar_blockers_all_valid
test_crafted_bad_blocker_is_rejected
echo ""
log_pass "all tests passed"
