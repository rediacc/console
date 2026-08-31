#!/bin/bash
# Tests for verify_version() in .ci/scripts/test/test-install-methods.sh.
#
# WHY THIS EXISTS. On 2026-08-07 release run 31154305287 published CLI binaries
# built as 1.2.16 under the label 1.2.17. Two guards passed silently, and
# underneath both sat this one primitive, whose whole body was
#
#     echo "$output" | grep -q "$expected"
#
# which reports success in three situations where nothing was verified:
# an EMPTY expectation (grep -q "" matches any line), EMPTY output (a binary
# that did not run, or whose output was discarded by `|| true`), and a
# SUBSTRING match, so 1.2.1 "verified" against a binary reporting 1.2.16. The
# dots are regex wildcards on top of that.
#
# The rule being pinned: there is ALWAYS a version, or it fails. A caller that
# genuinely cannot determine one must SKIP visibly, never hand an empty string
# to this and take the pass.
#
# Both directions are asserted throughout: a checker that always fails would
# satisfy every negative case, one that always passes would satisfy every
# positive one, and neither would be a check.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TARGET="$SCRIPT_DIR/../test-install-methods.sh"
[ -f "$TARGET" ] || log_fail "target not found: $TARGET"

# Extract the function rather than sourcing the whole script, which would run
# its argument parsing. If the extraction ever comes back empty the function
# was renamed or removed, and this file must refuse rather than pass over
# nothing.
FN="$(awk '/^verify_version\(\) \{/,/^\}/' "$TARGET")"
[ -n "$FN" ] || log_fail "verify_version() not found in $TARGET -- renamed or removed, so these tests would check nothing"

log_error() { :; } # the function under test calls it; keep the output clean
eval "$FN"

# Returns 0 when verify_version accepted, 1 when it refused.
vv() {
    verify_version "$1" "$2" >/dev/null 2>&1 && echo 0 || echo 1
}

test_real_versions_are_accepted() {
    assert_eq "0" "$(vv 'rdc 1.2.17' '1.2.17')" "an exact match must pass"
    assert_eq "0" "$(vv 'v1.2.17' '1.2.17')" "a v-prefixed output must pass"
    assert_eq "0" "$(vv 'rdc 1.2.17' 'v1.2.17')" "a v-prefixed expectation must pass"
    assert_eq "0" "$(vv 'rediacc rdc 1.2.17 (linux)' '1.2.17')" "the version may sit inside a longer line"
    log_pass "well-formed versions are accepted"
}

test_missing_version_never_passes() {
    # The founding defect class: nothing was established, yet grep said yes.
    assert_eq "1" "$(vv 'rdc 1.2.17' '')" "an EMPTY expectation must never pass"
    assert_eq "1" "$(vv '' '1.2.17')" "EMPTY output must never pass"
    assert_eq "1" "$(vv '' '')" "both empty must never pass"
    log_pass "a version that could not be established fails instead of passing"
}

test_substring_matches_are_refused() {
    # This is how a patch release would "verify" against the wrong build.
    assert_eq "1" "$(vv 'rdc 1.2.16' '1.2.1')" "1.2.1 must NOT match 1.2.16"
    assert_eq "1" "$(vv 'rdc 11.2.1' '1.2.1')" "1.2.1 must NOT match 11.2.1"
    assert_eq "1" "$(vv 'rdc 1x2y17' '1.2.17')" "dots must not behave as regex wildcards"
    assert_eq "1" "$(vv 'rdc 1.2.16' '1.2.17')" "a genuinely wrong version must fail"
    log_pass "substring and regex matches are refused"
}

test_latest_still_requires_a_real_version() {
    assert_eq "0" "$(vv '1.2.17' 'latest')" "latest accepts a well-formed semver"
    assert_eq "0" "$(vv '1.2.17-rc.1' 'latest')" "latest accepts a prerelease"
    assert_eq "1" "$(vv 'command not found' 'latest')" "latest must reject garbage"
    assert_eq "1" "$(vv '' 'latest')" "latest must reject empty output"
    log_pass "latest means any REAL version, not any output"
}

test_the_founding_defect_fires() {
    # The exact old body, re-created, must fail the cases above. If it passed
    # them, these tests would be decorative and would have let the incident
    # through unchanged.
    old_verify() {
        local output="$1" expected="$2"
        if [[ "$expected" == "latest" ]]; then
            [[ -n "$output" ]] && grep -qE '^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$' <<<"$output"
        else
            grep -q "$expected" <<<"$output"
        fi
    }
    local empty_expectation substring
    old_verify 'rdc 1.2.17' '' >/dev/null 2>&1 && empty_expectation=0 || empty_expectation=1
    old_verify 'rdc 1.2.16' '1.2.1' >/dev/null 2>&1 && substring=0 || substring=1
    assert_eq "0" "$empty_expectation" "the OLD body must accept an empty expectation, or this test proves nothing"
    assert_eq "0" "$substring" "the OLD body must accept 1.2.1 against 1.2.16, or this test proves nothing"
    log_pass "the old implementation really did admit both silent-pass classes"
}

log_test "test-verify-version"
test_real_versions_are_accepted
test_missing_version_never_passes
test_substring_matches_are_refused
test_latest_still_requires_a_real_version
test_the_founding_defect_fires
echo ""
log_pass "all tests passed"
