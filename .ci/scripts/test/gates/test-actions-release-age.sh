#!/bin/bash
# Two-directional test for the release-age defer in scripts/check-actions.ts.
#
# WHAT IT FIXES. The actions-freshness gate had no notion of release age, so an
# action published MINUTES earlier turned the build red, and the only ways out
# were to pin a barely-vetted SHA or to blocklist a version that is not blocked
# at all. Measured 2026-07-28: docker/login-action v4.5.2 was published at
# 07:04:43Z and had reddened the gate by 07:21Z, seventeen minutes later.
#
# Taking a release on sight also contradicts this repo's own supply-chain
# posture: .npmrc sets `minimum-release-age=1440`, and the Go and npm gates
# already defer through is_release_deferred. An action pin is the same kind of
# dependency, so it gets the same window.
#
# THE RISK THIS TEST EXISTS FOR. A defer is one line away from being a mute
# button. If the window silently swallowed every finding, the gate would report
# success forever and look exactly like a healthy repo. So the load-bearing
# assertion here is NOT that fresh releases are deferred; it is that an
# unwindowed run still FAILS on the very same input. The defer must be doing one
# specific thing, not disabling the check.
#
# Network: this drives the REAL gate, which queries the GitHub API, because the
# property under test is end-to-end behaviour and a mocked version would prove
# nothing about the shipped script.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A token is REQUIRED, not an optimisation. This file runs the real gate several
# times, and the anonymous GitHub rate limit trips well inside that, which used
# to make every lookup fail. CI passes github.token for the same reason.
GATE_TOKEN="$(gh auth token 2>/dev/null || echo "${GITHUB_TOKEN:-${GH_TOKEN:-}}")"

# run_gate <window-seconds> -> writes output to $WORK/out, returns the exit code
run_gate() {
    local window="$1"
    (cd "$REPO_ROOT" && RELEASE_AGE_WINDOW_SECONDS="$window" GITHUB_TOKEN="$GATE_TOKEN" \
        npx tsx scripts/check-actions.ts) >"$WORK/out" 2>&1
    return $?
}

# Set by the control so the paired assertion can demand the matching deferral
# instead of accepting "nothing fresh upstream", which is exactly how a
# rate-limited run passed for the wrong reason the first time this was written.
CONTROL_FIRED=0

# ---------------------------------------------------------------------------

test_gate_is_reachable_at_all() {
    # Anti-vacuity. Every assertion below reads the gate's output, so a gate that
    # cannot run (no network, rate limit, TS error) would make "no findings" and
    # "cannot tell" indistinguishable. Fail loudly instead of measuring nothing.
    assert_eq "$([ -n "$GATE_TOKEN" ] && echo yes)" "yes" \
        "a GitHub token is available, or every lookup below is rate-limited and proves nothing"
    run_gate 86400
    assert_contains "$(cat "$WORK/out")" "unique action(s)" \
        "the gate actually enumerated actions (network and parsing both work)"
    assert_not_contains "$(cat "$WORK/out")" "Could not resolve the latest release for ANY" \
        "and it resolved at least one release, so its verdict rests on real data"
    log_pass "the gate runs, is authenticated, and enumerates actions"
}

test_total_lookup_failure_is_a_failure_not_a_pass() {
    # THE VACUOUS-PASS FIX. With every lookup rate-limited the gate used to print
    # "All GitHub Actions are up-to-date (14 unknown)" and exit 0: fourteen
    # unknown means fourteen UNCHECKED, which is the opposite of up-to-date. An
    # offline or rate-limited run therefore reported freshness it never verified.
    #
    # Provoked by stripping the token so the run uses the anonymous limit. That
    # is NOT deterministic (the limit may not be exhausted yet), so the else
    # branch pins the guard against the source rather than reporting a pass that
    # measured nothing.
    local rc=0
    (cd "$REPO_ROOT" && RELEASE_AGE_WINDOW_SECONDS=86400 GITHUB_TOKEN='' GH_TOKEN='' \
        npx tsx scripts/check-actions.ts) >"$WORK/vacuous" 2>&1 || rc=$?
    local out
    out="$(cat "$WORK/vacuous")"
    if grep -q "Could not resolve the latest release for ANY" "$WORK/vacuous"; then
        assert_eq "$rc" "1" "a run that resolved nothing must FAIL"
        assert_not_contains "$out" "All GitHub Actions are up-to-date" \
            "and must never claim freshness it did not verify"
        log_pass "a total lookup failure is reported as a failure, not as up-to-date"
    else
        # Not rate-limited yet, so the anonymous path still worked. The behaviour
        # is pinned against the source instead of silently skipped.
        assert_contains "$(cat "$REPO_ROOT/scripts/check-actions.ts")" \
            "unknown.length === actions.size" \
            "the total-failure guard exists even when this run could not trigger it"
        log_pass "could not exhaust the anonymous limit here; guard pinned against the source"
    fi
}

