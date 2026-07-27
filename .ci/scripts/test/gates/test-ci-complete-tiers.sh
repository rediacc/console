#!/bin/bash
# Both-ways test for the tier logic in .ci/scripts/ci/assert-ci-complete.sh,
# added with the pointer-bump fast path (2026-07-22).
#
# The contract under test:
#   - Normally, BUILD_DOCKER / BUILD_DOCKER_FAST / BUILD_CLI are HARD-required:
#     a skip means the DAG broke and must read as red.
#   - Under POINTER_BUMP_ONLY=true those three are DELIBERATELY skipped by
#     ci.yml (content proven identical to a full-CI-green baseline), so their
#     skips must read as green -- but a genuine FAILURE of any job must still
#     be red, and INITIALIZE must still be hard-required.
#
# Both directions matter: too strict and every fast-path run is red (the
# fast path is dead on arrival); too lax and a skipped build reads as green
# on a normal run (the exact DAG-breakage the hard tier exists to catch).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ASSERT="$REPO_ROOT/.ci/scripts/ci/assert-ci-complete.sh"

# Every job green -- the baseline every case below perturbs.
declare -A BASELINE_RESULTS=(
    [RESULT_INITIALIZE]=success
    [RESULT_BUILD_DOCKER]=success
    [RESULT_BUILD_DOCKER_FAST]=success
    [RESULT_BUILD_CLI]=success
    [RESULT_QUALITY]=success
    [RESULT_REVIEW_GATE]=success
    [RESULT_STRIPE_SANDBOX]=success
    [RESULT_PACKAGE_TESTS]=success
    [RESULT_STAGE_ARTIFACTS]=success
    [RESULT_VALIDATE_INSTALL]=success
    [RESULT_VALIDATE_PROMOTE]=success
    [RESULT_TESTS]=success
    [RESULT_ELITE_RUN_TEST]=success
    [RESULT_OPS_TESTS]=success
    [RESULT_UPDATE_FLOW_TEST]=success
    [RESULT_DEPLOY_PREVIEW]=success
    [RESULT_SMOKE_TEST_PREVIEW]=success
    [RESULT_BREAKPOINT_LIFECYCLE]=success
)

# run_assert <expected-exit> <case-name> [VAR=value ...]
# Runs assert-ci-complete.sh with the green baseline plus overrides.
run_assert() {
    local expected="$1" name="$2"
    shift 2
    local -a env_kv=()
    local key
    for key in "${!BASELINE_RESULTS[@]}"; do
        env_kv+=("${key}=${BASELINE_RESULTS[$key]}")
    done
    env_kv+=("$@")
    local rc=0
    env -i PATH="$PATH" HOME="$HOME" "${env_kv[@]}" bash "$ASSERT" >/dev/null 2>&1 || rc=$?
    assert_exit_code "$expected" "$rc" "$name"
    log_pass "$name"
}

# A fast-path run: builds (and their dependents) skipped -> must PASS.
FASTPATH_SKIPS=(
    POINTER_BUMP_ONLY=true
    RESULT_BUILD_DOCKER=skipped
    RESULT_BUILD_DOCKER_FAST=skipped
    RESULT_BUILD_CLI=skipped
    RESULT_STAGE_ARTIFACTS=skipped
    RESULT_VALIDATE_INSTALL=skipped
    RESULT_VALIDATE_PROMOTE=skipped
    RESULT_TESTS=skipped
    RESULT_ELITE_RUN_TEST=skipped
    RESULT_OPS_TESTS=skipped
    RESULT_UPDATE_FLOW_TEST=skipped
    RESULT_DEPLOY_PREVIEW=skipped
    RESULT_SMOKE_TEST_PREVIEW=skipped
    RESULT_STRIPE_SANDBOX=skipped
    RESULT_PACKAGE_TESTS=skipped
    # breakpoint-lifecycle's if: excludes pointer_bump_only, so it skips here too
    RESULT_BREAKPOINT_LIFECYCLE=skipped
)

test_all_green_passes() {
    run_assert 0 "all-green run passes (no fast path)"
}

test_fastpath_skips_pass() {
    run_assert 0 "fast path: skipped builds+dependents pass" "${FASTPATH_SKIPS[@]}"
}

test_skipped_build_fails_without_flag() {
    # The exact fast-path shape, but WITHOUT the flag: hard tier must fire.
    local -a no_flag=("${FASTPATH_SKIPS[@]:1}") # drop POINTER_BUMP_ONLY=true
    run_assert 1 "no flag: skipped BUILD_* stays red (DAG breakage)" "${no_flag[@]}"
}

test_flag_false_keeps_hard_tier() {
    run_assert 1 "POINTER_BUMP_ONLY=false keeps the hard tier" \
        POINTER_BUMP_ONLY=false RESULT_BUILD_CLI=skipped
}

test_failure_still_red_on_fastpath() {
    # The soft tier forgives skips, never failures.
    run_assert 1 "fast path: a FAILED build is still red" \
        POINTER_BUMP_ONLY=true RESULT_BUILD_DOCKER=failure
    run_assert 1 "fast path: a failed soft job (quality) is still red" \
        POINTER_BUMP_ONLY=true RESULT_QUALITY=failure
}

test_initialize_stays_hard_on_fastpath() {
    run_assert 1 "fast path: skipped INITIALIZE is still red" \
        POINTER_BUMP_ONLY=true RESULT_INITIALIZE=skipped
}

test_unset_var_still_fails() {
    # A renamed job must break loudly, fast path or not. env -u is not
    # available through `env -i` composition, so rebuild without the key.
    local -a env_kv=(POINTER_BUMP_ONLY=true)
    local key
    for key in "${!BASELINE_RESULTS[@]}"; do
        [[ "$key" == "RESULT_TESTS" ]] && continue
        env_kv+=("${key}=${BASELINE_RESULTS[$key]}")
    done
    local rc=0
    env -i PATH="$PATH" HOME="$HOME" "${env_kv[@]}" bash "$ASSERT" >/dev/null 2>&1 || rc=$?
    assert_exit_code 1 "$rc" "unset RESULT_ var fails even on fast path"
    log_pass "unset RESULT_ var fails even on fast path"
}

test_all_green_passes
test_fastpath_skips_pass
test_skipped_build_fails_without_flag
test_flag_false_keeps_hard_tier
test_failure_still_red_on_fastpath
test_initialize_stays_hard_on_fastpath
test_unset_var_still_fails
