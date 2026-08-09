#!/bin/bash
# Tests for .ci/scripts/security/check-autopilot-workflow-invariants.sh, the
# static gate over .github/workflows/autopilot.yml.
#
# THE METHOD IS THE POINT: a static grep that has never been shown to FAIL is
# indistinguishable from `true` (this repo shipped exactly that shape in a
# --selftest nothing invoked). So every invariant is proven in both
# directions: the REAL workflow passes, and a MUTATED copy of the real
# workflow with that one invariant broken must exit 1 with the pinned
# diagnostic. Mutating the live file (rather than a frozen fixture) keeps the
# proofs from rotting as the workflow evolves: if the workflow's shape drifts
# so far that a mutation stops landing, the mutation's own assertion fails
# loudly instead of the test silently testing nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/security/check-autopilot-workflow-invariants.sh"
REAL="$REPO_ROOT/.github/workflows/autopilot.yml"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

out() { cat "$WORK/out.txt"; }
err() { cat "$WORK/err.txt"; }

# run_gate <workflow-file> -> prints exit code; out/err captured separately.
run_gate() {
    local rc=0
    WORKFLOW_FILE="$1" bash "$GATE" >"$WORK/out.txt" 2>"$WORK/err.txt" || rc=$?
    echo "$rc"
}

# assert_mutated <fixture> — the mutation must actually differ from the real
# file, or the "failure" test below would be re-running the control.
assert_mutated() {
    if diff -q "$REAL" "$1" >/dev/null 2>&1; then
        log_fail "mutation produced an identical file: $1 (the workflow's shape drifted; fix the mutation)"
    fi
}

test_real_workflow_passes() {
    assert_eq "$(run_gate "$REAL")" "0" "the real autopilot.yml satisfies every invariant"
    assert_contains "$(err)" "invariants hold" "and says so (common.sh log_info writes to stderr)"
    assert_contains "$(err)" "5 jobs scanned" "across all five jobs (gate, model, finish, escalate, sweeper)"
    log_pass "control: the real workflow passes the gate"
}

test_missing_workflow_fails_closed() {
    assert_eq "$(run_gate "$WORK/never-written.yml")" "1" "a missing workflow must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: workflow-missing" "as workflow-missing (a blind gate cannot pass)"
    log_pass "anti-vacuity: nothing to check is a failure, not a pass"
}

test_wall4_comment_is_required() {
    grep -v 'WALL 4' "$REAL" >"$WORK/no-wall4.yml"
    assert_mutated "$WORK/no-wall4.yml"
    assert_eq "$(run_gate "$WORK/no-wall4.yml")" "1" "stripping the WALL 4 comments must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: wall4-comment-missing" "as wall4-comment-missing"
    log_pass "the trusted checkout must stay explained at the point of use"
}

test_event_interpolation_in_run_fails() {
    # Plant a payload interpolation inside the first run: block. env:-passed
    # payload values are fine; ${{ github.event.* }} inside shell is the
    # injection surface the review pipeline's zero-interpolation rule closed.
    perl -pe '$_ .= qq{            echo "\${{ github.event.pull_request.title }}"\n} if /^\s+run: \|$/ && ++$c == 1' \
        "$REAL" >"$WORK/inject.yml"
    assert_mutated "$WORK/inject.yml"
    assert_eq "$(run_gate "$WORK/inject.yml")" "1" "payload interpolation in a run block must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: event-interpolation-in-run" "as event-interpolation-in-run"
    # CONTROL for the parser's scoping: the real file DOES use github.event.*
    # in if:/env:/concurrency (that is the sanctioned route), and the control
    # test above already proves those do not fire.
    grep -q 'github\.event\.workflow_run\.head_branch' "$REAL" ||
        log_fail "expected the real workflow to use github.event.* outside run blocks"
    log_pass "github.event.* is banned inside run blocks and only there"
}

test_token_before_model_fails() {
    perl -pe 'print qq{      - name: Premature token\n        uses: ./.github/actions/app-token\n} if /^      - name: Model round$/' \
        "$REAL" >"$WORK/pre-token.yml"
    assert_mutated "$WORK/pre-token.yml"
    assert_eq "$(run_gate "$WORK/pre-token.yml")" "1" "an app-token step before the model step must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: token-before-model" "as token-before-model (invariant 1: the model never holds a write token)"
    log_pass "a write token minted at or before the model step is structurally impossible"
}

test_token_in_gate_fails() {
    perl -pe 'print qq{      - name: Gate token\n        uses: ./.github/actions/app-token\n} if /^      - name: Locate the armed PR$/' \
        "$REAL" >"$WORK/gate-token.yml"
    assert_mutated "$WORK/gate-token.yml"
    assert_eq "$(run_gate "$WORK/gate-token.yml")" "1" "an app-token step in the gate job must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: token-in-gate" "as token-in-gate (the gate decides with zero write capability)"
    log_pass "the gate job can never mint a token"
}

test_persisted_credentials_fail() {
    perl -pe '$done ||= s/persist-credentials: false/persist-credentials: true/ unless $done' \
        "$REAL" >"$WORK/persist.yml"
    assert_mutated "$WORK/persist.yml"
    assert_eq "$(run_gate "$WORK/persist.yml")" "1" "a persisting checkout must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: persist-credentials" "as persist-credentials"
    log_pass "every checkout must refuse to persist a bearer token into the workspace"
}

