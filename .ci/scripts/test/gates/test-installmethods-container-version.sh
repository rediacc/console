#!/bin/bash
# Tests for the container version fence in .ci/scripts/test/test-install-methods.sh.
#
# WHY THIS EXISTS. On 2026-08-07 a release published CLI binaries built as
# 1.2.16 under the label 1.2.17. verify_version() was one hole (pinned by
# test-verify-version.sh). The other, larger one: SEVEN of the eleven install
# methods -- apt, dnf, apk, pacman, npm, linuxbrew, quick -- never compared a
# version at all. Each ended its `docker run ... set -e` heredoc with a bare
#
#     ${PKG_BINARY_NAME} --version
#
# whose output was never captured and never compared. $VERSION was referenced
# ZERO times inside any of those functions, so the only assertion was "the
# installed binary exits 0" -- which a mislabelled binary does. Both ci.yml and
# ct-install-methods.yml were passing `--version <next_version>` into every one
# of them, so the steps read like version checks in the workflow and were not.
#
# The fix moves the comparison HOST-side, through verify_version, and fences the
# container's version output between markers so the transcript's own mentions of
# the version (apt-get, npm and brew all print it while installing) cannot
# satisfy the check. Both properties are asserted here, in both directions:
# a checker that always failed would satisfy every negative case, one that always
# passed would satisfy every positive one, and neither would be a check.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TARGET="$SCRIPT_DIR/../test-install-methods.sh"
[ -f "$TARGET" ] || log_fail "target not found: $TARGET"

# Lift the real implementations out of the script rather than sourcing it, which
# would run its argument parsing. Every extraction is checked for emptiness: a
# renamed or deleted function must make this file REFUSE, not quietly test
# nothing.
extract_fn() {
    local name="$1" body
    body="$(awk "/^${name}\\(\\) \\{/,/^\\}/" "$TARGET")"
    [ -n "$body" ] || log_fail "${name}() not found in $TARGET -- renamed or removed, so these tests would check nothing"
    printf '%s\n' "$body"
}

FENCE_VARS="$(grep -E '^VERSION_FENCE_(BEGIN|END)=' "$TARGET")"
[ -n "$FENCE_VARS" ] || log_fail "VERSION_FENCE_BEGIN/END not found in $TARGET"

log_info() { :; } # the functions under test call these; keep the output clean
log_warn() { :; }
log_error() { :; }

eval "$FENCE_VARS"
eval "$(extract_fn verify_version)"
eval "$(extract_fn version_fence_probe)"
eval "$(extract_fn extract_fenced_version)"
eval "$(extract_fn run_container_version_test)"

# A stand-in for `docker run`: runs the REAL fenced probe the install functions
# paste into their container scripts, so the probe itself is under test and not
# just the host-side comparison. $1 is what the "installed binary" prints, $2 is
# surrounding install-transcript noise.
fake_container() {
    local reported="$1" noise="${2:-}"
    bash -c "
        set -e
        printf '%s\n' \"\$1\"
        $(version_fence_probe "printf '%s\n' \"\$2\"")
    " _ "$noise" "$reported"
}

fake_container_fails() {
    printf 'apt-get: package not found\n' >&2
    return 3
}

# 0 when the check accepted, 1 when it refused.
check() {
    local expected="$1" reported="$2" noise="${3:-}"
    VERSION="$expected"
    run_container_version_test "T" fake_container "$reported" "$noise" >/dev/null 2>&1 && echo 0 || echo 1
}

test_correct_version_is_accepted() {
    assert_eq "0" "$(check '1.2.17' '1.2.17')" "an exactly matching version must pass"
    assert_eq "0" "$(check '1.2.17' 'rdc 1.2.17')" "the version may sit inside a longer line"
    assert_eq "0" "$(check '1.2.17' '1.2.17' 'Setting up rediacc-cli (1.2.17) ...')" "install noise must not break a correct run"
    log_pass "a container reporting the expected version passes"
}

