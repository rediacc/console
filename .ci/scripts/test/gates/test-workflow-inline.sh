#!/bin/bash
# Both-ways test for the inline-run rule in .ci/scripts/quality/check-workflows.sh.
#
# The rule keeps CI step LOGIC out of workflow YAML: a `run:` block scalar whose
# shell logic exceeds INLINE_MAX_LOGIC (8) non-blank/non-comment lines is a
# violation. There is no baseline and no per-file exemption. A gate like this
# fails in BOTH directions, so both are asserted:
#
#   - Too quiet: an over-threshold block slips through and the workflow accretes
#     un-shared shell logic, or the whole rule goes blind because the workflow
#     directory moved.
#   - Too loud: it miscounts (comments, blank lines, the step's own YAML keys)
#     and reds a file that already complies.
#
# HISTORY, because it is the point of test_no_baseline_escape_hatch: the rule
# used to be a ratchet over .ci/quality/workflow-inline-baseline.json, which
# grandfathered 52 legacy blocks. All 52 were extracted and both the file and the
# ratchet logic were deleted. If someone reintroduces a baseline the rule stops
# holding, so that case pins its absence rather than trusting the reviewer.
#
# The rule is driven in isolation via WORKFLOW_INLINE_ONLY=1 + WORKFLOW_DIR
# pointed at fixtures, so the test never depends on the real .github/workflows
# census.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

CHECK="$REPO_ROOT/.ci/scripts/quality/check-workflows.sh"

LAST_OUT=""

# run_check <workflow-dir>
# Runs ONLY the inline-run rule against the fixture tree; captures output + rc.
run_check() {
    local dir="$1" rc=0
    LAST_OUT="$(WORKFLOW_INLINE_ONLY=1 WORKFLOW_DIR="$dir" \
        bash "$CHECK" 2>&1)" || rc=$?
    return "$rc"
}

# write_workflow <path> <num-violating-blocks> [logic-lines-per-block]
# Emits a valid workflow with <n> over-threshold run: blocks (9 logic lines each
# by default) plus one always-clean thin block (2 lines) to prove thin blocks
# never count.
write_workflow() {
    local path="$1" n="$2" lines="${3:-9}" i j
    {
        echo "name: fixture"
        echo "on: push"
        echo "jobs:"
        echo "  job:"
        echo "    runs-on: ubuntu-latest"
        echo "    steps:"
        for ((i = 1; i <= n; i++)); do
            echo "      - name: Violating $i"
            echo "        run: |"
            for ((j = 1; j <= lines; j++)); do
                echo "          echo line$j"
            done
        done
        echo "      - name: Thin"
        echo "        run: |"
        echo "          echo hi"
        echo "          bash .ci/scripts/quality/x.sh"
    } >"$path"
}

# ---------------------------------------------------------------------------

test_thin_blocks_never_count() {
    # A file that is ALL thin blocks (0 violations) passes.
    local d="$1"
    write_workflow "$d/clean.yml" 0

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "a file with only thin run: blocks must pass"
    log_pass "thin (<=8 line) run: blocks never count as violations"
}

test_fails_any_over_threshold_block() {
    # The core of the rule after the baseline was deleted: ONE fat block anywhere
    # fails, with no way to declare it acceptable.
    local d="$1"
    write_workflow "$d/newbie.yml" 1

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "any file with inline logic must fail"
    assert_contains "$LAST_OUT" "newbie.yml" "names the offending file"
    assert_contains "$LAST_OUT" "1 inline run: block(s) exceed 8" "reports the count and the threshold"
    assert_contains "$LAST_OUT" "extract each over-threshold block to .ci/scripts" "prints the teaching remedy"
    log_pass "a single over-threshold block fails, no exceptions"
}

test_reports_line_and_step_name() {
    # A gate that says "this file is bad" without saying WHERE costs the author a
    # manual hunt through a 600-line workflow.
    local d="$1"
    write_workflow "$d/located.yml" 1

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "over-threshold block must fail"
    assert_contains "$LAST_OUT" "located.yml:8" "cites file:line of the run: block"
    assert_contains "$LAST_OUT" "step: Violating 1" "names the offending step"
    assert_contains "$LAST_OUT" "has 9 logic lines" "reports the block's own logic-line count"
    log_pass "reports file:line, step name and logic-line count"
}

