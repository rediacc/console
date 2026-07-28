#!/bin/bash
# Unit test for the channel gating of the APT/RPM metadata assertions in
# .ci/scripts/release/validate-stage-artifacts.sh.
#
# WHAT BROKE. The script asserted APT and RPM repository metadata
# unconditionally. That metadata is CHANNEL-SCOPED and is built by cd-stage.yml's
# "Build package repositories" step, which self-gates on `inputs.channel != ''`.
# The channel is empty for any event that is not push or pull_request -- i.e.
# for the nightly, deliberately, so a scheduled run cannot orphan ~5 GB of R2
# bytes. So on every nightly the metadata was correctly absent and the validator
# failed the stage anyway:
#
#   run 30237524399 (2026-07-27), Stage Artifacts:
#     ##[error]No APT metadata files found
#     ##[error]No RPM metadata files found
#
# One of the three breaks behind twelve consecutive red nightlies.
#
# THE DANGEROUS DIRECTION. A channel gate is a WEAKENED CHECK, and the whole
# reason this bug survived is that nobody was watching a weakened signal. So the
# tests that matter most here are the ones proving the skip is NARROW: the
# assertions must still fire on a real release channel, and every other artifact
# assertion must still fire when the channel is empty.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

# get_repo_root() resolves from the SCRIPT's own path (.ci/scripts/lib -> up 3),
# not from cwd, so the fixture has to mirror the tree layout rather than just
# being a directory with a dist/ in it.
FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT
mkdir -p "$FIXTURE/.ci/scripts/release" "$FIXTURE/.ci/scripts/lib"
cp "$REPO_ROOT/.ci/scripts/release/validate-stage-artifacts.sh" "$FIXTURE/.ci/scripts/release/"
cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$FIXTURE/.ci/scripts/lib/"
VALIDATOR="$FIXTURE/.ci/scripts/release/validate-stage-artifacts.sh"

# Build a COMPLETE staged tree, then let each case remove exactly one thing.
seed_dist() {
    rm -rf "$FIXTURE/dist"
    mkdir -p "$FIXTURE/dist/cli" "$FIXTURE/dist/packages" "$FIXTURE/dist/pages" \
        "$FIXTURE/dist/repos/apt/dists" "$FIXTURE/dist/repos/rpm/repodata"
    touch "$FIXTURE/dist/cli/rdc-linux-x64"
    # Two of each: the validator asserts >= 2 per package format.
    for i in 1 2; do
        touch "$FIXTURE/dist/packages/pkg$i.deb" "$FIXTURE/dist/packages/pkg$i.rpm" \
            "$FIXTURE/dist/packages/pkg$i.apk" "$FIXTURE/dist/packages/pkg$i.pkg.tar.zst"
    done
    touch "$FIXTURE/dist/pages/index.html"
    touch "$FIXTURE/dist/repos/apt/dists/Release" "$FIXTURE/dist/repos/rpm/repodata/repomd.xml"
}

drop_metadata() { rm -rf "$FIXTURE/dist/repos"; }

# validate <event> <channel> -> prints "PASS" or "FAIL".
#
# The validator's own output goes to a FILE rather than a variable: every call
# site here is `$(validate ...)`, which runs the function in a subshell, so an
# assignment inside it could never reach the caller. (The first draft used a
# global and died on `unbound variable` at the first assertion that read it.)
validate() {
    local rc=0
    : >"$FIXTURE/summary.md"
    EVENT_NAME="$1" CHANNEL="$2" NEXT_VERSION=1.2.3 \
        GITHUB_STEP_SUMMARY="$FIXTURE/summary.md" GITHUB_OUTPUT="$FIXTURE/output.txt" \
        bash "$VALIDATOR" >"$FIXTURE/last-output.txt" 2>&1 || rc=$?
    [[ $rc -eq 0 ]] && echo "PASS" || echo "FAIL"
}
last_output() { cat "$FIXTURE/last-output.txt"; }

# ---------------------------------------------------------------------------

test_complete_tree_on_a_release_channel_passes() {
    # Baseline. If this failed, every other case would be meaningless.
    seed_dist
    assert_eq "$(validate push edge)" "PASS" "a complete staged tree on a real channel validates"
    log_pass "a complete tree on a release channel passes"
}

