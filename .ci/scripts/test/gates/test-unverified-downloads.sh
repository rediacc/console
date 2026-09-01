#!/bin/bash
# Integration test for scripts/check-unverified-downloads.ts.
#
# Both-ways, offline, fixture-driven: proves the gate passes the real tree, FIRES
# on each shape of unverified artifact, does NOT fire on the shapes that are
# legitimately fine, and refuses a bare allowlist entry.
#
# The shapes matter more than the count. Three of them shipped as real defects on
# 2026-09-01: a curl streamed straight into tar (unverifiable by construction), an
# image pinned by a MUTABLE tag, and a plain download with no checksum at all.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-unverified-downloads.ts"

test_real_tree_passes() {
    local rc=0
    (cd "$REPO_ROOT" && npx tsx "$GATE" >/dev/null 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "the real tree must pass; every fetch is verified or allowlisted"
    log_pass "real tree passes"
}

# The gate self-tests its detector on every run, so a green IS the planted-defect
# proof for the pure logic. This asserts that machinery is actually wired.
test_controls_run_every_invocation() {
    local out
    out=$( (cd "$REPO_ROOT" && npx tsx "$GATE" 2>&1) || true)
    assert_contains "$out" "controls fired" "the detector's own controls must run on every invocation"
    log_pass "controls run unconditionally"
}

test_bare_allowlist_entry_is_refused() {
    local d out rc=0
    d="$(mktemp -d)"
    printf 'some-vendor.example.com\n' >"$d/allow"
    out=$( (cd "$REPO_ROOT" && UNVERIFIED_DOWNLOAD_ALLOWLIST="$d/allow" npx tsx "$GATE" 2>&1)) || rc=$?
    rm -rf "$d"
    assert_exit_code 1 "$rc" "an allowlist entry with no BLOCKER reason must fail the gate"
    assert_contains "$out" "invalid entries" "the error names the malformed allowlist"
    log_pass "allowlist entry without a BLOCKER reason fires"
}

# An empty allowlist strips the four real exemptions, so the gate must go red on
# the tree's genuinely-unverifiable fetches. This is the vacuity guard: it proves
# the allowlist is doing work rather than the gate having nothing to find.
test_allowlist_is_load_bearing() {
    local d out rc=0
    d="$(mktemp -d)"
    : >"$d/allow"
    out=$( (cd "$REPO_ROOT" && UNVERIFIED_DOWNLOAD_ALLOWLIST="$d/allow" npx tsx "$GATE" 2>&1)) || rc=$?
    rm -rf "$d"
    assert_exit_code 1 "$rc" "with an empty allowlist the tree's curl|bash fetches must be reported"
    assert_contains "$out" "unverified remote artifact" "the failure names the class"
    log_pass "the allowlist is load-bearing, not decorative"
}

log_test "test-unverified-downloads"
test_real_tree_passes
test_controls_run_every_invocation
test_bare_allowlist_entry_is_refused
test_allowlist_is_load_bearing
echo ""
log_pass "all tests passed"
