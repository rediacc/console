#!/bin/bash
# Tests for .ci/scripts/quality/check-autopilot-breakpoint-alignment.sh, the
# gate that holds autopilot.yml's copied debug inputs to breakpoint.yml's
# originals.
#
# THE METHOD IS THE POINT (same doctrine as
# test-autopilot-workflow-invariants.sh): a comparison that has only ever been
# seen to pass is indistinguishable from `true`. So every direction is proven:
# the REAL tree passes, unmutated COPIES of the real files still pass (which is
# what proves the env seams point somewhere real rather than at nothing), and a
# copy with ONE option removed must exit 1 with the pinned diagnostic.
#
# The anti-vacuity cases matter as much as the drift case here: this gate's
# whole failure mode is comparing an empty extraction to an empty extraction
# and calling that alignment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check-autopilot-breakpoint-alignment.sh"
REAL_BP="$REPO_ROOT/.ci/breakpoint/workflow/breakpoint.yml"
REAL_AP="$REPO_ROOT/.github/workflows/autopilot.yml"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

out() { cat "$WORK/out.txt"; }
err() { cat "$WORK/err.txt"; }

# run_gate [bp-file] [ap-file] -> prints exit code; out/err captured apart.
run_gate() {
    local rc=0
    AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE="${1:-$REAL_BP}" \
        AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE="${2:-$REAL_AP}" \
        bash "$GATE" >"$WORK/out.txt" 2>"$WORK/err.txt" || rc=$?
    echo "$rc"
}

# assert_mutated <original> <copy> - a mutation that produced an identical
# file would make the failure case a re-run of the control.
assert_mutated() {
    if diff -q "$1" "$2" >/dev/null 2>&1; then
        log_fail "mutation produced an identical file: $2 (the workflow's shape drifted; fix the mutation)"
    fi
}

fresh_fixtures() { # <dir> - unmutated copies of both real files
    mkdir -p "$1"
    cp "$REAL_BP" "$1/bp.yml"
    cp "$REAL_AP" "$1/ap.yml"
}

test_real_tree_passes() {
    assert_eq "$(run_gate)" "0" "the real breakpoint.yml and autopilot.yml agree"
    assert_contains "$(err)" "autopilot debug inputs match breakpoint" "and the gate says so"
    assert_contains "$(err)" "300" "naming the option list it actually compared"
    log_pass "control: the real tree is aligned"
}

test_unmutated_copies_pass() {
    fresh_fixtures "$WORK/control"
    assert_eq "$(run_gate "$WORK/control/bp.yml" "$WORK/control/ap.yml")" "0" \
        "unmutated copies pass through the env seams"
    log_pass "control: the env seams read the files they are pointed at"
}

test_removed_duration_option_fires() {
    fresh_fixtures "$WORK/drift"
    # Drop the longest hold from breakpoint's ladder. Nothing else changes, so
    # a green here would mean the comparison is not happening at all.
    perl -pi -e "s/, '300'\]/]/ if /^        options: \['5', '10'/" "$WORK/drift/bp.yml"
    assert_mutated "$REAL_BP" "$WORK/drift/bp.yml"
    assert_eq "$(run_gate "$WORK/drift/bp.yml" "$WORK/drift/ap.yml")" "1" \
        "one removed duration option must fail"
    assert_contains "$(err)" "AUTOPILOT/BREAKPOINT DRIFT: hold-duration options differ" \
        "with the drift class named"
    assert_contains "$(err)" "frozen in MANIFEST.sha256" \
        "and the fix direction stated: breakpoint is canonical, autopilot follows"
    log_pass "an option removed on either side is caught, proven by mutation"
}

test_boolean_default_flip_fires() {
    fresh_fixtures "$WORK/boolflip"
    # send-email defaulting to false on one side only: the drift that would
    # print a bearer-credential URL into a public log while the operator
    # believes both tools behave the same.
    perl -0pi -e "s/(      send-email:.*?\n        default: )true/\${1}false/s" "$WORK/boolflip/ap.yml"
    assert_mutated "$REAL_AP" "$WORK/boolflip/ap.yml"
    assert_eq "$(run_gate "$WORK/boolflip/bp.yml" "$WORK/boolflip/ap.yml")" "1" \
        "a flipped send-email default must fail"
    assert_contains "$(err)" "send-email.default differs" "naming the exact field"
    assert_contains "$(err)" "bearer credential" "and why that default is not cosmetic"
    log_pass "type/default drift on the booleans is caught field by field"
}

test_missing_file_fails_closed() {
    assert_eq "$(run_gate "$WORK/never-written.yml")" "1" "a missing breakpoint file must fail"
    assert_contains "$(err)" "nothing to compare cannot pass" "as an anti-vacuity refusal"
    fresh_fixtures "$WORK/half"
    assert_eq "$(run_gate "$WORK/half/bp.yml" "$WORK/also-never-written.yml")" "1" \
        "a missing autopilot file must fail too"
    log_pass "anti-vacuity: a missing side is a failure, never a pass"
}

test_missing_input_block_fails_closed() {
    fresh_fixtures "$WORK/noblock"
    # Rename the autopilot input so the block cannot be found. The gate must
    # refuse rather than compare its value against an empty string.
    perl -pi -e "s/^      hold-duration:/      renamed-duration:/" "$WORK/noblock/ap.yml"
    assert_mutated "$REAL_AP" "$WORK/noblock/ap.yml"
    assert_eq "$(run_gate "$WORK/noblock/bp.yml" "$WORK/noblock/ap.yml")" "1" \
        "a renamed input block must fail"
    assert_contains "$(err)" "could not extract autopilot hold-duration options" \
        "naming what it failed to find"
    assert_contains "$(err)" "refuses to pass blind" "and refusing explicitly"
    log_pass "a lost extraction target is a failure, not an empty-equals-empty pass"
}

test_extractor_floor_fires() {
    fresh_fixtures "$WORK/floor"
    # A two-entry list is the shape a half-broken extractor produces. The
    # floor exists because "" != "" comparisons are not the only vacuous pass:
    # a list of one or two entries would compare fine and mean nothing.
    perl -pi -e "s/^        options: \['5', '10'.*/        options: ['5', '10']/" "$WORK/floor/bp.yml"
    perl -pi -e "s/^        options: \['5', '10'.*/        options: ['5', '10']/" "$WORK/floor/ap.yml"
    assert_mutated "$REAL_BP" "$WORK/floor/bp.yml"
    assert_eq "$(run_gate "$WORK/floor/bp.yml" "$WORK/floor/ap.yml")" "1" \
        "two IDENTICAL but implausibly short lists must still fail"
    assert_contains "$(err)" "fewer than 5 options" "on the floor, not on equality"
    log_pass "the floor catches a broken extractor that equality alone would pass"
}

log_test "test-autopilot-breakpoint-alignment"
test_real_tree_passes
test_unmutated_copies_pass
test_removed_duration_option_fires
test_boolean_default_flip_fires
test_missing_file_fails_closed
test_missing_input_block_fails_closed
test_extractor_floor_fires
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
