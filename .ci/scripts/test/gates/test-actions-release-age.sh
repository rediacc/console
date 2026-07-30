#!/bin/bash
# Test for the release-age deferral and the anti-vacuity guard in
# scripts/check-actions.ts.
#
# TWO DEFECTS THIS COVERS.
#
# 1. NO NOTION OF RELEASE AGE. The gate demanded an upgrade the instant upstream
#    published one. Measured 2026-07-28: docker/login-action v4.5.2 was published
#    at 07:04:43Z and had reddened the build by 07:21Z, seventeen minutes later,
#    leaving only two bad options -- pin a barely-vetted SHA, or blocklist a
#    version that is not actually blocked. It now defers through the SAME shared
#    window as check-deps and check-embed-asset-freshness.
#
# 2. A VACUOUS PASS, the worse of the two. With every GitHub API lookup
#    rate-limited the gate printed "All GitHub Actions are up-to-date
#    (14 unknown)" and exited 0. Fourteen unknown means fourteen UNCHECKED, so it
#    reported freshness it had verified for nothing, and an offline run would
#    have done that indefinitely.
#
# WHY THIS TEST IS OFFLINE. Its first version drove the real gate four times,
# which needed a GitHub token, spent ~56 API calls per run, and FAILED in CI's
# quality-gate harness where no token exists. Worse, when the anonymous limit
# tripped it passed for the wrong reason: it read "nothing fresh upstream" from
# output that actually said "nothing could be checked", which is the very defect
# it exists to catch. Pure logic gets tested purely.
#
# WHY NOT IMPORT check-actions.ts DIRECTLY. It invokes checkActions() at module
# scope, so importing it would run the gate. Adding a main-module guard to make
# it importable was rejected deliberately: a guard that is subtly wrong makes
# `npm run check:actions` exit 0 while doing nothing, which is a far worse
# vacuous pass than the one being fixed. The deferral logic is exercised through
# the shared lib it delegates to, and the wiring is pinned against the source.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-actions.ts"
LIB="$REPO_ROOT/scripts/lib/release-age.ts"

# window <published-iso> <now-iso> <min-age-ms> -> "deferred" | "eligible"
# Drives the REAL shared helper the gate delegates to, so this is behaviour and
# not a re-implementation.
window() {
    (cd "$REPO_ROOT" && npx tsx --eval "
import { isWithinFreshnessWindow } from './scripts/lib/release-age.ts';
const published = Date.parse('$1');
const now = Date.parse('$2');
process.stdout.write(isWithinFreshnessWindow(published, now, $3) ? 'deferred' : 'eligible');
" 2>/dev/null)
}

# ---------------------------------------------------------------------------

test_the_shared_lib_is_what_the_gate_uses() {
    # Anti-vacuity for this file: every behavioural assertion below drives the
    # shared lib, so if the gate stopped delegating to it they would all pass
    # while proving nothing about the gate.
    assert_contains "$(cat "$GATE")" "from './lib/release-age.js'" \
        "check-actions.ts delegates to the shared release-age lib"
    assert_contains "$(cat "$GATE")" "isWithinFreshnessWindow(published, nowMs, minReleaseAgeMs)" \
        "and calls it with the publish time it fetched, not a local copy of the rule"
    log_pass "the gate delegates to the shared window, so exercising the lib exercises the gate"
}

test_a_fresh_release_is_deferred() {
    # Seventeen minutes old, the exact case that reddened the build.
    assert_eq "$(window '2026-07-28T07:04:43Z' '2026-07-28T07:21:00Z' 86400000)" "deferred" \
        "a release minutes old must be deferred, not demanded"
    log_pass "a seventeen-minute-old release is deferred"
}

test_an_aged_release_is_eligible() {
    # THE CONTROL. Same helper, same shape, older release: it must come back
    # eligible. Without this the deferral could be a mute button and every other
    # assertion here would still pass.
    assert_eq "$(window '2026-07-20T07:04:43Z' '2026-07-28T07:21:00Z' 86400000)" "eligible" \
        "a release well past the window must still be demanded"
    log_pass "control: an aged release remains eligible, so the window is not a mute button"
}

test_a_zero_window_defers_nothing() {
    # The second control: with the feature disabled, even a release published
    # this instant is eligible. Proves the deferral is driven by the window
    # rather than by something incidental.
    assert_eq "$(window '2026-07-28T07:04:43Z' '2026-07-28T07:04:44Z' 0)" "eligible" \
        "a zero window disables deferral entirely"
    log_pass "control: a zero window defers nothing"
}

test_null_policy_is_fail_closed() {
    # A lookup hiccup must never manufacture a "you must upgrade now" failure.
    # Pinned against the source: the lib deliberately leaves null-handling to the
    # caller, and this gate's choice is the fail-closed one.
    local src
    src="$(cat "$GATE")"
    assert_contains "$src" "if (!publishedAt) return true" \
        "a missing publish date defers"
    assert_contains "$src" "if (Number.isNaN(published)) return true" \
        "and so does an unparseable one"
    log_pass "an absent or unparseable timestamp fails closed to deferred"
}

test_deferrals_are_reported_not_silent() {
    # A silent defer is indistinguishable from a gate that stopped looking, which
    # is the failure mode this repo keeps finding in its own tooling.
    local src
    src="$(cat "$GATE")"
    assert_contains "$src" "Deferred upgrades" "held-back upgrades are printed"
    assert_contains "$src" "become normal findings once the window passes" \
        "and announced as postponed rather than dismissed"
    log_pass "deferrals are announced and explicitly temporary"
}

test_total_lookup_failure_is_a_failure_not_a_pass() {
    # THE VACUOUS-PASS FIX. Zero resolved of N is evidence the read failed, never
    # evidence that everything is current.
    local src
    src="$(cat "$GATE")"
    assert_contains "$src" "unknown.length === actions.size" \
        "a run that resolved NOTHING is detected"
    assert_contains "$src" "Could not resolve the latest release for ANY" \
        "and says so explicitly"
    assert_contains "$src" "Nothing was verified" \
        "naming the reason rather than implying an all-green result"
    log_pass "a total lookup failure is reported as a failure, not as up-to-date"
}

test_partial_failure_is_deliberately_not_fatal() {
    # Scope matters: failing on ONE flaky lookup would make this the flakiest
    # gate in CI. Only a total failure is fatal, and that choice is written down.
    assert_contains "$(cat "$GATE")" "only a TOTAL lookup failure is fatal" \
        "the narrow scope is stated where the guard lives"
    log_pass "a partial lookup failure stays non-fatal, by design"
}

test_window_source_is_the_shared_npmrc_setting() {
    # The number is a repo-wide policy, not a local preference.
    assert_contains "$(cat "$LIB")" "minimum-release-age" \
        "the shared lib reads the window from .npmrc"
    assert_contains "$(cat "$REPO_ROOT/.npmrc")" "minimum-release-age=1440" \
        "and .npmrc still sets it"
    log_pass "the window comes from the repo-wide supply-chain setting"
}

log_test "test-actions-release-age"

test_the_shared_lib_is_what_the_gate_uses
test_a_fresh_release_is_deferred
test_an_aged_release_is_eligible
test_a_zero_window_defers_nothing
test_null_policy_is_fail_closed
test_deferrals_are_reported_not_silent
test_total_lookup_failure_is_a_failure_not_a_pass
test_partial_failure_is_deliberately_not_fatal
test_window_source_is_the_shared_npmrc_setting

log_pass "all tests passed"
