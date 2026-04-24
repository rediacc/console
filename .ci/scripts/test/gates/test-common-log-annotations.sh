#!/bin/bash
# Regression test for .ci/scripts/lib/common.sh log_error / log_warn.
#
# Contract: in CI (CI=true), these functions emit GitHub Actions annotations
# (::error:: / ::warning::). Locally, they emit coloured output. This matches
# the contract of .ci/scripts/lib/emit-advisory.sh and keeps AI navigability
# consistent across every script that sources common.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

COMMON_SH="$REPO_ROOT/.ci/scripts/lib/common.sh"

run_in_env() {
    # Run `log_error`/`log_warn` in a fresh bash with CI set (or unset).
    # Using export rather than the `VAR=val cmd` per-command form because
    # `source` is a builtin and some bash versions don't propagate the
    # pre-command assignment into the builtin's execution environment.
    local env_assignment="$1" fn="$2"
    shift 2
    local args=""
    for a in "$@"; do args="$args \"$a\""; done
    env -i PATH="$PATH" bash -c "$env_assignment; source '$COMMON_SH'; $fn $args" 2>&1
}

test_log_error_in_ci_emits_annotation() {
    local out
    out=$(run_in_env "export CI=true" log_error "oh no")
    assert_contains "$out" "::error::oh no" "CI=true must prefix with ::error::"
    log_pass "log_error emits ::error:: annotation in CI"
}

test_log_warn_in_ci_emits_annotation() {
    local out
    out=$(run_in_env "export CI=true" log_warn "careful")
    assert_contains "$out" "::warning::careful" "CI=true must prefix with ::warning::"
    log_pass "log_warn emits ::warning:: annotation in CI"
}

test_log_error_locally_keeps_colour() {
    local out
    out=$(run_in_env ":" log_error "local fail")
    assert_contains "$out" "local fail" "message is preserved"
    assert_not_contains "$out" "::error::" "no GitHub annotation outside CI"
    log_pass "log_error locally emits plain-text with no annotation"
}

test_log_warn_locally_keeps_colour() {
    local out
    out=$(run_in_env ":" log_warn "local warn")
    assert_contains "$out" "local warn" "message is preserved"
    assert_not_contains "$out" "::warning::" "no GitHub annotation outside CI"
    log_pass "log_warn locally emits plain-text with no annotation"
}

test_multi_word_message_preserved() {
    local out
    out=$(run_in_env "export CI=true" log_error "message with multiple words")
    assert_contains "$out" "::error::message with multiple words" "all words included"
    log_pass "multi-word arguments survive annotation wrapping"
}

log_test "test-common-log-annotations"
test_log_error_in_ci_emits_annotation
test_log_warn_in_ci_emits_annotation
test_log_error_locally_keeps_colour
test_log_warn_locally_keeps_colour
test_multi_word_message_preserved
echo ""
log_pass "all tests passed"
