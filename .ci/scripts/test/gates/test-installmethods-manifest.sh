#!/bin/bash
# Tests for test_update_check() in .ci/scripts/test/test-install-methods.sh.
#
# WHY THIS EXISTS. The update-manifest check fetched the channel's
# manifest.json, PRINTED its version, and never compared it:
#
#   manifest_ver=$(echo "$manifest" | jq -r '.version')
#   log_info "  Manifest version: $manifest_ver"     # last mention
#
# $VERSION did not appear anywhere in the function, so a channel still
# advertising the previous release looked exactly like a correctly published
# one. Two more silent passes sat underneath it: the structural guard
# `jq -e '.version, .binaries'` accepts `"binaries": {}` because an empty object
# is TRUTHY in jq, and the reachability check read the URL with `// empty` and,
# finding none, skipped itself and returned 0 -- so a manifest naming no binary
# at all passed twice over.
#
# All three are now failures. Each is asserted against the CURRENT code and
# against a re-creation of the OLD code, because a negative case only means
# something if the previous implementation really did admit it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TARGET="$SCRIPT_DIR/../test-install-methods.sh"
[ -f "$TARGET" ] || log_fail "target not found: $TARGET"

# jq is not optional here. test_update_check returns 77 (skip) without it, so on
# a machine with no jq this file would run green having exercised nothing.
command -v jq >/dev/null 2>&1 || log_fail "jq is required: without it test_update_check skips itself and these tests would check nothing"

extract_fn() {
    local name="$1" body
    body="$(awk "/^${name}\\(\\) \\{/,/^\\}/" "$TARGET")"
    [ -n "$body" ] || log_fail "${name}() not found in $TARGET -- renamed or removed, so these tests would check nothing"
    printf '%s\n' "$body"
}

log_info() { :; }
log_warn() { :; }
log_error() { :; }

eval "$(extract_fn verify_version)"
eval "$(extract_fn test_update_check)"

DRY_RUN=false
REPO_URL="https://releases.example.invalid"
REPO_CHANNEL="edge"

FIXTURES="$(mktemp -d)"
FAKE_BIN="$(mktemp -d)"
cleanup() { rm -rf "$FIXTURES" "$FAKE_BIN"; }
trap cleanup EXIT

# A curl that serves $FAKE_MANIFEST for a GET and answers reachability probes
# with $FAKE_HEAD_RC. Nothing here touches the network.
cat >"$FAKE_BIN/curl" <<'FAKE'
#!/bin/bash
for a in "$@"; do
    [ "$a" = "--head" ] && exit "${FAKE_HEAD_RC:-0}"
done
[ -n "${FAKE_FETCH_FAILS:-}" ] && exit 22
cat "$FAKE_MANIFEST"
FAKE
chmod +x "$FAKE_BIN/curl"
export PATH="$FAKE_BIN:$PATH"
export FAKE_HEAD_RC=0

manifest() {
    FAKE_MANIFEST="$FIXTURES/m.json"
    printf '%s' "$1" >"$FAKE_MANIFEST"
    export FAKE_MANIFEST
}

GOOD='{"version":"1.2.17","binaries":{"linux-x64":{"url":"https://x.invalid/rdc-linux-x64","sha256":"deadbeef"}}}'
STALE='{"version":"1.2.16","binaries":{"linux-x64":{"url":"https://x.invalid/rdc-linux-x64","sha256":"deadbeef"}}}'
NO_BINARIES='{"version":"1.2.17","binaries":{}}'
OTHER_ARCH='{"version":"1.2.17","binaries":{"mac-arm64":{"url":"https://x.invalid/rdc-mac-arm64"}}}'
NO_VERSION='{"version":"","binaries":{"linux-x64":{"url":"https://x.invalid/rdc-linux-x64"}}}'

# Returns the function's exit code.
check() {
    manifest "$1"
    # ${2-...} not ${2:-...}: an explicitly EMPTY expected version is a case
    # under test, and :- would silently substitute the default for it.
    VERSION="${2-1.2.17}"
    local rc=0
    test_update_check >/dev/null 2>&1 || rc=$?
    echo "$rc"
}

