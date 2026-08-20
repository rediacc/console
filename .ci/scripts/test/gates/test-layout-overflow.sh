#!/bin/bash
# Tests for scripts/check-layout-overflow.ts.
#
# WHY THIS FILE EXISTS AND WHAT IT MAY AND MAY NOT ASSERT.
# The gate is RED on the real tree today, deliberately: four CSS rules make this site
# scroll sideways and the fix belongs to a later wave. So this test must NOT pin the
# verdict -- an assertion of `exit 1` would go red the day the bug is fixed, which is
# exactly backwards. What it pins instead is everything that makes the verdict MEAN
# something:
#
#   1. the gate can FAIL -- its inline controls plant both cause shapes and require
#      detection, including the pseudo-element one that no browser-driven scan can see;
#   2. the gate really SCANNED -- the run reports a declaration-block count above its
#      floor rather than reporting on an empty glob;
#   3. the gate REFUSES an empty tree instead of printing a checkmark over nothing.
#
# Together those three are what separate "this gate is red" from "this gate is noise",
# and they hold whether the tree is red or green.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$REPO_ROOT/scripts/check-layout-overflow.ts"
[ -f "$GATE" ] || log_fail "gate not found: $GATE"

test_selftest_passes_and_plants_both_shapes() {
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" --selftest 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the gate's own controls must pass (output: $out)"
    assert_contains "$out" "PLANT: \`left: -9999px\` offscreen hiding is reported" \
        "the RTL offscreen plant must be exercised"
    assert_contains "$out" "PLANT: an invisible nowrap PSEUDO-ELEMENT is reported" \
        "the pseudo-element plant must be exercised -- this is the shape querySelectorAll cannot see"
    log_pass "both cause shapes are planted and detected"
}

test_the_control_can_actually_fail() {
    # MUTATE THE GATE, not the tree: strip the pseudo-element rule and require the
    # gate to declare itself broken. Without this the PASS lines above prove only that
    # a string was printed.
    # The mutant is written BESIDE the gate, not into a temp dir. The gate imports
    # ./lib/shrink-only-baseline.ts by relative path, and a copy in /tmp cannot resolve
    # that: the run dies on "Cannot find module" before any control executes, and the
    # assertion below then fails for the wrong reason. It reads as "the controls are not
    # load-bearing" when in fact the gate never started. Same directory, same relative
    # imports, so the mutant differs from the gate only in the mutation.
    local mutant
    mutant="$(dirname "$GATE")/.mutant-layout-overflow.ts"
    # BLOCKER: expanding mutant now binds the specific path into the trap so cleanup fires even if the variable is reassigned
    # shellcheck disable=SC2064
    trap "rm -f '$mutant'" RETURN
    sed "s/d.get('white-space') === 'nowrap' &&/false \&\&/" "$GATE" >"$mutant"
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$mutant" --selftest 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a gate that stopped detecting the nowrap shape must FAIL its own controls"
    assert_contains "$out" "FAIL" "the mutant must name the failing control"
    log_pass "removing the detector flips the gate's controls red (the controls are load-bearing)"
}

test_real_tree_scan_is_not_vacuous() {
    # Seam-free: the real invocation over the real tree. This is the line the manifest's
    # BLOCKER names. The VERDICT is deliberately not asserted (the tree is red by design
    # until the overflow fix lands); what is asserted is that a real scan happened.
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" 2>&1)" || rc=$?
    assert_not_contains "$out" "Refusing to run" "the real tree must give the gate enough input to judge"
    if [ "$rc" -eq 0 ]; then
        assert_contains "$out" "declaration block(s)" "a green verdict must state how many blocks it read"
    else
        assert_contains "$out" "declaration block(s)" "a red verdict must state how many blocks it read"
        assert_contains "$out" "packages/www" "a finding must name the file it is in"
    fi
    log_pass "the real scan ran over the real stylesheets and reported its coverage (exit $rc)"
}

test_empty_tree_is_refused() {
    local tmp
    tmp="$(mktemp -d)"
    # BLOCKER: expanding tmp now binds the specific path into the trap so cleanup fires even if the variable is reassigned
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" RETURN
    mkdir -p "$tmp/packages/www/src/styles"
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" --root "$tmp" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a tree with no stylesheets must be REFUSED, never passed"
    assert_contains "$out" "Refusing to run" "the refusal must say so"
    log_pass "an empty style tree is refused rather than reported clean"
}

log_test "test-layout-overflow"
test_selftest_passes_and_plants_both_shapes
test_the_control_can_actually_fail
test_real_tree_scan_is_not_vacuous
test_empty_tree_is_refused
echo ""
log_pass "all tests passed"
