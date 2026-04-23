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
source "$SCRIPT_DIR/lib/test-helpers.sh"

test_ci_mode_prefix() {
    local out
    out=$(CI=true bash -c "
        source '$SCRIPT_DIR/../lib/emit-advisory.sh'
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
        source '$SCRIPT_DIR/../lib/emit-advisory.sh'
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
        source '$SCRIPT_DIR/../lib/emit-advisory.sh'
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
        source '$SCRIPT_DIR/../lib/emit-advisory.sh'
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

log_test "test-emit-advisory"
test_ci_mode_prefix
test_non_ci_mode_glyph
test_full_metadata_renders_all_lines
test_emit_returns_zero_even_with_empty_hints
echo ""
log_pass "all tests passed"
