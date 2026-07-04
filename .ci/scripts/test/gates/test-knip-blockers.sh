#!/bin/bash
# Integration test for scripts/check-knip-blockers.ts.
#
# Creates temp knip.jsonc fixtures with known suppression + BLOCKER
# combinations and verifies the validator accepts covered entries and
# rejects uncovered or low-effort ones. Staleness of ignore entries is
# knip's own job (--treat-config-hints-as-errors), not this validator's.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

run_validator_with_config() {
    local config_content="$1"
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture TEMP at trap-set time, not at expansion time — we want
    # the specific path bound to the trap
    trap "rm -rf '$TEMP'" RETURN
    echo "$config_content" >"$TEMP/knip.jsonc"
    local out rc=0
    out=$(cd "$REPO_ROOT" && npx tsx scripts/check-knip-blockers.ts --config "$TEMP/knip.jsonc" 2>&1) || rc=$?
    echo "$out"
    return "$rc"
}

test_accepts_real_config() {
    cd "$REPO_ROOT"
    if [[ ! -f knip.jsonc ]]; then
        log_fail "knip.jsonc missing at repo root"
    fi
    if ! npx tsx scripts/check-knip-blockers.ts >/dev/null 2>&1; then
        log_fail "real knip.jsonc should pass BLOCKER validation"
    fi
    log_pass "real knip.jsonc passes validation"
}

test_accepts_group_blocker() {
    local out rc=0
    out=$(run_validator_with_config '{
  "ignoreBinaries": [
    // BLOCKER: platform terminal emulators probed via child_process at runtime, never npm-managed
    "konsole",
    "xterm"
  ]
}') || rc=$?
    assert_exit_code 0 "$rc" "grouped BLOCKER should cover following entries"
    log_pass "group BLOCKER covers multiple entries"
}

test_rejects_missing_blocker() {
    local out rc=0
    out=$(run_validator_with_config '{
  "ignoreDependencies": [
    "some-package"
  ]
}') || rc=$?
    assert_exit_code 1 "$rc" "entry without BLOCKER should fail"
    assert_contains "$out" "missing a" "error message names the problem"
    log_pass "missing BLOCKER is rejected"
}

test_rejects_low_effort_blocker() {
    local out rc=0
    out=$(run_validator_with_config '{
  "ignoreDependencies": [
    // BLOCKER: tbd
    "some-package"
  ]
}') || rc=$?
    assert_exit_code 1 "$rc" "low-effort BLOCKER should fail"
    assert_contains "$out" "low-effort placeholder" "error message identifies the issue"
    log_pass "low-effort BLOCKER is rejected"
}

test_blank_line_resets_blocker() {
    local out rc=0
    out=$(run_validator_with_config '{
  "ignoreBinaries": [
    // BLOCKER: platform terminal emulators probed via child_process at runtime, never npm-managed
    "konsole",

    "xterm"
  ]
}') || rc=$?
    assert_exit_code 1 "$rc" "entry after blank line should not inherit BLOCKER"
    assert_contains "$out" "xterm" "the uncovered entry is named"
    log_pass "blank line resets BLOCKER coverage"
}

test_entry_project_exempt() {
    local out rc=0
    out=$(run_validator_with_config '{
  "workspaces": {
    "packages/foo": {
      "entry": [
        "src/index.ts"
      ],
      "project": [
        "src/**/*.ts"
      ]
    }
  }
}') || rc=$?
    assert_exit_code 0 "$rc" "entry/project globs are configuration, not suppressions"
    log_pass "entry/project arrays are exempt"
}

log_test "test-knip-blockers"
test_accepts_real_config
test_accepts_group_blocker
test_rejects_missing_blocker
test_rejects_low_effort_blocker
test_blank_line_resets_blocker
test_entry_project_exempt
echo ""
log_pass "all tests passed"