test_the_incident_is_caught() {
    # The exact 2026-08-07 shape: a 1.2.16 binary installed under the 1.2.17
    # label, exiting 0 the whole way. This is what the seven methods could not
    # see.
    assert_eq "1" "$(check '1.2.17' '1.2.16')" "a 1.2.16 binary must FAIL a 1.2.17 run"
    assert_eq "1" "$(check '1.2.1' '1.2.16')" "1.2.1 must not be satisfied by 1.2.16"
    log_pass "the mislabelled-binary case now fails"
}

test_nothing_reported_is_never_a_pass() {
    assert_eq "1" "$(check '1.2.17' '')" "a binary that printed no version must FAIL"
    assert_eq "1" "$(check '' '1.2.17')" "an empty expected version must FAIL"
    log_pass "an unestablished version fails instead of passing"
}

test_transcript_noise_cannot_satisfy_the_check() {
    # The reason the comparison is fenced. apt-get, npm and brew all print the
    # version they are installing; if the host matched against the whole
    # transcript, that line alone would satisfy the check even when the binary
    # reported something else entirely.
    local noise='Setting up rediacc-cli (1.2.17) ...'
    assert_eq "1" "$(check '1.2.17' '1.2.16' "$noise")" "the installer's own version line must NOT satisfy the check"

    # And the control: an unfenced whole-transcript grep -- what a naive fix
    # would have done -- DOES accept it. Without this, the fence would be
    # decorative and nobody would know.
    local raw naive
    raw="$(fake_container '1.2.16' "$noise" 2>&1)"
    echo "$raw" | grep -q '1\.2\.17' && naive=0 || naive=1
    assert_eq "0" "$naive" "an unfenced grep must accept the wrong binary, or this test proves nothing"
    log_pass "fencing is what stops the installer's own output from passing the check"
}

test_a_failing_container_fails_the_test() {
    VERSION="1.2.17"
    local rc=0
    run_container_version_test "T" fake_container_fails >/dev/null 2>&1 || rc=1
    assert_eq "1" "$rc" "a container that exits non-zero must fail"
    log_pass "a failed install is a failure, not a missing version"
}

test_fence_extraction_takes_only_the_fenced_region() {
    local raw
    raw="$(fake_container '1.2.16' 'noise before 1.2.17')"
    assert_eq "1.2.16" "$(extract_fenced_version "$raw")" "only the fenced region is extracted"
    assert_eq "" "$(extract_fenced_version 'no markers here at all')" "an unfenced transcript yields nothing, which verify_version refuses"
    log_pass "extraction returns the binary's own output and nothing else"
}

test_every_container_method_routes_through_the_fence() {
    # Structural, so a future edit that reverts one method to a bare
    # `${PKG_BINARY_NAME} --version` is caught here rather than in a release.
    local fn body
    for fn in test_apt_install test_dnf_install test_apk_install test_pacman_install \
        test_npm_install test_homebrew_linuxbrew test_quick_install; do
        body="$(extract_fn "$fn")"
        assert_contains "$body" "run_container_version_test" "$fn must verify its version host-side"
        assert_contains "$body" "version_fence_probe" "$fn must fence its version output"
    done

    # Discrimination check: the assertion above must be capable of NOT matching.
    # test_docker_pull_and_run verifies its version without a container fence
    # (it captures `docker run --rm <image> --version` directly), so it must not
    # contain either token -- if it did, the loop above would be matching
    # something present in every function and asserting nothing.
    body="$(extract_fn test_docker_pull_and_run)"
    assert_not_contains "$body" "version_fence_probe" "the structural check must be able to miss, or it proves nothing"
    assert_contains "$body" "verify_version" "test_docker_pull_and_run still compares its version directly"
    log_pass "all seven container install methods verify a version"
}

log_test "test-installmethods-container-version"
test_correct_version_is_accepted
test_the_incident_is_caught
test_nothing_reported_is_never_a_pass
test_transcript_noise_cannot_satisfy_the_check
test_a_failing_container_fails_the_test
test_fence_extraction_takes_only_the_fenced_region
test_every_container_method_routes_through_the_fence
echo ""
log_pass "all tests passed"
