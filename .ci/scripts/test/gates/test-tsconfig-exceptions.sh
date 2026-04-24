#!/bin/bash
# Integration test for scripts/check-tsconfig-exceptions.ts.
#
# Builds a temp tree with crafted tsconfigs + sidecar combinations and
# verifies presence, quality, and drift detection.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

VALIDATOR_SRC="$REPO_ROOT/scripts/check-tsconfig-exceptions.ts"

# Run the validator against a temp CONSOLE_ROOT. The script resolves paths
# relative to __dirname of scripts/, so we copy scripts/ + .ci/config/ into
# a fresh tree and populate the crafted tsconfig tree inside it.
run_against_tree() {
    local tree="$1"
    local out rc=0
    cd "$tree"
    out=$(npx tsx scripts/check-tsconfig-exceptions.ts 2>&1) || rc=$?
    cd - >/dev/null
    echo "$out"
    return "$rc"
}

build_tree() {
    local tree="$1" tsconfig_content="$2" sidecar_content="$3"
    cp -r "$REPO_ROOT/scripts" "$tree/scripts"
    mkdir -p "$tree/.ci/config"
    printf '%s' "$sidecar_content" >"$tree/.ci/config/tsconfig-exceptions.md"
    mkdir -p "$tree/packages/demo"
    printf '%s' "$tsconfig_content" >"$tree/packages/demo/tsconfig.json"
}

test_accepts_real_repo() {
    cd "$REPO_ROOT"
    if ! npx tsx scripts/check-tsconfig-exceptions.ts >/dev/null 2>&1; then
        log_fail "real repo sidecar + tsconfigs should pass validation"
    fi
    log_pass "real repo passes validation"
}

test_missing_row_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    build_tree "$TEMP" \
        '{"compilerOptions":{"skipLibCheck":true,"strict":true}}' \
        "# empty sidecar"
    local out rc=0
    out=$(run_against_tree "$TEMP") || rc=$?
    assert_exit_code 1 "$rc" "missing row must fail"
    assert_contains "$out" "skipLibCheck" "names the flag"
    assert_contains "$out" "packages/demo/tsconfig.json" "names the file"
    log_pass "missing sidecar row is rejected"
}

test_low_effort_blocker_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    build_tree "$TEMP" \
        '{"compilerOptions":{"skipLibCheck":true,"strict":true}}' \
        '<!-- tsconfig-exception:
path: packages/demo/tsconfig.json
flag: skipLibCheck
blocker: tbd
-->'
    local out rc=0
    out=$(run_against_tree "$TEMP") || rc=$?
    assert_exit_code 1 "$rc" "low-effort reason must fail"
    assert_contains "$out" "low-effort placeholder" "names the issue"
    log_pass "low-effort BLOCKER is rejected"
}

test_valid_row_passes() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    build_tree "$TEMP" \
        '{"compilerOptions":{"skipLibCheck":true,"strict":true}}' \
        '<!-- tsconfig-exception:
path: packages/demo/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention; compiling node_modules .d.ts would add 10+ seconds per tsc pass
-->'
    local out rc=0
    out=$(run_against_tree "$TEMP") || rc=$?
    assert_exit_code 0 "$rc" "valid row must pass"
    log_pass "valid row is accepted"
}

test_stale_row_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    build_tree "$TEMP" \
        '{"compilerOptions":{"strict":true}}' \
        '<!-- tsconfig-exception:
path: packages/demo/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: stale row — the actual tsconfig above no longer disables skipLibCheck
-->'
    local out rc=0
    out=$(run_against_tree "$TEMP") || rc=$?
    assert_exit_code 1 "$rc" "stale row must fail"
    assert_contains "$out" "stale row" "error names drift"
    log_pass "stale sidecar row is rejected"
}

log_test "test-tsconfig-exceptions"
test_accepts_real_repo
test_missing_row_fails
test_low_effort_blocker_fails
test_valid_row_passes
test_stale_row_fails
echo ""
log_pass "all tests passed"
