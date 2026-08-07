#!/bin/bash
# Tests for the version assertions in .ci/scripts/test/test-linux-packages.sh.
#
# WHY THIS EXISTS. That file carried the same unanchored-grep idiom that let a
# 1.2.16 binary verify as 1.2.17 in the release path, in two shapes:
#
#   ${PKG_BINARY_NAME} --version 2>/dev/null | grep -q '${TEST_VERSION}'
#   echo "$info" | grep -q "Version: ${TEST_VERSION}"
#
# SEVERITY IS LOW and deliberately recorded as such: TEST_VERSION is hardcoded
# to 99.0.0 and the binary under test is a dummy shell script the same file
# writes, so no real version could drift out from under those checks. The point
# of the change, and of this file, is to stop the idiom being COPIED somewhere a
# real version is at stake -- and to keep it from creeping back in.
#
# The name carries the test-installmethods- prefix because that is the prefix
# this batch of gate tests was added under; the target is test-linux-packages.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TARGET="$SCRIPT_DIR/../test-linux-packages.sh"
[ -f "$TARGET" ] || log_fail "target not found: $TARGET"

extract_fn() {
    local name="$1" body
    body="$(awk "/^${name}\\(\\) \\{/,/^\\}/" "$TARGET")"
    [ -n "$body" ] || log_fail "${name}() not found in $TARGET -- renamed or removed, so these tests would check nothing"
    printf '%s\n' "$body"
}

log_error() { :; }

TEST_VERSION="$(grep -E '^TEST_VERSION=' "$TARGET" | head -1 | cut -d'"' -f2)"
[ -n "$TEST_VERSION" ] || log_fail "TEST_VERSION not found in $TARGET"

eval "$(extract_fn version_token_re)"
eval "$(extract_fn assert_version_field)"
TEST_VERSION_RE="$(version_token_re "$TEST_VERSION")"

# dpkg-deb --info and rpm -qip lay the same field out differently; both shapes
# are what the two callers actually feed in.
deb_info() { printf ' Package: rediacc-cli\n Version: %s\n Architecture: amd64\n Maintainer: x\n' "$1"; }
rpm_info() { printf 'Name        : rediacc-cli\nVersion     : %s\nArchitecture: x86_64\n' "$1"; }

field() {
    assert_version_field "$1" "Version" >/dev/null 2>&1 && echo 0 || echo 1
}

token() {
    printf '%s\n' "$1" | grep -qE "$TEST_VERSION_RE" && echo 0 || echo 1
}

test_the_right_version_is_accepted_in_both_layouts() {
    assert_eq "0" "$(field "$(deb_info "$TEST_VERSION")")" "the deb layout with the right version must pass"
    assert_eq "0" "$(field "$(rpm_info "$TEST_VERSION")")" "the rpm layout with the right version must pass"
    log_pass "both metadata layouts still validate a correct version"
}

test_a_longer_version_no_longer_satisfies_the_field_check() {
    local longer="${TEST_VERSION}1"
    assert_eq "1" "$(field "$(deb_info "$longer")")" "'$longer' must NOT satisfy a '$TEST_VERSION' check"
    assert_eq "1" "$(field "$(rpm_info "$longer")")" "'$longer' must NOT satisfy a '$TEST_VERSION' check"

    # The control. Both old idioms accept it, which is what made them worth
    # replacing even at low severity.
    local old_deb old_rpm
    deb_info "$longer" | grep -q "Version: ${TEST_VERSION}" && old_deb=0 || old_deb=1
    rpm_info "$longer" | grep -q "Version.*: ${TEST_VERSION}" && old_rpm=0 || old_rpm=1
    assert_eq "0" "$old_deb" "the OLD deb idiom must accept it, or this test proves nothing"
    assert_eq "0" "$old_rpm" "the OLD rpm idiom must accept it, or this test proves nothing"
    log_pass "a substring version is refused where it used to pass"
}

test_a_missing_or_wrong_field_fails() {
    assert_eq "1" "$(field "$(printf ' Package: rediacc-cli\n Architecture: amd64\n')")" "a missing Version field must FAIL"
    assert_eq "1" "$(field "$(deb_info '1.0.0')")" "a plainly wrong version must FAIL"
    assert_eq "1" "$(field "$(deb_info '')")" "an empty version value must FAIL"
    log_pass "an absent or wrong version field is a failure"
}

test_the_token_regex_matches_whole_versions_only() {
    assert_eq "0" "$(token "rdc version $TEST_VERSION")" "the version inside a longer line must match"
    assert_eq "0" "$(token "v$TEST_VERSION")" "a v-prefixed output must match"
    assert_eq "1" "$(token "rdc version ${TEST_VERSION}1")" "a longer version must NOT match"
    assert_eq "1" "$(token "rdc version 1${TEST_VERSION}")" "a longer prefix must NOT match"
    assert_eq "1" "$(token "")" "empty output must NOT match"

    # Control: the old container idiom accepts the first two negatives.
    local old
    printf 'rdc version %s1\n' "$TEST_VERSION" | grep -q "$TEST_VERSION" && old=0 || old=1
    assert_eq "0" "$old" "the OLD container idiom must accept a longer version, or this test proves nothing"
    log_pass "the exact-token regex refuses what the old grep accepted"
}

test_the_old_idiom_is_gone_from_the_target() {
    # Structural, so the idiom cannot quietly come back.
    #
    # Comment lines are stripped first: the header of the target QUOTES both old
    # idioms verbatim to explain what was wrong with them, and a naive whole-file
    # search matches that documentation and fails on it. (It did, on the first
    # run of this test.)
    local code
    code="$(grep -vE '^[[:space:]]*#' "$TARGET")"

    count() { printf '%s\n' "$code" | grep -cF "$1" || true; }

    assert_eq "0" "$(count 'grep -q '"'"'${TEST_VERSION}'"'"'')" "the unanchored container grep must be gone from the code"
    assert_eq "0" "$(count 'grep -q "Version: ${TEST_VERSION}"')" "the unanchored deb grep must be gone from the code"
    assert_eq "0" "$(count 'grep -q "Version.*: ${TEST_VERSION}"')" "the unanchored rpm grep must be gone from the code"

    # Discrimination: count() must be able to find something, or the three zeros
    # above would be satisfied by a broken matcher.
    assert_eq "2" "$(count 'assert_version_field "$info" "Version"')" "both metadata validators must use assert_version_field"

    # And all four container checks use the exact-match regex. Counted, not
    # merely present: three of four converted would otherwise look identical.
    assert_eq "4" "$(count 'grep -qE '"'"'${TEST_VERSION_RE}'"'"'')" "all four container install checks must use the exact-token regex"
    log_pass "the target carries one exact-match spelling and no copies of the old one"
}

log_test "test-installmethods-linuxpkg-idiom"
test_the_right_version_is_accepted_in_both_layouts
test_a_longer_version_no_longer_satisfies_the_field_check
test_a_missing_or_wrong_field_fails
test_the_token_regex_matches_whole_versions_only
test_the_old_idiom_is_gone_from_the_target
echo ""
log_pass "all tests passed"
