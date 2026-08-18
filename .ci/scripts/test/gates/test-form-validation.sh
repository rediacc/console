#!/bin/bash
# Tests for scripts/check-form-validation.ts.
#
# The gate is RED on the real tree today: five of the six forms in packages/www disable
# browser validation without replacing it, or read an input and silently discard it. The
# fix belongs to a later wave, so this test does NOT pin the verdict. It pins:
#
#   1. the gate can FAIL -- both plants (the captcha-only guard, and the silent return)
#      are exercised, AND the one form that gets it right stays clean, which is what keeps
#      the rule from being unreasonable;
#   2. its controls are load-bearing -- mutating the captcha exclusion out flips them red;
#   3. the real scan really ran over a form count above its floor, and refuses an empty
#      tree rather than reporting it clean.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$REPO_ROOT/scripts/check-form-validation.ts"
[ -f "$GATE" ] || log_fail "gate not found: $GATE"

test_selftest_passes_and_plants_both_shapes() {
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" --selftest 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the gate's own controls must pass (output: $out)"
    assert_contains "$out" "PLANT: a captcha guard does not count as input validation" \
        "the captcha-only plant must be exercised -- it is what ContactForm actually has"
    assert_contains "$out" "PLANT: a captcha READ FROM AN INPUT still does not count as input validation" \
        "the reachable form of the captcha rule must be exercised, or CAPTCHA_IDENTS is a rule that cannot fire"
    assert_contains "$out" "PLANT: a value read from an input and silently discarded is reported" \
        "the dead-button plant must be exercised"
    assert_contains "$out" "a noValidate form WITH a field guard that reports an error is clean" \
        "the good form must stay clean, or the rule is asking for the impossible"
    log_pass "both defect shapes and the good-form control are exercised"
}

test_the_control_can_actually_fail() {
    local tmp
    tmp="$(mktemp -d)"
    # BLOCKER: expanding tmp now binds the specific path into the trap so cleanup fires even if the variable is reassigned
    # shellcheck disable=SC2064
    trap "rm -rf '$tmp'" RETURN
    # Accept a captcha guard as validation -- the exact leniency that would let ContactForm
    # pass while an empty submit still reaches the network.
    sed 's/&& !CAPTCHA_IDENTS.test(i)//' "$GATE" >"$tmp/mutant.ts"
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$tmp/mutant.ts" --selftest 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a gate that counts a captcha guard as validation must FAIL its own controls"
    assert_contains "$out" "FAIL  PLANT: a captcha READ FROM AN INPUT" "the mutant must name the control it broke"
    log_pass "accepting a captcha guard as validation flips the gate's controls red"
}

test_real_tree_scan_is_not_vacuous() {
    # Seam-free: the real invocation over the real component tree. This is the line the
    # manifest's BLOCKER names.
    local out rc=0
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" 2>&1)" || rc=$?
    assert_not_contains "$out" "Refusing to run" "the real tree must give the gate enough forms to judge"
    assert_contains "$out" "form(s)" "the verdict must state how many forms it read"
    if [ "$rc" -ne 0 ]; then
        assert_contains "$out" "packages/www" "a finding must name the file it is in"
    fi
    log_pass "the real scan ran over the real forms and reported its coverage (exit $rc)"
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
    assert_exit_code 1 "$rc" "a tree with no forms must be REFUSED, never passed"
    assert_contains "$out" "Refusing to run" "the refusal must say so"
    log_pass "a tree with no forms is refused rather than reported clean"
}

log_test "test-form-validation"
test_selftest_passes_and_plants_both_shapes
test_the_control_can_actually_fail
test_real_tree_scan_is_not_vacuous
test_empty_tree_is_refused
echo ""
log_pass "all tests passed"
