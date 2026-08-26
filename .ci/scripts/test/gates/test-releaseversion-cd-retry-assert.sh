#!/bin/bash
# Both-ways test for the artifact-version assertion's reachability in
# .github/workflows/cd-v2.yml.
#
# WHAT THE ASSERTION IS FOR. assert-artifact-version.sh compares the version
# baked into the CI artifacts against the version CD is about to publish them
# under. It is the only thing standing between "these bytes were built as
# 1.2.16" and a GitHub Release labelled 1.2.17.
#
# WHAT WAS BROKEN. The step carried `retry_mode != 'true'`, excused by a comment
# claiming "retry uses the latest tag's version, which the artifacts already
# match by definition". They do not. Retry takes its VERSION from
# resolve-version.sh --current, but its ARTIFACTS from resolve-ci-run.sh, which
# with no ci_run_id supplied picks the LATEST GREEN CI RUN ON MAIN -- not the
# run that cut that tag. A retry dispatched after any newer CI went green
# republishes those newer artifacts under the older tag, which is precisely the
# mismatch the assertion exists to catch, with the assertion switched off.
#
# This is a text test rather than a YAML-object test on purpose: the condition
# is a GitHub expression inside a folded scalar, so its meaning lives in the
# string either way, and awk keeps the gate dependency-free.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WORKFLOW="$REPO_ROOT/.github/workflows/cd-v2.yml"
STEP_NAME="Assert artifact version matches promotion target"

# Prints the step's own YAML block: from its `- name:` line up to (not
# including) the next step at the same indentation.
step_block() {
    awk -v name="$STEP_NAME" '
        index($0, "- name: " name) { p = 1; print; next }
        p && /^      - / { exit }
        p { print }
    ' "$1"
}

test_step_exists() {
    log_test "the artifact-version assertion step is present"
    local block
    block="$(step_block "$WORKFLOW")"
    assert_contains "$block" "assert-artifact-version.sh" "the step must still run the assertion script"
    log_pass "step found in cd-v2.yml"
}

test_retry_mode_no_longer_skips_it() {
    log_test "retry mode does NOT skip the assertion"
    local block
    block="$(step_block "$WORKFLOW")"
    assert_not_contains "$block" "retry_mode" "retry must not be excluded from the assertion"
    log_pass "the assertion runs in retry mode"
}

test_workers_only_still_skips_it() {
    log_test "workers-only still skips the assertion"
    local block
    block="$(step_block "$WORKFLOW")"
    assert_contains "$block" "workers_only != 'true'" "workers-only promotes no artifacts, so it stays excluded"
    # `skip_release` WAS REMOVED FROM cd-v2 (2026-08-26) and asserting it here
    # would now pin a condition that cannot exist. decide-release-mode.sh wrote
    # that output `false` on all three of its paths, so every guard reading it was
    # permanently true -- a condition that cannot be false is a claim, not a guard,
    # and one of cd-v2's own comments credited it with a skip `workers_only` was
    # actually performing. The operator was offered the revert and declined.
    #
    # What genuinely keeps a skipped release excluded is upstream: cd-v2 is only
    # DISPATCHED when the release is not skipped (initialize decides, ci.yml
    # guards the dispatch). So the assertion that belongs here is that the stale
    # condition is GONE, not that it is present.
    # Match the CONDITION (`outputs.skip_release`), not the bare word: cd-v2 now
    # carries a comment explaining why the clause was removed, and asserting on
    # the word alone flagged that prose. A gate that cannot survive being written
    # about is too broad.
    assert_not_contains "$block" "outputs.skip_release" \
        "the permanently-true skip_release guard is gone; exclusion is upstream, at dispatch"
    log_pass "workers-only remains excluded"
}

# A step that runs in retry mode but reads only the normal-mode version output
# would receive an EMPTY VERSION there, which assert-artifact-version.sh rejects
# outright -- a hard failure on every retry. The env must cover both paths, in
# the same precedence the job's own next_version output uses.
test_version_env_covers_retry_mode() {
    log_test "VERSION is wired for both the retry and normal paths"
    local block
    block="$(step_block "$WORKFLOW")"
    assert_contains "$block" "steps.version.outputs.next_version" "the retry-mode version output must be read"
    assert_contains "$block" "steps.init.outputs.next_version" "the normal-mode version output must be read"
    log_pass "VERSION covers retry and normal modes"
}

# THE CONTROL. Plant the old condition in a copy and prove the checks above go
# red on it. Without this, "no retry_mode found" could just as easily mean the
# extractor matched nothing.
test_planted_old_condition_is_caught() {
    log_test "control: the pre-fix condition is detected"
    local fixture
    fixture="$(mktemp -d)"
    # THE PLANT ANCHOR MOVED (2026-08-26). It used to substitute on the
    # `skip_release != 'true' &&` line, which no longer exists -- that guard was
    # permanently true and was removed. The control caught its own plant failing
    # to land rather than passing over an unmutated fixture, which is exactly
    # what it is for. Re-anchored on the condition that IS still there.
    sed "s|^        if: steps.skip-check.outputs.workers_only != 'true'$|        if: >-\n          steps.skip-check.outputs.workers_only != 'true' \&\&\n          steps.skip-check.outputs.retry_mode != 'true'|" \
        "$WORKFLOW" >"$fixture/cd-v2.yml"

    local block
    block="$(step_block "$fixture/cd-v2.yml")"
    rm -rf "$fixture"

    assert_contains "$block" "retry_mode" "planted condition must be visible to the extractor (else these checks prove nothing)"
    assert_contains "$block" "assert-artifact-version.sh" "planted fixture must still be the right step"
    log_pass "the extractor demonstrably sees a retry_mode exclusion when one exists"
}

test_step_exists
test_retry_mode_no_longer_skips_it
test_workers_only_still_skips_it
test_version_env_covers_retry_mode
test_planted_old_condition_is_caught
