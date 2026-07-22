#!/bin/bash
# Both-ways test for scripts/check-embed-arch-parity.ts.
#
# The gate exists because arm64 criu silently became a different version from
# amd64 criu and every existing gate stayed green: nothing carried an
# architecture dimension, so a per-arch divergence was structurally invisible.
# A gate for that class is worthless unless it demonstrably FIRES, so every
# defect class below is planted into a fixture lockfile and asserted to fail,
# and the real lockfile is asserted to pass.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REAL_LOCKFILE="$REPO_ROOT/private/renet/embed-assets.lock.json"

# Run the gate against a lockfile produced by applying a jq filter to the real one.
run_with_filter() {
    local filter="$1"
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: capture TEMP at trap-set time so RETURN removes this exact dir
    trap "rm -rf '$TEMP'" RETURN
    jq "$filter" "$REAL_LOCKFILE" >"$TEMP/lock.json"
    local out rc=0
    out=$(cd "$REPO_ROOT" && EMBED_PARITY_LOCKFILE="$TEMP/lock.json" \
        npx tsx scripts/check-embed-arch-parity.ts 2>&1) || rc=$?
    echo "$out"
    return "$rc"
}

test_accepts_real_lockfile() {
    if [[ ! -f "$REAL_LOCKFILE" ]]; then
        log_pass "renet submodule absent — skipping (gate is a no-op without it)"
        return
    fi
    local out rc=0
    out=$(cd "$REPO_ROOT" && npx tsx scripts/check-embed-arch-parity.ts 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "the real lockfile should pass arch parity"
    assert_contains "$out" "arch entries" "success output reports what it checked"
    log_pass "real lockfile passes arch parity"
}

test_rejects_missing_arch() {
    local out rc=0
    out=$(run_with_filter '.components.criu.arches |= del(.arm64)') || rc=$?
    assert_exit_code 1 "$rc" "a component missing an arch should fail"
    assert_contains "$out" "architectures" "error names the arch mismatch"
    log_pass "a component that loses an architecture is rejected"
}

test_rejects_malformed_digest() {
    local out rc=0
    out=$(run_with_filter '.components.k3s.arches.amd64.sha256 = "not-a-digest"') || rc=$?
    assert_exit_code 1 "$rc" "a malformed download digest should fail"
    assert_contains "$out" "sha256" "error names the digest"
    log_pass "a malformed download digest is rejected"
}

test_rejects_unpinned_source() {
    local out rc=0
    out=$(run_with_filter 'del(.components.criu.source.commit)') || rc=$?
    assert_exit_code 1 "$rc" "a source build without a commit pin should fail"
    assert_contains "$out" "commit" "error names the missing pin"
    log_pass "a source build with no immutable pin is rejected"
}

test_rejects_bad_class() {
    local out rc=0
    out=$(run_with_filter '.components.zot.class = "bogus"') || rc=$?
    assert_exit_code 1 "$rc" "an invalid class should fail"
    assert_contains "$out" "base|cluster" "error names the valid classes"
    log_pass "an invalid asset class is rejected"
}

test_rejects_empty_lockfile() {
    # Anti-vacuity: a lockfile with nothing in it must never report parity.
    local out rc=0
    out=$(run_with_filter '.components = {}') || rc=$?
    assert_exit_code 1 "$rc" "an empty lockfile should fail, not vacuously pass"
    assert_contains "$out" "blind" "error says the gate would be blind"
    log_pass "an empty lockfile is rejected rather than vacuously passing"
}

log_test "test-embed-arch-parity"
test_accepts_real_lockfile
test_rejects_missing_arch
test_rejects_malformed_digest
test_rejects_unpinned_source
test_rejects_bad_class
test_rejects_empty_lockfile
echo ""
log_pass "all tests passed"
