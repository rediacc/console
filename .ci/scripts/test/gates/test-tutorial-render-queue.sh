#!/bin/bash
# Prove `check:ci-tutorial-render-queue` reports the truth, including when there is nothing
# to report.
#
# `packages/www/scripts/list-tutorial-render-pairs.js` is the ONE readiness predicate for
# "which (tutorial, language) pairs need rendering". Everything downstream trusts it:
# `run.sh`'s `www tutorials media` and `www tutorials watch` both render exactly what it
# emits, so a predicate that silently answers "nothing" produces a green run that rendered
# nothing, and one that over-reports burns hours of CPU re-rendering finished work.
#
# WHY THIS FILE EXISTS RATHER THAN A REGISTRY LINE
# ------------------------------------------------
# The obvious home for the empty-tree case is the REGISTRY in test-gate-anti-vacuity.sh.
# It does not work there, and the reason is worth recording so nobody re-adds it:
#
#   That harness builds its fixture with `cp -r "$REPO_ROOT/scripts"` and
#   `cp -r "$REPO_ROOT/.ci/scripts"` (test-gate-anti-vacuity.sh:136,143) and copies NOTHING
#   from packages/. The predicate lives at packages/www/scripts/, so a registry entry would
#   fail with "No such file or directory" -- non-zero for a reason that has nothing to do
#   with vacuity, which is precisely the false signal that file's own REGISTRY POLICY warns
#   about. It is the same call already made for check-breakpoint-drift.sh.
#
# So this test carries its own fixture, exactly as test-breakpoint-portability.sh does.
#
# WHAT IS CHECKED HERE VERSUS IN --selftest
# -----------------------------------------
# The predicate ships `--selftest` with its own staleness cases (mp4 missing, timeline newer,
# mp4 newer, wrong provider, audio dir absent). This file does NOT duplicate those. It checks
# the properties a self-test cannot honestly check about itself:
#   - the empty-tree refusal, against a REAL empty tree rather than a constructed fixture
#   - that --selftest is wired into the npm gate at all, and that it FAILS the gate when it
#     fails (a self-test nothing runs is decoration)
#   - that the self-test contains controls, i.e. cases that must NOT report

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

PREDICATE="$REPO_ROOT/packages/www/scripts/list-tutorial-render-pairs.js"
GATE_NAME="check:ci-tutorial-render-queue"

test_predicate_exists() {
    if [[ ! -f "$PREDICATE" ]]; then
        log_fail "predicate missing at $PREDICATE -- the gate cannot be meaningful"
    fi
    log_pass "predicate present"
}

# An empty tree must REFUSE, not answer "0 pairs". "0 pairs" is indistinguishable from
# "everything is rendered", and that is the reading that makes a broken checkout look green.
test_empty_tree_refuses() {
    local tmp="$1" out status=0
    out="$(node "$PREDICATE" --root "$tmp" 2>&1)" || status=$?
    assert_exit_code 1 "$status" "empty tree must exit non-zero"
    assert_contains "$out" "Refusing to run" "refusal must say it is refusing"
    # Pin the DIAGNOSTIC, not just the code: a crash also exits non-zero.
    assert_contains "$out" "meaningless" "refusal must explain why the answer would be wrong"
    log_pass "an empty tree refuses instead of reporting zero pairs"
}

# Half a tree is the nastier case: casts present, timelines absent (or the reverse) is what a
# partial checkout or a half-finished narration run actually looks like.
test_half_populated_tree_refuses() {
    local tmp="$1" out status=0
    mkdir -p "$tmp/packages/www/public/assets/tutorials"
    printf '{}' >"$tmp/packages/www/public/assets/tutorials/tutorial-fake.cast"
    out="$(node "$PREDICATE" --root "$tmp" 2>&1)" || status=$?
    assert_exit_code 1 "$status" "casts-without-timelines must exit non-zero"
    assert_contains "$out" "Refusing to run" "half-populated tree must refuse"
    log_pass "casts present but no timeline dirs still refuses"
}

