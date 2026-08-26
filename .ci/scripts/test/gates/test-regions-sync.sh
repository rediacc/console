#!/bin/bash
# check-regions-sync.sh must actually refuse a divergence.
#
# WHY THE GATE EXISTS, restated so this file stands alone: `data.json` is the
# region list the CLI ships with, and `region-discovery.ts` fetches
# `${SITE_URL}/regions.json`, which returns 404 (measured 2026-08-26). So the
# "fallback" is the only list anyone gets, and `index.ts` claimed a build
# process kept it in step with the root `regions.json` when nothing did.
#
# THE FAILURE THIS TEST GUARDS is not "the files differ" -- it is a comparison
# that cannot fail. Two empty files compare equal; so do two invalid ones if the
# parse errors are swallowed. Each refusal below is planted and observed.
#
# HERMETIC: every case runs against mktemp fixtures via the gate's own
# REGIONS_ROOT_FILE / REGIONS_BAKED_FILE seams, so this never edits the real
# tree and cannot race another session's checkout.
#
# WHAT THIS CANNOT SEE: whether either file's CONTENT is right, and whether the
# live endpoint serves anything. Both are outside the gate's claim.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/.ci/scripts/quality/check-regions-sync.sh"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

GOOD='{"regions":[{"id":"eu","label":"Europe","domain":"eu.example"},{"id":"us","label":"US","domain":"us.example"}]}'

run_gate() { # run_gate <root-file> <baked-file>
    (cd "$REPO_ROOT" && REGIONS_ROOT_FILE="$1" REGIONS_BAKED_FILE="$2" bash "$SUT" >/dev/null 2>&1)
}

test_identical_files_pass() {
    log_test "two identical lists must PASS"
    printf '%s' "$GOOD" >"$WORK/a.json"
    printf '%s' "$GOOD" >"$WORK/b.json"
    run_gate "$WORK/a.json" "$WORK/b.json" ||
        log_fail "identical files were rejected; every refusal below would then be trivially satisfied"
    log_pass "identical lists pass"
}

test_formatting_alone_is_not_drift() {
    log_test "different FORMATTING of the same data must not fail"
    # Byte comparison would fail here, and failing on whitespace trains people to
    # reformat rather than to reconcile.
    printf '%s' "$GOOD" >"$WORK/a.json"
    python3 -c "
import json,sys
json.dump(json.load(open(sys.argv[1])), open(sys.argv[2],'w'), indent=4, sort_keys=True)
" "$WORK/a.json" "$WORK/pretty.json"
    run_gate "$WORK/a.json" "$WORK/pretty.json" ||
        log_fail "reformatted-but-equal JSON was reported as drift"
    log_pass "formatting differences are not drift"
}

test_a_real_divergence_is_caught() {
    log_test "an actual divergence must FAIL"
    printf '%s' "$GOOD" >"$WORK/a.json"
    python3 -c "
import json,sys
d=json.load(open(sys.argv[1])); d['regions'].append({'id':'planted','label':'p','domain':'p'})
json.dump(d, open(sys.argv[2],'w'))
" "$WORK/a.json" "$WORK/drift.json"
    if run_gate "$WORK/a.json" "$WORK/drift.json"; then
        log_fail "a divergent baked list PASSED -- a stale copy would ship to every install"
    fi
    log_pass "a real divergence is caught"
}

test_two_empty_files_do_not_compare_equal() {
    log_test "ANTI-VACUITY: two empty files must not pass by comparing equal"
    : >"$WORK/e1.json"
    : >"$WORK/e2.json"
    if run_gate "$WORK/e1.json" "$WORK/e2.json"; then
        log_fail "two EMPTY files passed; equality over nothing is the vacuous pass this guards"
    fi
    log_pass "empty files are refused, not compared"
}

test_invalid_json_fails_rather_than_passing() {
    log_test "unparseable JSON must FAIL, not be swallowed"
    printf '%s' "$GOOD" >"$WORK/a.json"
    printf 'not json at all' >"$WORK/bad.json"
    if run_gate "$WORK/a.json" "$WORK/bad.json"; then
        log_fail "invalid JSON passed; a comparison that could not parse is not a match"
    fi
    log_pass "invalid JSON is refused"
}

test_missing_file_is_not_a_clean_tree() {
    log_test "a missing file must FAIL, not read as nothing-to-compare"
    printf '%s' "$GOOD" >"$WORK/a.json"
    if run_gate "$WORK/a.json" "$WORK/does-not-exist.json"; then
        log_fail "a missing baked list passed; 'nothing to compare' must never be a pass"
    fi
    log_pass "a missing file is refused"
}

test_the_live_tree_agrees() {
    log_test "the REAL regions.json and data.json agree right now"
    # Over-fire guard, and the reason the gate is worth running at all: if these
    # two ever drift, CI says so instead of shipping a stale list.
    (cd "$REPO_ROOT" && bash "$SUT" >/dev/null 2>&1) ||
        log_fail "the live tree's two region lists have diverged; reconcile them"
    log_pass "the live tree's two lists agree"
}

test_identical_files_pass
test_formatting_alone_is_not_drift
test_a_real_divergence_is_caught
test_two_empty_files_do_not_compare_equal
test_invalid_json_fails_rather_than_passing
test_missing_file_is_not_a_clean_tree
test_the_live_tree_agrees

echo
log_pass "regions-sync gate: 7/7"
echo "  Blind spot: proves the two copies match and that the gate can refuse;"
echo "  says nothing about whether either list is CORRECT, nor whether"
echo "  \${SITE_URL}/regions.json serves anything (it 404s today)."