test_zero_window_still_fails_on_a_real_upgrade() {
    # THE CONTROL, and the whole reason this file exists. With the window set to
    # zero nothing can be deferred, so any genuinely outdated action must still
    # fail the gate. If this ever passes, the defer has become a mute button and
    # the gate is no longer checking anything.
    local rc=0
    run_gate 0 || rc=$?
    local out
    out="$(cat "$WORK/out")"

    if [[ "$rc" -eq 0 ]]; then
        # No outdated action exists right now, so the control cannot be exercised
        # from live data. Say so rather than reporting a pass that measured
        # nothing: a silent skip here would hide a broken control indefinitely.
        assert_contains "$out" "up-to-date" \
            "with a zero window and no outdated action, the gate legitimately passes"
        log_pass "control not exercisable right now (no outdated action upstream); state recorded, not hidden"
        return 0
    fi

    assert_contains "$out" "Outdated actions" \
        "with a zero window a real upgrade must FAIL the gate, not be deferred"
    assert_not_contains "$out" "Deferred upgrades" \
        "and nothing may be deferred when the window is zero"
    CONTROL_FIRED=1
    log_pass "control fires: a zero window still fails on a genuinely outdated action"
}

test_default_window_defers_that_same_input() {
    # The other direction, on the SAME upstream state as the control above, which
    # is what makes the pair meaningful rather than two unrelated observations.
    local rc=0
    run_gate 86400 || rc=$?
    local out
    out="$(cat "$WORK/out")"
    assert_eq "$rc" "0" "the 24h window must not fail the gate on a fresh release: $out"

    if [[ "$CONTROL_FIRED" == "1" ]]; then
        # PAIRED with the control on the SAME upstream state: the zero-window run
        # just proved an outdated action exists, so the windowed run MUST defer
        # it. Accepting "nothing fresh upstream" here is what let a rate-limited
        # run pass for the wrong reason when this file was first written.
        assert_contains "$out" "Deferred upgrades" \
            "the control found an outdated action, so the 24h window must DEFER that same one"
        assert_contains "$out" "inside the" "a deferral names the window it fell inside"
        assert_contains "$out" "published " "and names the publish timestamp it judged"
        log_pass "the same upgrade that fails at window=0 is deferred at window=24h"
    else
        log_pass "control did not fire (nothing outdated upstream); the 24h window passes cleanly"
    fi
}

test_deferrals_are_reported_not_silent() {
    # A silent defer is indistinguishable from a gate that stopped looking, which
    # is the failure mode this repo keeps finding in its own tooling. Whatever is
    # held back must be named in the output.
    run_gate 86400
    local out
    out="$(cat "$WORK/out")"
    if grep -q "Deferred upgrades" "$WORK/out"; then
        assert_contains "$out" "become normal findings once the window passes" \
            "the report says the finding is postponed, not dismissed"
        log_pass "deferrals are announced and explicitly temporary"
    else
        log_pass "no deferrals to report in the current upstream state"
    fi
}

test_window_is_the_shared_one() {
    # The number is a policy, not a local preference: it must match .npmrc's
    # minimum-release-age (minutes) and the bash helper's window (seconds).
    local src npmrc
    src="$(cat "$REPO_ROOT/scripts/check-actions.ts")"
    npmrc="$(cat "$REPO_ROOT/.npmrc" 2>/dev/null || echo '')"
    assert_contains "$src" "24 * 60 * 60" "the default window is 24h, spelled out"
    assert_contains "$npmrc" "minimum-release-age=1440" \
        "and .npmrc still enforces the same 1440-minute posture this mirrors"
    log_pass "the defer window matches the repo-wide supply-chain posture (24h)"
}

test_missing_timestamp_fails_closed() {
    # A lookup hiccup must never manufacture a "you must upgrade now" failure.
    # Pinned against the source because the API cannot be made to omit the field
    # on demand.
    local src
    src="$(cat "$REPO_ROOT/scripts/check-actions.ts")"
    assert_contains "$src" "if (!publishedAt) return true" \
        "a missing publish date defers rather than demanding an upgrade"
    assert_contains "$src" "if (Number.isNaN(published)) return true" \
        "an unparseable publish date does the same"
    log_pass "an absent or unparseable timestamp fails closed to deferred"
}

log_test "test-actions-release-age"

test_gate_is_reachable_at_all
test_total_lookup_failure_is_a_failure_not_a_pass
test_zero_window_still_fails_on_a_real_upgrade
test_default_window_defers_that_same_input
test_deferrals_are_reported_not_silent
test_window_is_the_shared_one
test_missing_timestamp_fails_closed

log_pass "all tests passed"