# The implementation as it stood before this change, for the red proof.
old_update_check() {
    local manifest
    manifest=$(curl -fsSL "url") || return 1
    if ! echo "$manifest" | jq -e '.version, .binaries' >/dev/null 2>&1; then
        return 1
    fi
    local manifest_ver
    manifest_ver=$(echo "$manifest" | jq -r '.version')
    : "$manifest_ver" # printed, never compared
    local binary_url
    binary_url=$(echo "$manifest" | jq -r '.binaries["linux-x64"].url // empty')
    if [[ -n "$binary_url" ]]; then
        curl -fsSL -o /dev/null --head "$binary_url" 2>/dev/null || return 1
    fi
}

old_check() {
    manifest "$1"
    local rc=0
    old_update_check >/dev/null 2>&1 || rc=$?
    echo "$rc"
}

test_a_correct_manifest_passes() {
    assert_eq "0" "$(check "$GOOD" 1.2.17)" "a manifest matching the expected version must pass"
    log_pass "a correctly published manifest passes"
}

test_a_stale_manifest_version_fails() {
    # The core hole: the channel still advertising the previous release.
    assert_eq "1" "$(check "$STALE" 1.2.17)" "a manifest advertising 1.2.16 must FAIL a 1.2.17 run"
    assert_eq "0" "$(old_check "$STALE")" "the OLD code must accept it, or this test proves nothing"
    log_pass "the manifest version is compared, not merely printed"
}

test_an_empty_binaries_map_fails() {
    # `jq -e '.version, .binaries'` passes on {} because an empty object is
    # truthy, and the reachability check then skipped itself.
    assert_eq "1" "$(check "$NO_BINARIES" 1.2.17)" "a manifest with no binaries must FAIL"
    assert_eq "0" "$(old_check "$NO_BINARIES")" "the OLD code must accept an empty binaries map, or this test proves nothing"
    log_pass "a manifest that names no binary is a failure"
}

test_a_missing_linux_binary_fails() {
    assert_eq "1" "$(check "$OTHER_ARCH" 1.2.17)" "a manifest with no linux-x64 entry must FAIL"
    assert_eq "0" "$(old_check "$OTHER_ARCH")" "the OLD code must accept it via '// empty', or this test proves nothing"
    log_pass "an absent binary URL is a failure, not a skipped check"
}

test_an_empty_version_field_fails() {
    assert_eq "1" "$(check "$NO_VERSION" 1.2.17)" "an empty .version must FAIL"
    assert_eq "1" "$(check "$GOOD" "")" "an empty expected version must FAIL"
    log_pass "a version that could not be established fails"
}

test_an_unreachable_binary_still_fails() {
    # This one the old code did catch; assert it did not regress.
    FAKE_HEAD_RC=1
    assert_eq "1" "$(check "$GOOD" 1.2.17)" "an unreachable binary URL must FAIL"
    FAKE_HEAD_RC=0
    assert_eq "0" "$(check "$GOOD" 1.2.17)" "and must pass again once reachable"
    log_pass "reachability is still enforced"
}

test_a_failed_fetch_fails() {
    export FAKE_FETCH_FAILS=1
    assert_eq "1" "$(check "$GOOD" 1.2.17)" "a manifest that cannot be fetched must FAIL"
    unset FAKE_FETCH_FAILS
    log_pass "a fetch failure is a failure"
}

test_no_channel_skips_visibly() {
    # With no channel the URL would be .../cli//manifest.json, a path that names
    # nothing. 77 is the skip code run_test reports as SKIP; it must not be 0.
    manifest "$GOOD"
    VERSION="1.2.17"
    local rc=0
    REPO_CHANNEL="" test_update_check >/dev/null 2>&1 || rc=$?
    assert_eq "77" "$rc" "a channel-less run must SKIP, not pass and not fail"
    log_pass "a run with no staged channel skips instead of chasing a dead URL"
}

log_test "test-installmethods-manifest"
test_a_correct_manifest_passes
test_a_stale_manifest_version_fails
test_an_empty_binaries_map_fails
test_a_missing_linux_binary_fails
test_an_empty_version_field_fails
test_an_unreachable_binary_still_fails
test_a_failed_fetch_fails
test_no_channel_skips_visibly
echo ""
log_pass "all tests passed"
