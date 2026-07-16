#!/bin/bash
# Both-ways test for the inline-run rule in .ci/scripts/quality/check-workflows.sh.
#
# The rule keeps CI step LOGIC out of workflow YAML: a `run:` block scalar whose
# shell logic exceeds INLINE_MAX_LOGIC (8) non-blank/non-comment lines is a
# violation, and legacy violations are frozen per-file in a baseline that may only
# ratchet DOWN. A gate like this fails in BOTH directions, so both are asserted:
#
#   - Too quiet: a new inline block, or a new over-threshold block in an existing
#     file, slips through and the workflow accretes un-shared shell logic.
#   - Too loud: it miscounts and reds a file that is at (or under) its frozen
#     baseline, blocking work that already complies.
#
# The rule is driven in isolation via WORKFLOW_INLINE_ONLY=1 + WORKFLOW_DIR +
# WORKFLOW_INLINE_BASELINE pointed at fixtures, so the test never depends on the
# real .github/workflows census.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

CHECK="$REPO_ROOT/.ci/scripts/quality/check-workflows.sh"

LAST_OUT=""

# run_check <workflow-dir> <baseline-file>
# Runs ONLY the inline-run rule against the fixture tree; captures output + rc.
run_check() {
    local dir="$1" baseline="$2" rc=0
    LAST_OUT="$(WORKFLOW_INLINE_ONLY=1 WORKFLOW_DIR="$dir" WORKFLOW_INLINE_BASELINE="$baseline" \
        bash "$CHECK" 2>&1)" || rc=$?
    return "$rc"
}

# write_workflow <path> <num-violating-blocks>
# Emits a valid workflow with <n> over-threshold run: blocks (9 logic lines each)
# plus one always-clean thin block (2 lines) to prove thin blocks never count.
write_workflow() {
    local path="$1" n="$2" i j
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
            for j in 1 2 3 4 5 6 7 8 9; do
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

test_passes_at_exact_baseline() {
    local d="$1"
    write_workflow "$d/legacy.yml" 2
    echo '{"legacy.yml":2}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 0 "$rc" "file at its exact frozen baseline must pass"
    log_pass "file at exact baseline passes (2 legacy blocks, baseline 2)"
}

test_thin_blocks_never_count() {
    # A file that is ALL thin blocks (0 violations) with no baseline entry passes.
    local d="$1"
    write_workflow "$d/clean.yml" 0
    echo '{}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 0 "$rc" "a file with only thin run: blocks must pass"
    log_pass "thin (<=8 line) run: blocks never count as violations"
}

test_fails_new_file_absent_from_baseline() {
    local d="$1"
    write_workflow "$d/newbie.yml" 1
    echo '{}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 1 "$rc" "a new file with inline logic must fail"
    assert_contains "$LAST_OUT" "not in the baseline" "names the missing-baseline cause"
    assert_contains "$LAST_OUT" "extract each over-threshold block to .ci/scripts" "prints the teaching remedy"
    assert_contains "$LAST_OUT" "newbie.yml" "names the offending file"
    log_pass "new file with an inline block fails (absent from baseline)"
}

test_fails_regression_above_baseline() {
    local d="$1"
    write_workflow "$d/legacy.yml" 2
    echo '{"legacy.yml":1}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 1 "$rc" "adding a block above baseline must fail"
    assert_contains "$LAST_OUT" "regression" "names the regression"
    log_pass "count above baseline fails (2 blocks vs baseline 1)"
}

test_fails_ratchet_down_when_stale() {
    # Fixed one block (now 1) but baseline still records 2 -> must force a ratchet.
    local d="$1"
    write_workflow "$d/legacy.yml" 1
    echo '{"legacy.yml":2}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 1 "$rc" "count below baseline must fail until the baseline is lowered"
    assert_contains "$LAST_OUT" "ratchet down" "instructs the author to ratchet down"
    log_pass "count below baseline fails (must ratchet down)"
}

test_passes_after_ratchet_down() {
    # Same fixed file, but the baseline has now been lowered to match -> passes.
    local d="$1"
    write_workflow "$d/legacy.yml" 1
    echo '{"legacy.yml":1}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 0 "$rc" "lowering the baseline to match must pass"
    log_pass "ratchet-down clears the failure (baseline lowered to 1)"
}

test_fails_stale_entry_for_missing_file() {
    # Baseline names a file that no longer exists -> stale entry must be removed.
    local d="$1"
    write_workflow "$d/clean.yml" 0
    echo '{"ghost.yml":3}' >"$d/baseline.json"

    local rc=0
    run_check "$d" "$d/baseline.json" || rc=$?
    assert_exit_code 1 "$rc" "a baseline entry for a deleted file must fail"
    assert_contains "$LAST_OUT" "no longer exists" "names the vanished file"
    log_pass "stale baseline entry for a missing file fails"
}

test_counts_blocks_within_a_file() {
    # Shape check: the rule counts BLOCKS inside a file, not mere file presence.
    local d="$1"
    write_workflow "$d/multi.yml" 3

    echo '{"multi.yml":3}' >"$d/exact.json"
    local rc=0
    run_check "$d" "$d/exact.json" || rc=$?
    assert_exit_code 0 "$rc" "3 blocks against baseline 3 must pass"

    echo '{"multi.yml":2}' >"$d/low.json"
    rc=0
    run_check "$d" "$d/low.json" || rc=$?
    assert_exit_code 1 "$rc" "3 blocks against baseline 2 must fail (counts each block)"
    assert_contains "$LAST_OUT" "3 inline run: block(s)" "reports the actual block count"
    log_pass "counts each over-threshold block within a file (3 blocks distinguished from 2)"
}

log_test "test-workflow-inline"
with_temp_dir test_passes_at_exact_baseline
with_temp_dir test_thin_blocks_never_count
with_temp_dir test_fails_new_file_absent_from_baseline
with_temp_dir test_fails_regression_above_baseline
with_temp_dir test_fails_ratchet_down_when_stale
with_temp_dir test_passes_after_ratchet_down
with_temp_dir test_fails_stale_entry_for_missing_file
with_temp_dir test_counts_blocks_within_a_file
echo ""
log_pass "all tests passed"
