#!/bin/bash
# Integration test for private/renet/.ci/scripts/quality/deadcode.sh.
#
# Sources the script (main is guarded) and exercises evaluate_deadcode with
# fixture dead-lists + allowlists: violations fail, BLOCKER quality is
# enforced, and the stale-entry guard rejects allowlisted-but-not-dead names.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

DEADCODE_SH="$REPO_ROOT/private/renet/.ci/scripts/quality/deadcode.sh"

if [[ ! -f "$DEADCODE_SH" ]]; then
    echo "renet submodule not present -- skipping renet deadcode gate test"
    exit 0
fi

# Sourcing skips main (BASH_SOURCE guard) but pulls in evaluate_deadcode,
# validate_blocker_reason, and renet's common.sh logging helpers.
# shellcheck source=/dev/null
source "$DEADCODE_SH"

FIXTURES="$(mktemp -d)"
trap 'rm -rf "$FIXTURES"' EXIT

FUNC_A="github.com/rediacc/renet/pkg/example.DeadFunc"
FUNC_B="github.com/rediacc/renet/pkg/example.Type.DeadMethod"

make_dead_tsv() {
    local file="$FIXTURES/dead.tsv"
    : >"$file"
    local name
    for name in "$@"; do
        printf '%s\tpkg/example/file.go:42\n' "$name" >>"$file"
    done
    echo "$file"
}

test_passes_when_all_dead_allowlisted() {
    local dead allow rc=0 out
    dead="$(make_dead_tsv "$FUNC_A")"
    allow="$FIXTURES/allow-good"
    cat >"$allow" <<EOF
# BLOCKER: reachable only under GOOS=darwin syscall fallback; deleting breaks the cross-platform build
$FUNC_A
EOF
    out=$(evaluate_deadcode "$dead" "$allow" 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "allowlisted dead function should pass"
    log_pass "allowlisted dead function passes"
}

test_fails_on_unlisted_dead_function() {
    local dead rc=0 out
    dead="$(make_dead_tsv "$FUNC_A" "$FUNC_B")"
    out=$(evaluate_deadcode "$dead" "$FIXTURES/nonexistent-allowlist" 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "unlisted dead functions should fail"
    assert_contains "$out" "unreachable function" "error names the problem"
    assert_contains "$out" "$FUNC_B" "error lists the offending function"
    log_pass "unlisted dead function is rejected"
}

test_fails_on_missing_blocker() {
    local dead allow rc=0 out
    dead="$(make_dead_tsv "$FUNC_A")"
    allow="$FIXTURES/allow-nobloc"
    printf '%s\n' "$FUNC_A" >"$allow"
    out=$(evaluate_deadcode "$dead" "$allow" 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "entry without BLOCKER should fail"
    assert_contains "$out" "BLOCKER" "error mentions the BLOCKER requirement"
    log_pass "missing BLOCKER is rejected"
}

test_fails_on_low_effort_blocker() {
    local dead allow rc=0 out
    dead="$(make_dead_tsv "$FUNC_A")"
    allow="$FIXTURES/allow-loweffort"
    cat >"$allow" <<EOF
# BLOCKER: tbd
$FUNC_A
EOF
    out=$(evaluate_deadcode "$dead" "$allow" 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "low-effort BLOCKER should fail"
    assert_contains "$out" "too short" "short low-effort reason is called out"
    log_pass "low-effort BLOCKER is rejected"
}

test_fails_on_low_effort_phrase_at_length() {
    # A banned phrase padded to >=30 chars must still fail the exact-match
    # check when it is exactly a banned phrase; a >=30-char phrase like
    # "no fix available" is shorter than 30, so use validate directly.
    local rc=0
    validate_blocker_reason "x" "no fix available" >/dev/null 2>&1 || rc=$?
    assert_exit_code 1 "$rc" "banned phrase should fail validation"
    log_pass "banned phrase is rejected by validator"
}

test_fails_on_stale_entry() {
    local dead allow rc=0 out
    dead="$(make_dead_tsv "$FUNC_A")"
    allow="$FIXTURES/allow-stale"
    cat >"$allow" <<EOF
# BLOCKER: reachable only under GOOS=darwin syscall fallback; deleting breaks the cross-platform build
$FUNC_A

# BLOCKER: kept alive only by the btrfs-tagged privileged test suite in pkg/example
$FUNC_B
EOF
    out=$(evaluate_deadcode "$dead" "$allow" 2>&1) || rc=$?
    assert_exit_code 1 "$rc" "stale allowlist entry should fail"
    assert_contains "$out" "Stale allowlist entry" "error names the stale entry guard"
    assert_contains "$out" "$FUNC_B" "error identifies the stale name"
    log_pass "stale allowlist entry is rejected"
}

test_passes_on_empty_dead_list() {
    local dead rc=0
    dead="$(make_dead_tsv)"
    evaluate_deadcode "$dead" "$FIXTURES/nonexistent-allowlist" >/dev/null 2>&1 || rc=$?
    assert_exit_code 0 "$rc" "empty dead list with no allowlist should pass"
    log_pass "empty dead list passes"
}

log_test "test-renet-deadcode"
test_passes_when_all_dead_allowlisted
test_fails_on_unlisted_dead_function
test_fails_on_missing_blocker
test_fails_on_low_effort_blocker
test_fails_on_low_effort_phrase_at_length
test_fails_on_stale_entry
test_passes_on_empty_dead_list
echo ""
log_pass "all tests passed"
