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
# Point the ratchet file at a non-existent path so unit tests stay
# independent of the production .ci/config/release-contract-floor.txt
# value. Individual cases that exercise the ratchet override it explicitly.
export RSV_FLOOR_FILE="/nonexistent/release-contract-floor.txt"
# shellcheck source=../../lib/release-state-validator.sh
source "$REPO_ROOT/.ci/scripts/lib/release-state-validator.sh"

# Small helpers — rsv_assert_bijection emits drift-or-OK to stdout; we capture
# both the exit code and the output to assert both at once.
run_assert() {
    local cli="$1" tags="$2" in_flight="${3:-}"
    local out rc=0
    out="$(rsv_assert_bijection "$cli" "$tags" "$in_flight" 2>&1)" || rc=$?
    printf '%s\n' "$out"
    return "$rc"
}

test_all_committed_passes() {
    log_test "all-committed → OK"
    local out rc=0
    out="$(run_assert \
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
    out="$(run_assert "" "")" || rc=$?
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
        "$(printf 'v1.0.0\n')")" || rc=$?
    assert_exit_code 0 "$rc" "orphan is not sentinel-vs-tag drift"
    log_pass "orphan-prefix"
}

test_sentinel_without_tag_fails() {
    log_test "cli sentinel present, tag missing → DRIFT (this is the #458 bug)"
    local out rc=0
    out="$(run_assert \
        "$(printf 'v1.0.0\nv1.0.5\n')" \
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
        "$(printf 'v1.0.0\nv1.0.5\n')")" || rc=$?
    assert_exit_code 1 "$rc" "tag-without-sentinel must fail"
    assert_contains "$out" "DRIFT v1.0.5" "names the drifted version"
    assert_contains "$out" "git tag present, cli sentinel missing" "identifies direction"
    assert_contains "$out" "re-run CI to produce artifacts" "remediation present"
    log_pass "tag-without-sentinel"
}

test_in_flight_excluded() {
    log_test "in-flight version with no sentinel yet → excluded from bijection, gate passes"
    local out rc=0
    out="$(run_assert \
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
        "$(printf 'v1.0.5\nv1.0.6\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "override pushes floor up; drift below it suppressed"
    assert_not_contains "$out" "DRIFT v1.0.6" "v1.0.6 < override; not flagged"
    assert_contains "$out" "floor: v1.5.0" "OK line reflects overridden floor"
    log_pass "explicit-override"
}