test_boundary_at_threshold() {
    # Off-by-one guard on both sides of INLINE_MAX_LOGIC=8.
    local d="$1"

    write_workflow "$d/at.yml" 1 8
    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "exactly 8 logic lines is at the limit and must pass"

    rm -f "$d/at.yml"
    write_workflow "$d/over.yml" 1 9
    rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "9 logic lines is over the limit and must fail"
    log_pass "boundary is exact: 8 passes, 9 fails"
}

test_comments_and_blanks_are_not_logic() {
    # Too-loud direction: a well-commented 6-line block must not be counted as a
    # 20-line one, or authors get punished for explaining themselves.
    local d="$1"
    {
        echo "name: fixture"
        echo "on: push"
        echo "jobs:"
        echo "  job:"
        echo "    runs-on: ubuntu-latest"
        echo "    steps:"
        echo "      - name: Commented"
        echo "        run: |"
        local i
        for i in 1 2 3 4 5 6; do
            echo "          # explanation $i"
            echo ""
            echo "          echo line$i"
        done
    } >"$d/commented.yml"

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 0 "$rc" "comments and blank lines must not count toward the limit"
    log_pass "only non-blank, non-comment lines count as logic"
}

test_counts_blocks_within_a_file() {
    # Shape check: the rule counts BLOCKS inside a file, not mere file presence.
    local d="$1"
    write_workflow "$d/multi.yml" 3

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "3 over-threshold blocks must fail"
    assert_contains "$LAST_OUT" "3 inline run: block(s)" "reports the actual block count"
    assert_contains "$LAST_OUT" "step: Violating 3" "reports the LAST block, not just the first"
    log_pass "counts each over-threshold block within a file (reports 3, not 1)"
}

test_reports_every_offending_file() {
    # Stopping at the first bad file turns one fix round into three.
    local d="$1"
    write_workflow "$d/alpha.yml" 1
    write_workflow "$d/beta.yml" 2

    local rc=0
    run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "multiple offending files must fail"
    assert_contains "$LAST_OUT" "alpha.yml" "names the first offending file"
    assert_contains "$LAST_OUT" "beta.yml" "names the second offending file"
    log_pass "reports every offending file in one pass"
}

test_no_baseline_escape_hatch() {
    # Regression guard on the deleted grandfather clause: a baseline file sitting
    # in the tree, naming the offending workflow with a matching count, must NOT
    # excuse it. If this ever passes at exit 0, the ratchet has come back.
    local d="$1"
    write_workflow "$d/legacy.yml" 2
    echo '{"legacy.yml":2}' >"$d/baseline.json"
    echo '{"legacy.yml":2}' >"$d/workflow-inline-baseline.json"

    local rc=0
    WORKFLOW_INLINE_BASELINE="$d/baseline.json" run_check "$d" || rc=$?
    assert_exit_code 1 "$rc" "a baseline file must not grandfather anything"
    assert_contains "$LAST_OUT" "legacy.yml" "still names the file the baseline tried to excuse"
    log_pass "no baseline escape hatch: a stray baseline file changes nothing"
}

test_empty_tree_is_not_a_pass() {
    # Anti-vacuity: if the workflow directory moves or empties, the rule is
    # asserting nothing and must say so instead of reporting clean.
    local d="$1"
    mkdir -p "$d/empty"

    local rc=0
    run_check "$d/empty" || rc=$?
    assert_exit_code 1 "$rc" "a workflow dir with no workflows must fail, not pass vacuously"
    assert_contains "$LAST_OUT" "this check is blind" "says the check has nothing to assert"
    log_pass "empty workflow tree fails (anti-vacuity)"
}

log_test "test-workflow-inline"
with_temp_dir test_thin_blocks_never_count
with_temp_dir test_fails_any_over_threshold_block
with_temp_dir test_reports_line_and_step_name
with_temp_dir test_boundary_at_threshold
with_temp_dir test_comments_and_blanks_are_not_logic
with_temp_dir test_counts_blocks_within_a_file
with_temp_dir test_reports_every_offending_file
with_temp_dir test_no_baseline_escape_hatch
with_temp_dir test_empty_tree_is_not_a_pass
echo ""
log_pass "all tests passed"
