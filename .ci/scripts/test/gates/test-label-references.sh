#!/bin/bash
# Tests for .ci/scripts/quality/check-label-references.sh: every label a
# workflow or script references must be declared in labels.yml.
#
# Driven entirely through the gate's env seams (LABEL_REFS_SCAN_DIRS,
# LABEL_REFS_LABELS_FILE, LABEL_REFS_MIN_DISTINCT) against temp fixtures, so
# no tracked file is touched. NOTE this file's planted label strings are
# excluded from the real gate's sweep by basename (GREP_EXCLUDES), which is
# itself asserted here: if that exclusion ever breaks, the real gate would
# demand these fixtures be declared in the real labels.yml.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$SCRIPT_DIR/../../quality/check-label-references.sh"

LAST_OUT=""
run_gate() {
    local root="$1" labels="$2" min="${3:-1}" rc=0
    LAST_OUT="$(LABEL_REFS_SCAN_DIRS="$root" LABEL_REFS_LABELS_FILE="$labels" \
        LABEL_REFS_MIN_DISTINCT="$min" bash "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

# scaffold <dir>: one reference of every consumption shape, all declared.
scaffold() {
    local d="$1"
    mkdir -p "$d/scan"
    cat >"$d/scan/wf.yml" <<'YAML'
    if: contains(github.event.pull_request.labels.*.name, 'fixture-alpha')
    run: gh api -f 'labels[]=fixture-beta'
    run: gh pr list --search "label:fixture-gamma"
    LABEL: ${{ vars.AUTOPILOT_LABEL || 'fixture-delta' }}
YAML
    cat >"$d/scan/tool.cjs" <<'CJS'
if (labels.includes('fixture-epsilon')) {}
const ISSUE_LABEL = 'fixture-zeta';
const ISSUE_LABELS = ['fixture-eta', ISSUE_LABEL];
CJS
    cat >"$d/scan/gate.sh" <<'SH'
LABEL="${AUTOPILOT_LABEL:-fixture-theta}"
jq -e --arg l "fixture-iota" '.labels | index($l)'
echo "$labels" | grep -qx "fixture-kappa"
SH
    cat >"$d/labels.yml" <<'YAML'
- name: fixture-alpha
- name: fixture-beta
- name: fixture-gamma
- name: fixture-delta
- name: fixture-epsilon
- name: fixture-zeta
- name: fixture-eta
- name: fixture-theta
- name: fixture-iota
- name: fixture-kappa
YAML
}

test_all_declared_passes() {
    local d="$1"
    scaffold "$d"
    local rc=0
    run_gate "$d/scan" "$d/labels.yml" 10 || rc=$?
    assert_exit_code 0 "$rc" "every shape declared must pass (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "all 10 code-referenced labels" "counts every consumption shape"
    log_pass "all ten consumption shapes are extracted and pass when declared"
}

test_undeclared_reference_fails() {
    # FIRE: remove one declaration; the gate must name the label AND the file.
    local d="$1"
    scaffold "$d"
    grep -v "fixture-epsilon" "$d/labels.yml" >"$d/labels2.yml"
    local rc=0
    run_gate "$d/scan" "$d/labels2.yml" 9 || rc=$?
    assert_exit_code 1 "$rc" "an undeclared referenced label must fail"
    assert_contains "$LAST_OUT" "fixture-epsilon" "names the undeclared label"
    assert_contains "$LAST_OUT" "tool.cjs" "names the referencing site"
    log_pass "an undeclared reference fails, naming label and site"
}

test_declared_but_unreferenced_is_fine() {
    # Direction check: labels.yml may carry inventory nothing references.
    local d="$1"
    scaffold "$d"
    echo "- name: fixture-unused" >>"$d/labels.yml"
    local rc=0
    run_gate "$d/scan" "$d/labels.yml" 10 || rc=$?
    assert_exit_code 0 "$rc" "a declared-but-unreferenced label is inventory, not an error"
    log_pass "declaration without reference does not fail (one direction only)"
}

test_floor_catches_a_dead_sweep() {
    # Anti-vacuity: a scan surface with almost nothing in it must REFUSE, not
    # report clean -- that is how a wrong SCAN_DIRS would present.
    local d="$1"
    mkdir -p "$d/scan"
    echo "nothing label-shaped here" >"$d/scan/empty.txt"
    echo "- name: whatever" >"$d/labels.yml"
    local rc=0
    run_gate "$d/scan" "$d/labels.yml" 8 || rc=$?
    assert_exit_code 1 "$rc" "a sweep under the floor must refuse"
    assert_contains "$LAST_OUT" "floor" "says the sweep is broken, not clean"
    log_pass "the distinct-labels floor refuses a dead sweep"
}

test_real_tree_is_clean_and_excludes_this_file() {
    # The real invocation must pass on the real tree; that implicitly proves
    # the GREP_EXCLUDES work, because THIS file plants labels (fixture-*)
    # that are not in the real labels.yml.
    local rc=0
    LAST_OUT="$(bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must be clean (output: $LAST_OUT)"
    case "$LAST_OUT" in
        *fixture-alpha*) log_fail "this test's planted labels leaked into the real sweep: the basename exclusion broke" ;;
        *) ;;
    esac
    log_pass "real tree clean; this file's fixtures stay excluded from the sweep"
}

log_test "test-label-references"
with_temp_dir test_all_declared_passes
with_temp_dir test_undeclared_reference_fails
with_temp_dir test_declared_but_unreferenced_is_fine
with_temp_dir test_floor_catches_a_dead_sweep
test_real_tree_is_clean_and_excludes_this_file
echo ""
log_pass "all tests passed"
