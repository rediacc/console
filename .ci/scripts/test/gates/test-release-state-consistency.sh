#!/bin/bash
# Unit-tests the rsv_assert_bijection function in release-state-validator.sh
# against synthetic version lists. The live R2 + git probes are exercised
# end-to-end by the quality gate itself during CI; this test pins the pure
# assertion logic so drift-detection behaviour stays correct even if callers
# refactor.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"
# Clear the grandfather baseline before sourcing so the production default
# does not silently exclude versions we use in test fixtures. Individual
# grandfather cases set the env var explicitly.
export RSV_GRANDFATHER_BEFORE=""
# shellcheck source=../../lib/release-state-validator.sh
source "$REPO_ROOT/.ci/scripts/lib/release-state-validator.sh"

# Small helpers — rsv_assert_bijection emits drift-or-OK to stdout; we capture
# both the exit code and the output to assert both at once.
run_assert() {
    local cli="$1" desk="$2" tags="$3" in_flight="${4:-}"
    local out rc=0
    out="$(rsv_assert_bijection "$cli" "$desk" "$tags" "$in_flight" 2>&1)" || rc=$?
    printf '%s\n' "$out"
    return "$rc"
}

test_all_committed_passes() {
    log_test "all-committed → OK"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\nv1.0.1\nv1.0.2\n')" \
        "$(printf 'v1.0.0\nv1.0.1\nv1.0.2\n')" \
        "$(printf 'v1.0.0\nv1.0.1\nv1.0.2\n')")" || rc=$?
    assert_exit_code 0 "$rc" "bijection should hold"
    assert_contains "$out" "OK:" "positive confirmation emitted"
    assert_not_contains "$out" "DRIFT" "no drift lines"
    log_pass "all-committed"
}

test_empty_state_passes() {
    log_test "no sentinels + no tags → OK"
    local out rc=0
    out="$(run_assert "" "" "")" || rc=$?
    assert_exit_code 0 "$rc" "empty state is a bijection"
    assert_contains "$out" "OK:" "positive confirmation emitted"
    log_pass "empty-state"
}

test_orphan_prefix_not_flagged() {
    # The library flags sentinel↔tag drift, not the presence of orphan bytes
    # without a sentinel. Orphans are handled upstream by the pre-upload scrub.
    log_test "orphan prefix (no sentinel, no tag) → OK (not this gate's concern)"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')")" || rc=$?
    assert_exit_code 0 "$rc" "orphan is not sentinel-vs-tag drift"
    log_pass "orphan-prefix"
}

test_sentinel_without_tag_fails() {
    log_test "cli sentinel present, tag missing → DRIFT (this is the #458 bug)"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\nv1.0.5\n')" \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')")" || rc=$?
    assert_exit_code 1 "$rc" "sentinel-without-tag must fail"
    assert_contains "$out" "DRIFT v1.0.5" "names the drifted version"
    assert_contains "$out" "cli sentinel present, git tag missing" "identifies direction"
    assert_contains "$out" "re-run CD to tag" "remediation present"
    log_pass "sentinel-without-tag"
}

test_tag_without_sentinel_fails() {
    log_test "git tag present, cli sentinel missing → DRIFT"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\nv1.0.5\n')")" || rc=$?
    assert_exit_code 1 "$rc" "tag-without-sentinel must fail"
    assert_contains "$out" "DRIFT v1.0.5" "names the drifted version"
    assert_contains "$out" "git tag present, cli sentinel missing" "identifies direction"
    assert_contains "$out" "re-run CI to produce artifacts" "remediation present"
    log_pass "tag-without-sentinel"
}

test_desktop_without_cli_fails() {
    log_test "desktop sentinel present without cli sentinel → DRIFT"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\nv1.0.5\n')" \
        "$(printf 'v1.0.0\nv1.0.5\n')")" || rc=$?
    assert_exit_code 1 "$rc" "desktop-without-cli must fail"
    assert_contains "$out" "DRIFT v1.0.5" "names the drifted version"
    assert_contains "$out" "desktop sentinel present, cli sentinel missing" "identifies invariant violated"
    log_pass "desktop-without-cli"
}