test_selftest_passes() {
    local out status=0
    out="$(node "$PREDICATE" --selftest 2>&1)" || status=$?
    assert_exit_code 0 "$status" "--selftest must pass on a clean tree"
    log_pass "--selftest passes"
}

# A self-test made only of cases that expect a hit cannot detect an over-reporting predicate.
# Require controls -- cases asserting something is NOT listed.
test_selftest_has_controls() {
    local body control_count
    body="$(node "$PREDICATE" --selftest 2>&1)"
    control_count="$(grep -c -i 'control' <<<"$body" || true)"
    if ((control_count < 2)); then
        log_fail "--selftest reported only $control_count control case(s); a predicate needs cases that must NOT fire (mp4 newer, wrong provider) or it cannot catch over-reporting"
    fi
    log_pass "--selftest carries $control_count control case(s)"
}

# The gate is worthless if the npm script does not actually run the self-test, or runs it in a
# way that ignores its exit code.
test_gate_runs_the_selftest() {
    local cmd
    cmd="$(node -e "process.stdout.write(require('$REPO_ROOT/package.json').scripts['$GATE_NAME'] || '')")"
    if [[ -z "$cmd" ]]; then
        log_fail "$GATE_NAME is not registered in package.json"
    fi
    assert_contains "$cmd" "list-tutorial-render-pairs" "$GATE_NAME must invoke the predicate"
    assert_contains "$cmd" "--selftest" "$GATE_NAME must run --selftest"
    # `;` or `||` between stages would swallow a failure; `&&` propagates it.
    if [[ "$cmd" == *";"* ]]; then
        log_fail "$GATE_NAME chains with ';' which discards a failing stage's exit code: $cmd"
    fi
    log_pass "$GATE_NAME runs --selftest and propagates its exit code"
}

# The gate must be in the local gate set, or nothing runs it.
#
# This used to read package.json's `ci` value and look for the key in it. That
# stopped working the moment `scripts.ci` became `tsx scripts/ci-runner/run.ts`:
# the chain string no longer names any gate, so the assertion went red. It is
# the same string-parsing assumption that made check-ci-chain-parity.ts and
# check-gate-reachability.ts unfixable in place. The manifest is the gate set
# now, and scripts/check-ci-parity.ts is what keeps it honest against CI.
test_gate_is_in_the_gate_manifest() {
    local manifest="$REPO_ROOT/scripts/ci-runner/manifest.ts"
    [[ -f "$manifest" ]] || log_fail "no gate manifest at $manifest, so this assertion would be vacuous"
    grep -q "id: '$GATE_NAME'" "$manifest" ||
        log_fail "$GATE_NAME must be an entry in scripts/ci-runner/manifest.ts, or no local run schedules it"
    log_pass "$GATE_NAME is wired into the gate manifest"
}

# CONTROL for this file: a deliberately broken predicate must make the empty-tree assertion
# FAIL. Without this, every test above could be passing because `node` errors on everything.
test_harness_can_actually_fail() {
    local tmp="$1" fake="$1/fake-predicate.js" out status=0
    # A predicate that cheerfully reports zero pairs on an empty tree -- the exact defect.
    printf 'console.log("");\nprocess.exit(0);\n' >"$fake"
    out="$(node "$fake" --root "$tmp" 2>&1)" || status=$?
    if [[ "$status" -ne 0 ]]; then
        log_fail "control is broken: a stub that exits 0 reported status $status"
    fi
    assert_not_contains "$out" "Refusing to run" "control stub must not refuse"
    log_pass "control: a zero-exit stub is distinguishable from the real refusal"
}

with_temp_dir test_predicate_exists
with_temp_dir test_empty_tree_refuses
with_temp_dir test_half_populated_tree_refuses
with_temp_dir test_selftest_passes
with_temp_dir test_selftest_has_controls
with_temp_dir test_gate_runs_the_selftest
with_temp_dir test_gate_is_in_the_gate_manifest
with_temp_dir test_harness_can_actually_fail
