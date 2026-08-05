#!/bin/bash
# Tests for .ci/scripts/quality/run-external-gate.sh, the wrapper that gives
# externally-dependent quality gates their three-state behaviour (hard on a
# normal PR, absent on a labelled PR via the step `if:`, soft on schedule).
#
# Every direction is exercised with a REAL child process, and both failure
# directions are proven able to fire: a soft failure that exits non-zero or a
# hard failure that exits zero would each silently break the design in the
# dangerous direction (a red nightly nobody wanted, or a green PR that should
# have blocked).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WRAPPER="$SCRIPT_DIR/../../quality/run-external-gate.sh"
[ -x "$WRAPPER" ] || {
    log_fail "wrapper not found or not executable: $WRAPPER"
    exit 1
}

# run_wrapper <mode-or-UNSET> <expected-exit> <label> [cmd...]
# Captures stdout+stderr and the real exit code without tripping set -e.
OUT=""
run_wrapper() {
    local mode="$1" expected="$2" label="$3"
    shift 3
    local rc=0
    if [ "$mode" = "UNSET" ]; then
        OUT="$(env -u EXTERNAL_QUALITY_MODE "$WRAPPER" "$@" 2>&1)" || rc=$?
    else
        OUT="$(EXTERNAL_QUALITY_MODE="$mode" "$WRAPPER" "$@" 2>&1)" || rc=$?
    fi
    if [ "$rc" -ne "$expected" ]; then
        log_fail "$label: expected exit $expected, got $rc (output: $OUT)"
    fi
}

test_soft_failure_is_green_with_warning() {
    run_wrapper soft 0 "soft mode swallows a failure" false
    case "$OUT" in
        *"::warning::"*) ;;
        *) log_fail "soft failure must emit a ::warning:: annotation, got: $OUT" ;;
    esac
    log_pass "soft mode: failing command exits 0 and warns"
}

test_hard_failure_blocks_with_original_code() {
    # CONTROL for the case above: the same failing command must still fail in
    # hard mode, and with ITS exit code, not a generic 1.
    run_wrapper hard 3 "hard mode preserves the exit code" bash -c 'exit 3'
    case "$OUT" in
        *"::warning::"*) log_fail "hard failure must not emit the soft warning: $OUT" ;;
        *) ;;
    esac
    log_pass "hard mode: failing command keeps exit code 3, no warning"
}

test_success_is_silent_in_both_modes() {
    run_wrapper soft 0 "soft mode passes a success through" true
    case "$OUT" in
        *"::warning::"*) log_fail "a passing command must not warn in soft mode: $OUT" ;;
        *) ;;
    esac
    run_wrapper hard 0 "hard mode passes a success through" true
    log_pass "success exits 0 with no warning in both modes"
}

test_unset_mode_fails_closed_to_hard() {
    # A wiring break (env var never reaches the step) must behave as HARD:
    # silently going soft would disable a blocking gate with no visible trace.
    run_wrapper UNSET 1 "unset mode is hard" false
    log_pass "unset EXTERNAL_QUALITY_MODE fails closed to hard"
}

test_unknown_mode_refuses() {
    # Same fail-closed logic one step further: an unknown value is a wiring
    # bug and must refuse loudly even when the wrapped command SUCCEEDS.
    run_wrapper sideways 2 "unknown mode refuses" true
    case "$OUT" in
        *"unknown EXTERNAL_QUALITY_MODE"*) ;;
        *) log_fail "unknown mode must name itself in the refusal: $OUT" ;;
    esac
    log_pass "unknown mode refuses (exit 2) even around a passing command"
}

test_no_command_refuses() {
    run_wrapper hard 2 "no command refuses" || true
    log_pass "missing command refuses with usage"
}

test_soft_failure_writes_step_summary() {
    local tmp
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' RETURN
    local rc=0
    EXTERNAL_QUALITY_MODE=soft GITHUB_STEP_SUMMARY="$tmp" "$WRAPPER" false >/dev/null 2>&1 || rc=$?
    [ "$rc" -eq 0 ] || log_fail "soft failure with summary should still exit 0, got $rc"
    grep -q "External gate soft-failed" "$tmp" ||
        log_fail "step summary not written: $(cat "$tmp")"
    log_pass "soft failure writes the step summary when GITHUB_STEP_SUMMARY is set"
}

test_soft_failure_is_green_with_warning
test_hard_failure_blocks_with_original_code
test_success_is_silent_in_both_modes
test_unset_mode_fails_closed_to_hard
test_unknown_mode_refuses
test_no_command_refuses
test_soft_failure_writes_step_summary

log_pass "all tests passed"
