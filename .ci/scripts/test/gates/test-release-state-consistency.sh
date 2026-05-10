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
# The floor is now data-derived from the cli sentinel list passed to each
# call (no module-level default), so tests no longer need to clear an env
# var here. The override-only escape hatch (RSV_GRANDFATHER_BEFORE) is
# unset by default and individual cases set it explicitly when exercising
# override semantics.
unset RSV_GRANDFATHER_BEFORE
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

test_floor_excludes_pre_contract_tags() {
    log_test "tags older than the oldest cli sentinel are excluded (data-derived floor)"
    # Mirrors the live shape: pre-contract tags exist (v0.9.5..v1.0.4) but
    # have no sentinel; the contract first wrote a sentinel at v1.0.5, and
    # later releases (v1.0.6+) carry both. The floor is auto-derived from
    # the cli list, so no override is set here.
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.5\nv1.0.6\n')" \
        "$(printf 'v1.0.5\nv1.0.6\n')" \
        "$(printf 'v0.9.5\nv1.0.0\nv1.0.4\nv1.0.5\nv1.0.6\n')")" || rc=$?
    assert_exit_code 0 "$rc" "pre-contract tags must not trigger drift"
    assert_not_contains "$out" "DRIFT v0.9.5" "v0.9.5 is below floor"
    assert_not_contains "$out" "DRIFT v1.0.0" "v1.0.0 is below floor"
    assert_not_contains "$out" "DRIFT v1.0.4" "v1.0.4 is below floor"
    assert_contains "$out" "floor: v1.0.5" "OK line surfaces derived floor"
    log_pass "floor-excludes-pre-contract"
}

test_floor_does_not_mask_post_contract_drift() {
    log_test "tags at-or-above the derived floor still subject to bijection"
    # cli sentinels exist for v1.0.5 and v1.0.6; tag v1.0.7 has no
    # sentinel, so the floor (v1.0.5) does not hide it.
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.5\nv1.0.6\n')" \
        "" \
        "$(printf 'v1.0.5\nv1.0.6\nv1.0.7\n')")" || rc=$?
    assert_exit_code 1 "$rc" "post-contract drift must still fire"
    assert_contains "$out" "DRIFT v1.0.7" "v1.0.7 is at-or-above floor; drift fires"
    assert_not_contains "$out" "DRIFT v1.0.5" "v1.0.5 (== floor) is committed, no drift"
    log_pass "floor-does-not-mask"
}

test_no_sentinels_short_circuits() {
    log_test "no cli sentinels (and no override) → bijection short-circuits to OK"
    # Fresh dev bucket / pre-rollout state: contract not in effect for any
    # tag we have. Asserting drift on every tag would be useless noise.
    local out rc=0
    out="$(run_assert \
        "" \
        "" \
        "$(printf 'v0.9.5\nv1.0.0\nv1.0.4\n')")" || rc=$?
    assert_exit_code 0 "$rc" "no-sentinels state is a no-op"
    assert_contains "$out" "contract not in effect" "diagnostic message present"
    log_pass "no-sentinels-short-circuits"
}

test_explicit_override_still_works() {
    log_test "RSV_GRANDFATHER_BEFORE overrides the data-derived floor"
    # Operators can pin a synthetic floor for emergency dry-runs or tests.
    # Here we feed a cli sentinel at v1.0.5 (which would normally derive
    # floor=v1.0.5) but override the floor up to v1.5.0 — every drift
    # below v1.5.0 must then be silenced.
    local out rc=0
    out="$(RSV_GRANDFATHER_BEFORE="v1.5.0" rsv_assert_bijection \
        "$(printf 'v1.0.5\n')" \
        "" \
        "$(printf 'v1.0.5\nv1.0.6\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "override pushes floor up; drift below it suppressed"
    assert_not_contains "$out" "DRIFT v1.0.6" "v1.0.6 < override; not flagged"
    assert_contains "$out" "floor: v1.5.0" "OK line reflects overridden floor"
    log_pass "explicit-override"
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
test_floor_excludes_pre_contract_tags
test_floor_does_not_mask_post_contract_drift
test_no_sentinels_short_circuits
test_explicit_override_still_works

log_pass "all release-state-consistency cases"