test_metadata_assertions_STILL_FIRE_on_a_release_channel() {
    # THE CONTROL. The channel gate must not have turned these assertions off
    # for the runs that actually publish. This is the case that proves the fix
    # narrowed the check rather than deleting it.
    seed_dist
    drop_metadata
    assert_eq "$(validate push edge)" "FAIL" "missing metadata on a real channel must still fail"
    assert_contains "$(last_output)" "No APT metadata files found" "the APT assertion still fires"
    assert_contains "$(last_output)" "No RPM metadata files found" "the RPM assertion still fires"
    log_pass "on a release channel the metadata assertions still fail the stage"
}

test_pr_channel_also_still_asserts() {
    # pr-N is a real channel and does stage package repositories.
    seed_dist
    drop_metadata
    assert_eq "$(validate pull_request pr-540)" "FAIL" "a pr-N channel must still assert metadata"
    log_pass "a pr-N channel still asserts metadata"
}

test_empty_channel_skips_only_the_metadata_assertions() {
    # THE FIX. This is the exact nightly shape: no channel, so no package
    # repositories were built, so their absence is correct.
    seed_dist
    drop_metadata
    assert_eq "$(validate schedule '')" "PASS" "the nightly shape must validate"
    assert_not_contains "$(last_output)" "No APT metadata files found" "the APT assertion is skipped"
    assert_not_contains "$(last_output)" "No RPM metadata files found" "the RPM assertion is skipped"
    log_pass "an empty channel skips exactly the two metadata assertions"
}

test_the_skip_is_announced_not_silent() {
    # A silently weakened check is how this class of bug survives. The skip has
    # to be visible in the run summary and as a notice.
    seed_dist
    drop_metadata
    validate schedule '' >/dev/null
    assert_contains "$(last_output)" "::notice::" "the skip emits a notice"
    assert_contains "$(cat "$FIXTURE/summary.md")" "metadata assertions skipped" \
        "the skip is recorded in the step summary a human reads"
    log_pass "the skip announces itself in both the log and the step summary"
}

test_empty_channel_does_NOT_weaken_the_other_assertions() {
    # THE OTHER DANGEROUS DIRECTION, and the one a careless fix gets wrong: the
    # channel gate must cover ONLY the two metadata checks. If a nightly stops
    # producing CLI binaries or half the packages, that must still be red --
    # otherwise "fix the nightly" would have quietly become "stop checking it".
    seed_dist
    drop_metadata
    rm -f "$FIXTURE/dist/cli/rdc-linux-x64"
    assert_eq "$(validate schedule '')" "FAIL" "missing CLI artifacts must still fail on a channel-less run"
    assert_contains "$(last_output)" "No CLI artifacts found" "the CLI assertion is untouched"

    seed_dist
    drop_metadata
    rm -f "$FIXTURE/dist/packages/pkg2.deb"
    assert_eq "$(validate schedule '')" "FAIL" "too few DEBs must still fail on a channel-less run"
    assert_contains "$(last_output)" "Expected at least 2 DEB packages" "the DEB assertion is untouched"

    seed_dist
    drop_metadata
    rm -f "$FIXTURE/dist/packages/pkg2.rpm"
    assert_eq "$(validate schedule '')" "FAIL" "too few RPMs must still fail on a channel-less run"

    seed_dist
    drop_metadata
    rm -f "$FIXTURE/dist/packages/pkg2.pkg.tar.zst"
    assert_eq "$(validate schedule '')" "FAIL" "too few Arch packages must still fail on a channel-less run"
    log_pass "the channel gate covers ONLY the metadata assertions; every other check is untouched"
}

log_test "test-stage-artifacts-channel"
test_complete_tree_on_a_release_channel_passes
test_metadata_assertions_STILL_FIRE_on_a_release_channel
test_pr_channel_also_still_asserts
test_empty_channel_skips_only_the_metadata_assertions
test_the_skip_is_announced_not_silent
test_empty_channel_does_NOT_weaken_the_other_assertions
echo ""
log_pass "all tests passed"
