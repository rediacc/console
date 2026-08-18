#!/bin/bash
# Tests for scripts/check-hydration-clean.ts.
#
# The gate is RED on the real tree today: four React islands compute a different initial
# state on the server than in the browser, so React discards their server-rendered trees.
# The fix belongs to a later wave, so this test does NOT pin the verdict -- pinning `exit 1`
# would turn the gate red the day the bug is fixed. It pins the three properties that make
# the verdict worth reading:
#
#   1. the gate can FAIL -- its inline controls plant the InstallMethods shape AND the
#      indirect ThemeToggle shape, and require both to be reported;
#   2. its controls are load-bearing -- mutating the detector out flips them red;
#   3. the real scan really ran, over a component count above its floor, and refuses an
#      empty tree rather than reporting it clean.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$REPO_ROOT/scripts/check-hydration-clean.ts"
[ -f "$GATE" ] || log_fail "gate not found: $GATE"

test_selftest_passes_and_plants_both_shapes() {
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" --selftest 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the gate's own controls must pass (output: $out)"
    assert_contains "$out" "a \`typeof window\` branch in a useState initializer is reported" \
        "the direct plant must be exercised"
    assert_contains "$out" "a bare function reference whose body tests the environment is reported" \
        "the ONE-HOP plant must be exercised -- without it the gate finds one defect instead of four"
    assert_contains "$out" "an SSR guard inside useEffect is NOT reported" \
        "the false-positive control must be exercised, or the gate would flag every SSR guard"
    log_pass "both defect shapes and the false-positive controls are exercised"
}

test_the_control_can_actually_fail() {
    local tmp
    tmp="$(mktemp -d)"
    # BLOCKER: expanding tmp now binds the specific path into the trap so cleanup fires even if the variable is reassigned
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" RETURN
    # Blind the one-hop lookup: the indirect control must go red while the direct one stays green.
    sed 's/const body = bodies.get(ident);/const body = undefined;/' "$GATE" >"$tmp/mutant.ts"
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$tmp/mutant.ts" --selftest 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a gate that stopped following the one hop must FAIL its own controls"
    assert_contains "$out" "FAIL  a bare function reference" "the mutant must name the control it broke"
    log_pass "blinding the one-hop lookup flips the gate's controls red"
}

test_real_tree_scan_is_not_vacuous() {
    # Seam-free: the real invocation over the real component tree. This is the line the
    # manifest's BLOCKER names.
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" 2>&1)" || rc=$?
    assert_not_contains "$out" "Refusing to run" "the real tree must give the gate enough input to judge"
    assert_contains "$out" "component(s)" "the verdict must state how many components it read"
    if [ "$rc" -ne 0 ]; then
        assert_contains "$out" "packages/www" "a finding must name the file it is in"
    fi
    log_pass "the real scan ran over the real components and reported its coverage (exit $rc)"
}

test_empty_tree_is_refused() {
    local tmp
    tmp="$(mktemp -d)"
    # BLOCKER: expanding tmp now binds the specific path into the trap so cleanup fires even if the variable is reassigned
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" RETURN
    mkdir -p "$tmp/packages/www/src"
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" --root "$tmp" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a tree with no components must be REFUSED, never passed"
    assert_contains "$out" "Refusing to run" "the refusal must say so"
    log_pass "an empty component tree is refused rather than reported clean"
}

log_test "test-hydration-clean"
test_selftest_passes_and_plants_both_shapes
test_the_control_can_actually_fail
test_real_tree_scan_is_not_vacuous
test_empty_tree_is_refused
echo ""
log_pass "all tests passed"