test_ratchet_lifts_floor_above_observed() {
    log_test "ratchet file value lifts floor above observed CLI sentinels (regression guard)"
    # If an operator scrubs a recent cli sentinel, the observed oldest
    # shifts up silently. The ratchet's role is to remember where the
    # floor used to be so the bijection still fires for the now-missing
    # version. Here: observed oldest is v1.0.8, but the ratchet says
    # v1.0.6 -- but ratchet is BELOW observed, so observed wins (floor
    # advances, not retreats). Then with ratchet=v1.0.10 (above observed),
    # the ratchet wins and v1.0.8/v1.0.9 below the floor get suppressed.
    local tmpfile
    tmpfile="$(mktemp)"

    # Case 1: ratchet below observed → observed wins.
    echo "v1.0.6" >"$tmpfile"
    local out rc=0
    out="$(RSV_FLOOR_FILE="$tmpfile" rsv_assert_bijection \
        "$(printf 'v1.0.8\nv1.0.9\n')" \
        "$(printf 'v1.0.6\nv1.0.7\nv1.0.8\nv1.0.9\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "ratchet < observed: observed v1.0.8 floor used"
    assert_contains "$out" "floor: v1.0.8" "floor message names v1.0.8"
    assert_not_contains "$out" "DRIFT v1.0.6" "v1.0.6 below floor; suppressed"

    # Case 2: ratchet above observed → ratchet wins, drift still suppressed
    # below floor.
    echo "v1.0.10" >"$tmpfile"
    rc=0
    out="$(RSV_FLOOR_FILE="$tmpfile" rsv_assert_bijection \
        "$(printf 'v1.0.8\nv1.0.10\n')" \
        "$(printf 'v1.0.8\nv1.0.9\nv1.0.10\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "ratchet > observed: ratchet floor used, no drift below"
    assert_contains "$out" "floor: v1.0.10" "ratchet pulls floor up to v1.0.10"
    assert_not_contains "$out" "DRIFT v1.0.8" "observed v1.0.8 cli sentinel below ratchet floor; suppressed"
    assert_not_contains "$out" "DRIFT v1.0.9" "v1.0.9 below ratchet floor; suppressed"

    rm -f "$tmpfile"
    log_pass "ratchet-lifts-floor"
}

test_ratchet_protects_against_all_sentinels_scrubbed() {
    log_test "ratchet pins floor even when every cli sentinel is missing"
    # Without the ratchet: if R2 returns an empty cli sentinel list (every
    # sentinel scrubbed, or a misconfigured probe), the validator short-
    # circuits to OK because "no contract in effect yet". That's the right
    # call for a fresh dev bucket, but the WRONG call for a production
    # bucket where releases have happened -- it would hide every drift.
    #
    # The ratchet defends that case: when observed is empty but the ratchet
    # remembers a version, the floor falls back to the ratchet value and
    # the bijection still applies.
    local tmpfile
    tmpfile="$(mktemp)"
    echo "v1.0.8" >"$tmpfile"
    local out rc=0
    out="$(RSV_FLOOR_FILE="$tmpfile" rsv_assert_bijection \
        "" \
        "$(printf 'v1.0.7\nv1.0.8\nv1.0.9\n')" \
        "" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "tags above ratchet with no cli sentinel must drift"
    assert_contains "$out" "DRIFT v1.0.8" "v1.0.8 tag without cli sentinel; ratchet keeps it in scope"
    assert_contains "$out" "DRIFT v1.0.9" "v1.0.9 likewise"
    assert_not_contains "$out" "DRIFT v1.0.7" "v1.0.7 below ratchet; still grandfathered"
    rm -f "$tmpfile"
    log_pass "ratchet-protects-empty-observed"
}

test_all_committed_passes
test_empty_state_passes
test_orphan_prefix_not_flagged
test_sentinel_without_tag_fails
test_tag_without_sentinel_fails
test_in_flight_excluded
test_in_flight_does_not_mask_other_drift
test_prerelease_tags_ignored
test_floor_excludes_pre_contract_tags
test_floor_does_not_mask_post_contract_drift
test_no_sentinels_short_circuits
test_explicit_override_still_works
test_ratchet_lifts_floor_above_observed
test_ratchet_protects_against_all_sentinels_scrubbed

# =============================================================================
# rsv_assert_channel_pointer_tagged -- the relation the bijection does NOT cover
# =============================================================================
# The bijection reconciles sentinels against tags, and a bump-none merge
# correctly skips BOTH. The channel pointer was advanced anyway, so it could
# name a version with no tag and a 404 notes URL. Measured live: cli/edge
# advertised 1.3.1 across three bump-none merges (#573, #574, #576) with no
# v1.3.1 tag, and promote-stable would have checked out `ref: v1.3.1` on
# 2026-09-01 AFTER the R2 and Docker halves succeeded.

run_pointer() { # <channel> <latest> <manifest> <tags> [in_flight]
    local rc=0
    POUT="$(rsv_assert_channel_pointer_tagged "$1" "$2" "$3" "$4" "${5:-}" 2>&1)" || rc=$?
    PRC="$rc"
}

POINTER_TAGS=$'v1.2.9\nv1.3.0\nv1.3.1'

test_pointer_naming_a_tagged_version_passes() {
    run_pointer edge v1.3.1 v1.3.1 "$POINTER_TAGS"
    assert_exit_code 0 "$PRC" "a tagged pointer must pass"
    assert_contains "$POUT" "OK:" "positive confirmation emitted"
    log_pass "a pointer naming a tagged version passes"
}

test_pointer_naming_an_untagged_version_is_caught() {
    # THE BUG, reproduced exactly.
    run_pointer edge v9.9.9 v9.9.9 "$POINTER_TAGS"
    assert_exit_code 1 "$PRC" "an untagged pointer MUST fail"
    assert_contains "$POUT" "NO git tag" "the finding names the cause"
    log_pass "a pointer naming an untagged version is caught"
}

test_torn_pointer_write_is_caught() {
    # latest.json and manifest.json are written seconds apart; disagreement
    # means install.sh and the auto-updater resolve to different versions.
    run_pointer edge v1.3.1 v1.3.0 "$POINTER_TAGS"
    assert_exit_code 1 "$PRC" "a torn write MUST fail"
    assert_contains "$POUT" "torn write" "the finding names the cause"
    log_pass "a torn pointer write is caught"
}

test_unreadable_pointer_is_not_a_pass() {
    # A pointer nobody could read is never a clean channel.
    run_pointer edge "" v1.3.1 "$POINTER_TAGS"
    assert_exit_code 1 "$PRC" "an unreadable pointer must NOT pass"
    assert_contains "$POUT" "never a pass" "refuses to certify a read it could not make"
    log_pass "an unreadable pointer fails rather than passing blind"
}

test_in_flight_version_is_excluded() {
    # The pointer for release X is written BEFORE X's tag is pushed. Without
    # this exclusion the relation would redden every release that uses it.
    run_pointer edge v9.9.9 v9.9.9 "$POINTER_TAGS" v9.9.9
    assert_exit_code 0 "$PRC" "the in-flight version must be excluded"
    assert_contains "$POUT" "in-flight" "says why it was excluded"
    log_pass "the in-flight version is excluded, so the gate is safe on the release path"
}

test_control_the_tag_lookup_can_fail() {
    # CONTROL, by construction: a version present in the tag list must pass and
    # one absent must fail, using the SAME inputs. If both answered the same the
    # assertions above would be decoration.
    run_pointer edge v1.3.0 v1.3.0 "$POINTER_TAGS"
    local tagged="$PRC"
    run_pointer edge v0.0.1 v0.0.1 "$POINTER_TAGS"
    local untagged="$PRC"
    [[ "$tagged" -eq 0 && "$untagged" -eq 1 ]] ||
        log_fail "CONTROL DID NOT FIRE: tagged=$tagged untagged=$untagged; the tag lookup does not discriminate"
    log_pass "control fires: the tag lookup distinguishes tagged from untagged"
}

test_pointer_naming_a_tagged_version_passes
test_pointer_naming_an_untagged_version_is_caught
test_torn_pointer_write_is_caught
test_unreadable_pointer_is_not_a_pass
test_in_flight_version_is_excluded
test_control_the_tag_lookup_can_fail

log_pass "all release-state-consistency cases"
echo "  Blind spot: rsv_assert_channel_pointer_tagged is PURE. These cases prove"
echo "  the judgement, not the READS -- whether check-release-state.sh actually"
echo "  fetches latest.json/manifest.json and the git tags is not covered here,"
echo "  and cannot be locally (aws is unavailable on host and in the devbox)."