test_untrusted_first_checkout_fails() {
    perl -pe '$done ||= s/^(\s+)ref: main$/$1ref: pr-authored-branch/ unless $done' \
        "$REAL" >"$WORK/untrusted.yml"
    assert_mutated "$WORK/untrusted.yml"
    assert_eq "$(run_gate "$WORK/untrusted.yml")" "1" "a first checkout off the trusted ref must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: trusted-checkout-not-first" "as trusted-checkout-not-first (wall 4)"
    log_pass "the first checkout of every job is pinned to rediacc/console @ main"
}

test_track_progress_armed_fails() {
    perl -pe "s/track_progress: 'false'/track_progress: 'true'/" "$REAL" >"$WORK/track.yml"
    assert_mutated "$WORK/track.yml"
    assert_eq "$(run_gate "$WORK/track.yml")" "1" "arming track_progress must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: track-progress-armed" "as track-progress-armed (its tag-mode fetch is the credentialed path)"
    log_pass "track_progress stays the literal 'false'"
}

test_cancel_in_progress_armed_fails() {
    perl -pe 's/cancel-in-progress: false/cancel-in-progress: true/' "$REAL" >"$WORK/cancel.yml"
    assert_mutated "$WORK/cancel.yml"
    assert_eq "$(run_gate "$WORK/cancel.yml")" "1" "cancel-in-progress: true must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: cancel-in-progress-armed" "as cancel-in-progress-armed (never kill a round mid-push)"
    log_pass "concurrency can queue rounds but never cancel one mid-push"
}

test_model_without_state_guard_fails() {
    # The model job's if: must require AUTOPILOT_ALLOW_STATE. Strip ONLY that
    # clause: the state-write step further down still mentions the flag, so a
    # checker that greps the whole file would pass this mutation -- which is
    # exactly the substitute this invariant must refuse.
    perl -0pe "s/      vars\.AUTOPILOT_ALLOW_MODEL == 'true' &&\n      vars\.AUTOPILOT_ALLOW_STATE == 'true'\n/      vars.AUTOPILOT_ALLOW_MODEL == 'true'\n/" \
        "$REAL" >"$WORK/nostate.yml"
    assert_mutated "$WORK/nostate.yml"
    grep -q 'AUTOPILOT_ALLOW_STATE' "$WORK/nostate.yml" ||
        log_fail "the mutation removed every mention of the flag; it must survive elsewhere or this proves nothing"
    assert_eq "$(run_gate "$WORK/nostate.yml")" "1" "a model job that can run without the state flag must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: model-without-state-guard" \
        "as model-without-state-guard (a round that cannot record itself breaks the round counter)"
    log_pass "the model job is structurally unable to run while state writes are disarmed"
}

test_unparsed_model_if_fails_closed() {
    # Anti-vacuity for the invariant above: if the model job's if: cannot be
    # found at all, the check verified nothing and must say so rather than
    # pass. Renaming the job is the cheapest way to make it unfindable.
    perl -pe 's/^  model:$/  modelx:/' "$REAL" >"$WORK/nomodeljob.yml"
    assert_mutated "$WORK/nomodeljob.yml"
    assert_eq "$(run_gate "$WORK/nomodeljob.yml")" "1" "an unfindable model if: must fail"
    assert_contains "$(err)" "an unparsed guard cannot pass" "naming the anti-vacuity reason"
    log_pass "anti-vacuity: an invariant that cannot locate its subject fails closed"
}

test_submodule_checkout_before_model_fails() {
    # S6 makes submodule PUSHES possible after the model exits. The tempting
    # follow-on is to let the model EDIT submodules by adding submodules: to
    # its checkout -- but the four submodules are private, so that fetch needs
    # a credential, and a credential before the model step is the one thing
    # this design exists to prevent.
    perl -pe '$_ .= "          submodules: recursive\n" if /^          filter: blob:none$/' \
        "$REAL" >"$WORK/sub-checkout.yml"
    assert_mutated "$WORK/sub-checkout.yml"
    assert_eq "$(run_gate "$WORK/sub-checkout.yml")" "1" "a submodule-fetching checkout before the model must fail"
    assert_contains "$(err)" "INVARIANT-FAIL: submodule-checkout-pre-model" "as submodule-checkout-pre-model"
    assert_contains "$(err)" "(model)" "attributed to the model job"
    # CONTROL 1: an explicit `submodules: false` is the harmless spelling and
    # must not fire, or the rule would ban writing the safe thing down.
    perl -pe '$_ .= "          submodules: false\n" if /^          filter: blob:none$/' \
        "$REAL" >"$WORK/sub-false.yml"
    assert_mutated "$WORK/sub-false.yml"
    assert_eq "$(run_gate "$WORK/sub-false.yml")" "0" "an explicit submodules: false is fine"
    # CONTROL 2: the rule is about POSITION, not about the word. The finish job
    # runs no model, so a submodule checkout there is not a pre-model
    # credential and must pass.
    perl -pe '$_ .= "          submodules: recursive\n" if /^          ref: main$/ && ++$c == 3' \
        "$REAL" >"$WORK/sub-finish.yml"
    assert_mutated "$WORK/sub-finish.yml"
    assert_eq "$(run_gate "$WORK/sub-finish.yml")" "0" "a submodule checkout in a modelless job is not a pre-model credential"
    log_pass "submodules may be fetched after the model exits, never before it"
}

log_test "test-autopilot-workflow-invariants"
test_real_workflow_passes
test_missing_workflow_fails_closed
test_wall4_comment_is_required
test_event_interpolation_in_run_fails
test_token_before_model_fails
test_token_in_gate_fails
test_persisted_credentials_fail
test_untrusted_first_checkout_fails
test_track_progress_armed_fails
test_cancel_in_progress_armed_fails
test_model_without_state_guard_fails
test_unparsed_model_if_fails_closed
test_submodule_checkout_before_model_fails
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
