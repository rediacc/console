#!/bin/bash
# Unit tests for .ci/scripts/lib/emit-advisory.sh.
#
# Exercises the shape of the annotations:
#   - CI mode emits ::error:: / ::warning:: prefix
#   - Non-CI mode emits coloured ANSI with ✗ / ⚠ glyphs
#   - Continuation lines fire only for supplied hints

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

test_ci_mode_prefix() {
    local out
    out=$(CI=true bash -c "
        source '$SCRIPT_DIR/../../lib/emit-advisory.sh'
        declare -A ADV_SEVERITY=() ADV_TITLE=() ADV_GHSA=() ADV_URL=()
        declare -A ADV_VULN_RANGE=() ADV_PATCHED_VERSION=() ADV_DESC_PREVIEW=()
        emit_advisory error 'testid' 'testpkg' 'test fix hint'
    " 2>&1)
    assert_contains "$out" "::error::testid (testpkg)" "CI error has annotation prefix"
    assert_contains "$out" "  Fix: test fix hint" "fix hint renders"
    log_pass "CI mode emits annotation prefix + continuation"
}

test_non_ci_mode_glyph() {
    local out
    out=$(env -u CI bash -c "
        source '$SCRIPT_DIR/../../lib/emit-advisory.sh'
        declare -A ADV_SEVERITY=() ADV_TITLE=() ADV_GHSA=() ADV_URL=()
        declare -A ADV_VULN_RANGE=() ADV_PATCHED_VERSION=() ADV_DESC_PREVIEW=()
        emit_advisory warn 'testid' 'testpkg' 'test fix hint'
    " 2>&1)
    assert_contains "$out" "⚠" "non-CI warn has ⚠ glyph"
    assert_contains "$out" "testid (testpkg)" "header present"
    log_pass "non-CI mode uses glyphs"
}

test_full_metadata_renders_all_lines() {
    local out
    out=$(CI=true bash -c "
        source '$SCRIPT_DIR/../../lib/emit-advisory.sh'
        declare -A ADV_SEVERITY=(['id1']='critical')
        declare -A ADV_TITLE=(['id1']='Test title')
        declare -A ADV_GHSA=(['id1']='GHSA-xxxx-yyyy-zzzz')
        declare -A ADV_URL=(['id1']='https://github.com/advisories/GHSA-xxxx-yyyy-zzzz')
        declare -A ADV_VULN_RANGE=(['id1']='<= 1.0.0')
        declare -A ADV_PATCHED_VERSION=(['id1']='1.0.1')
        declare -A ADV_DESC_PREVIEW=(['id1']='Detailed CVE description preview')
        emit_advisory error 'id1' 'pkgname' 'fix: upgrade' 'action: take the fix'
    " 2>&1)
    assert_contains "$out" "critical" "severity shown"
    assert_contains "$out" "GHSA-xxxx-yyyy-zzzz" "GHSA shown"
    assert_contains "$out" "Test title" "title shown"
    assert_contains "$out" "Affected: <= 1.0.0" "affected range shown"
    assert_contains "$out" "Patched in: 1.0.1" "patched version shown"
    assert_contains "$out" "Summary: Detailed CVE" "summary shown"
    assert_contains "$out" "Fix: fix: upgrade" "fix hint shown"
    assert_contains "$out" "Action: action:" "action hint shown"
    assert_contains "$out" "Details: https://github.com/advisories" "url shown"
    log_pass "full metadata renders all lines"
}

test_emit_returns_zero_even_with_empty_hints() {
    # Regression test for the set -e gotcha — emit_advisory must return 0
    # so callers using set -euo pipefail don't exit on the trailing conditional.
    local out rc
    out=$(CI=true bash -c "
        set -euo pipefail
        source '$SCRIPT_DIR/../../lib/emit-advisory.sh'
        declare -A ADV_SEVERITY=() ADV_TITLE=() ADV_GHSA=() ADV_URL=()
        declare -A ADV_VULN_RANGE=() ADV_PATCHED_VERSION=() ADV_DESC_PREVIEW=()
        emit_advisory warn 'testid' 'testpkg' ''
        echo 'after-emit'
    " 2>&1)
    rc=$?
    assert_exit_code 0 "$rc" "emit_advisory does not fail caller under set -e"
    assert_contains "$out" "after-emit" "execution continues past emit_advisory"
    log_pass "emit_advisory returns 0 (set -e safe)"
}

# ---------------------------------------------------------------------------
# Stream and argument regressions (found 2026-09-06).
#
# emit-advisory.sh used to assign RED/GREEN/YELLOW/NC and define
# log_error / log_success / log_warn / log_info UNCONDITIONALLY. Four gates
# (check-profiler-coverage.sh, check-swallowed-failures.sh,
# check-ci-job-aggregation.sh, check-go-deps.sh) source common.sh first and
# then reach this library transitively through blocker-validator.sh:26, so the
# later definitions won and silently replaced common.sh's TTY-gated logger.
# Two symptoms, neither of which the older cases above could see:
#   - log_info / log_warn / log_success moved from stderr to stdout, so a gate
#     that a caller pipes for data got colour escapes mixed into that pipe
#   - log_error interpolated "$1", so `log_error a b` printed only "a"
#
# The cases below capture stdout and stderr into SEPARATE files on purpose.
# The defect is a stream swap; the `2>&1` used by every case above merges the
# two streams back together and would hide it completely.
#
# Sibling note: check-pool-writer-safety.sh sources only common.sh and never
# reaches blocker-validator.sh, which is why it was never affected. If it ever
# grows a blocker-validator source, these cases are what keep it honest.
# ---------------------------------------------------------------------------

# Exit status of the last _run_split_streams child. Kept in a global rather
# than returned, because the caller runs under `set -e` and a non-zero return
# would abort the test before it could report a useful diagnostic.
SPLIT_RC=0

# _run_split_streams <tmp> <script>
#
# Runs <script> in a child bash with stdout in <tmp>/out and stderr in
# <tmp>/err. `env -u CI` puts emit-advisory.sh in its colours-on branch, and
# neither stream is a tty, which is exactly the condition common.sh gates its
# own colours on -- so the two libraries disagree here if the fix regresses.
_run_split_streams() {
    local tmp="$1" script="$2"
    SPLIT_RC=0
    env -u CI bash -c "$script" >"$tmp/out" 2>"$tmp/err" || SPLIT_RC=$?
}

test_production_order_keeps_common_logger() {
    with_temp_dir _production_order_body
}

_production_order_body() {
    local tmp="$1"
    # The production source order of the four affected gates, verbatim.
    _run_split_streams "$tmp" "
        source '$SCRIPT_DIR/../../lib/common.sh'
        source '$SCRIPT_DIR/../../lib/blocker-validator.sh'
        log_info x
        log_warn y
        log_error a b
    "
    assert_exit_code 0 "$SPLIT_RC" "production-order logging exits clean"
    assert_eq "$(cat "$tmp/out")" "" "stdout stays empty while a gate logs"
    local err
    err="$(cat "$tmp/err")"
    assert_contains "$err" "x" "log_info reaches stderr, not stdout"
    assert_contains "$err" "y" "log_warn reaches stderr, not stdout"
    assert_contains "$err" "a" "log_error reaches stderr"
    assert_contains "$err" "b" "log_error keeps arguments past the first"
    log_pass "common.sh logger survives blocker-validator's transitive source"
}

test_no_escape_bytes_on_stdout_off_tty() {
    with_temp_dir _no_escape_stdout_body
}

_no_escape_stdout_body() {
    local tmp="$1"
    # log_success is the interesting one: common.sh does not define it, so it
    # legitimately comes from this library even in production order. It must
    # still honour the RED/GREEN/... that common.sh already emptied.
    _run_split_streams "$tmp" "
        source '$SCRIPT_DIR/../../lib/common.sh'
        source '$SCRIPT_DIR/../../lib/blocker-validator.sh'
        log_info x
        log_warn y
        log_success z
        log_error a b
    "
    assert_exit_code 0 "$SPLIT_RC" "off-tty logging exits clean"
    local esc
    esc="$(tr -cd '\033' <"$tmp/out" | wc -c | tr -d ' ')"
    assert_eq "$esc" "0" "zero ESC bytes on stdout when stderr is not a tty"
    log_pass "off a tty, stdout carries no colour escapes"
}

test_standalone_source_still_defines_logger() {
    with_temp_dir _standalone_body
}

_standalone_body() {
    local tmp="$1"
    # The standalone contract: a script that sources ONLY this library still
    # gets all four helpers, with log_error on stderr and the rest on stdout.
    # Making the definitions conditional must not quietly define nothing.
    _run_split_streams "$tmp" "
        source '$SCRIPT_DIR/../../lib/emit-advisory.sh'
        declare -F log_error log_success log_warn log_info >/dev/null || exit 3
        log_info x
        log_success z
        log_warn y
        log_error a b
    "
    assert_exit_code 0 "$SPLIT_RC" "standalone source defines all four log_* helpers"
    local out err
    out="$(cat "$tmp/out")"
    err="$(cat "$tmp/err")"
    assert_contains "$out" "x" "standalone log_info still writes to stdout"
    assert_contains "$out" "z" "standalone log_success still writes to stdout"
    assert_contains "$out" "y" "standalone log_warn still writes to stdout"
    assert_contains "$err" "a" "standalone log_error still writes to stderr"
    assert_contains "$err" "b" "standalone log_error keeps its argument tail"
    assert_not_contains "$out" "✗" "standalone log_error does not leak onto stdout"
    log_pass "emit-advisory alone keeps its standalone logger contract"
}

log_test "test-emit-advisory"
test_ci_mode_prefix
test_non_ci_mode_glyph
test_full_metadata_renders_all_lines
test_emit_returns_zero_even_with_empty_hints
test_production_order_keeps_common_logger
test_no_escape_bytes_on_stdout_off_tty
test_standalone_source_still_defines_logger
echo ""
log_pass "all tests passed"
