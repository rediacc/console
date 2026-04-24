#!/bin/bash
# Integration test for scripts/check-biome-reasons.ts.
#
# Builds a temp tree with crafted biome.json + sidecar combinations and
# verifies presence, quality, and drift detection.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

run_against_tree() {
    local tree="$1"
    local out rc=0
    cd "$tree"
    out=$(npx tsx scripts/check-biome-reasons.ts 2>&1) || rc=$?
    cd - >/dev/null
    echo "$out"
    return "$rc"
}

build_tree() {
    local tree="$1" biome_content="$2" sidecar_content="$3"
    cp -r "$REPO_ROOT/scripts" "$tree/scripts"
    mkdir -p "$tree/.ci/config"
    printf '%s' "$biome_content" >"$tree/biome.json"
    printf '%s' "$sidecar_content" >"$tree/.ci/config/biome-reasons.md"
}

test_accepts_real_repo() {
    cd "$REPO_ROOT"
    if ! npx tsx scripts/check-biome-reasons.ts >/dev/null 2>&1; then
        log_fail "real biome.json + biome-reasons.md should pass validation"
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
        '{"linter":{"enabled":false}}' \
        "# empty sidecar"
    local out rc=0
    out=$(run_against_tree "$TEMP") || rc=$?
    assert_exit_code 1 "$rc" "missing sidecar row must fail"
    assert_contains "$out" "linter.enabled=false" "names the key"
    log_pass "missing sidecar row is rejected"
}

test_low_effort_blocker_fails() {
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expand TEMP now so the trap binds the specific path
    trap "rm -rf '$TEMP'" RETURN
    build_tree "$TEMP" \
        '{"linter":{"enabled":false}}' \
        '<!-- biome-suppression:
key: linter.enabled=false
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
        '{"linter":{"enabled":false}}' \
        '<!-- biome-suppression:
key: linter.enabled=false
blocker: BLOCKER: ESLint handles lint for this codebase; biome runs format only to avoid duplicated diagnostics and rule conflicts
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
        '{}' \
        '<!-- biome-suppression:
key: linter.enabled=false
blocker: BLOCKER: stale row — biome.json no longer has this suppression so the reason should be removed
-->'
    local out rc=0
    out=$(run_against_tree "$TEMP") || rc=$?
    assert_exit_code 1 "$rc" "stale row must fail"
    assert_contains "$out" "stale row" "error names drift"
    log_pass "stale sidecar row is rejected"
}

log_test "test-biome-reasons"
test_accepts_real_repo
test_missing_row_fails
test_low_effort_blocker_fails
test_valid_row_passes
test_stale_row_fails
echo ""
log_pass "all tests passed"