test_desktop_missing_is_fine() {
    # Desktop is optional — a platform-skipped or cli-only release is valid.
    log_test "cli sentinel + tag present, desktop absent → OK"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\nv1.0.5\n')" \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\nv1.0.5\n')")" || rc=$?
    assert_exit_code 0 "$rc" "desktop absence is legitimate"
    log_pass "desktop-optional"
}

test_in_flight_excluded() {
    log_test "in-flight version with no sentinel yet → excluded from bijection, gate passes"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')" \
        "v1.0.5")" || rc=$?
    assert_exit_code 0 "$rc" "in-flight exclusion prevents self-flag"
    log_pass "in-flight-excluded"
}

test_in_flight_does_not_mask_other_drift() {
    log_test "in-flight exclusion does not hide unrelated drift"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\nv1.0.3\n')" \
        "" \
        "$(printf 'v1.0.0\n')" \
        "v1.0.5")" || rc=$?
    assert_exit_code 1 "$rc" "v1.0.3 drift must still fire"
    assert_contains "$out" "DRIFT v1.0.3" "unrelated drift still caught"
    assert_not_contains "$out" "DRIFT v1.0.5" "in-flight remains excluded"
    log_pass "in-flight-targeted-exclusion"
}

test_prerelease_tags_ignored() {
    log_test "pre-release tags (v1.0.0-beta.1) are not part of the bijection"
    # rsv_list_git_tags filters these out in live use; assert the assertion
    # function also ignores them when they happen to appear in inputs.
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\n')" \
        "$(printf 'v1.0.0\nv1.0.1-beta.1\n')")" || rc=$?
    assert_exit_code 0 "$rc" "pre-release tag must not trigger drift"
    log_pass "prerelease-filtered"
}

test_grandfather_excludes_old_tags() {
    log_test "tags <= RSV_GRANDFATHER_BEFORE are excluded (rollout grace)"
    # Under live config, every pre-rollout tag (v0.9.x, v1.0.0-1.0.4) lacks
    # the new sentinel. With grandfather=v1.0.4, those drifts must NOT fire,
    # but a fresh tag (v1.0.5+) without a sentinel still must.
    local out rc=0
    out="$(RSV_GRANDFATHER_BEFORE="v1.0.4" rsv_assert_bijection \
        "" \
        "" \
        "$(printf 'v0.9.5\nv1.0.0\nv1.0.4\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "grandfathered tags must not trigger drift"
    assert_not_contains "$out" "DRIFT v0.9.5" "v0.9.5 is grandfathered"
    assert_not_contains "$out" "DRIFT v1.0.0" "v1.0.0 is grandfathered"
    assert_not_contains "$out" "DRIFT v1.0.4" "v1.0.4 (== baseline) is grandfathered"
    log_pass "grandfather-excludes-old-tags"
}

test_grandfather_does_not_mask_post_rollout_drift() {
    log_test "tags > RSV_GRANDFATHER_BEFORE still subject to bijection"
    local out rc=0
    out="$(RSV_GRANDFATHER_BEFORE="v1.0.4" rsv_assert_bijection \
        "" \
        "" \
        "$(printf 'v1.0.0\nv1.0.5\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "post-rollout drift must still fire"
    assert_contains "$out" "DRIFT v1.0.5" "v1.0.5 is past baseline; drift fires"
    assert_not_contains "$out" "DRIFT v1.0.0" "v1.0.0 is grandfathered"
    log_pass "grandfather-does-not-mask"
}

test_all_committed_passes
test_empty_state_passes
test_orphan_prefix_not_flagged
test_sentinel_without_tag_fails
test_tag_without_sentinel_fails
test_desktop_without_cli_fails
test_desktop_missing_is_fine
test_in_flight_excluded
test_in_flight_does_not_mask_other_drift
test_prerelease_tags_ignored
test_grandfather_excludes_old_tags
test_grandfather_does_not_mask_post_rollout_drift

log_pass "all release-state-consistency cases"
