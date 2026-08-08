#!/bin/bash
# Proof battery for the parallel scheduler inside .ci/scripts/test/run-all.sh.
#
# WHY THIS EXISTS. run-all.sh is the runner for every other gate test, so a
# defect in it does not fail loudly: it fails by running FEWER tests, or by
# shredding their output, or by reintroducing the real-tree collision the
# schedule exists to prevent. All three of those look like a green run. The
# battery below pins the four properties that separate "fast" from "still a
# gate", and every timing assertion carries its own control, because a
# stopwatch that can only ever read "fast enough" measures nothing.
#
#   1. The pool really runs tests at the same time -- with the control that
#      proves the measurement can FAIL (the same set at jobs=1 must be slow).
#   2. jobs=1 and jobs=4 produce byte-identical transcripts, exit codes and
#      failure sets over a mixed set (pass / red / vacuous-exit-0).
#   3. No test's output interleaves with another's, under --verbose, where a
#      naive worker-prints-directly design would shred both.
#   4. The W/S hold-back actually holds: a scanner never runs while a real-tree
#      writer is alive. Its control removes the schedule and shows the same
#      fixtures go red, so a green here is the hold-back and not luck.
#
# Everything runs against PLANTED FIXTURES in a temp directory via
# RUN_ALL_GATES_DIR, so this test touches no real gate and no real tree.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared test assertion / colour helpers
source "$SCRIPT_DIR/../lib/test-helpers.sh"

RUNNER="$REPO_ROOT/.ci/scripts/test/run-all.sh"

if [[ ! -x "$RUNNER" ]]; then
    log_fail "$RUNNER is missing or not executable; this gate has nothing to prove"
fi

now_ms() { date +%s%3N; }

# mk_fixture <dir> <name> <body-line>...
mk_fixture() {
    local dir="$1" name="$2"
    shift 2
    {
        printf '#!/bin/bash\n'
        printf 'set -euo pipefail\n'
        printf '%s\n' "$@"
    } >"$dir/$name"
    chmod +x "$dir/$name"
}

# ---------------------------------------------------------------------------
# 1. Concurrency, with the control that proves the stopwatch can fail.
# ---------------------------------------------------------------------------

test_pool_runs_tests_concurrently() {
    local temp="$1"
    local gates="$temp/gates"
    local i start parallel_ms serial_ms
    mkdir -p "$gates"
    for i in 1 2 3 4; do
        mk_fixture "$gates" "test-sleeper-$i.sh" 'sleep 2' "echo \"PASS: sleeper $i finished\""
    done

    start="$(now_ms)"
    RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=4 "$RUNNER" >/dev/null
    parallel_ms=$(($(now_ms) - start))

    if ((parallel_ms >= 6000)); then
        log_fail "four 2s tests took ${parallel_ms}ms at jobs=4; they are not overlapping"
    fi
    log_pass "four 2s tests finish in ${parallel_ms}ms at jobs=4 (ceiling 6000ms)"

    # THE CONTROL. Without it, a runner that silently ignored RUN_ALL_JOBS and
    # ran everything at once anyway would pass the assertion above, and so would
    # a broken stopwatch. The same four fixtures at jobs=1 must be slow.
    start="$(now_ms)"
    RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=1 "$RUNNER" >/dev/null
    serial_ms=$(($(now_ms) - start))

    if ((serial_ms < 8000)); then
        log_fail "control failed: the same four took ${serial_ms}ms at jobs=1, so the timing assertion above cannot fire"
    fi
    log_pass "control: the same four take ${serial_ms}ms at jobs=1 (floor 8000ms), so the measurement can fail"
}

# ---------------------------------------------------------------------------
# 2. Determinism across worker counts, over a set that is not all-green.
# ---------------------------------------------------------------------------

test_jobs_one_and_jobs_four_agree() {
    local temp="$1"
    local gates="$temp/gates"
    local out_serial out_parallel rc_serial=0 rc_parallel=0
    mkdir -p "$gates"
    mk_fixture "$gates" "test-a-green.sh" 'echo "PASS: green fixture asserted something"'
    mk_fixture "$gates" "test-b-red.sh" 'echo "diagnostic line from the red fixture"' 'exit 1'
    # Exit 0 with no PASS: line at all. run-all.sh must score this as a failure
    # in both modes; a mode that scored it differently would mean the vacuity
    # guard moved with the scheduler.
    mk_fixture "$gates" "test-c-vacuous.sh" 'echo "this fixture asserts nothing"' 'exit 0'
    mk_fixture "$gates" "test-d-green.sh" 'sleep 1' 'echo "PASS: slow green fixture asserted something"'

    out_serial="$(RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=1 "$RUNNER" 2>&1)" || rc_serial=$?
    out_parallel="$(RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=4 "$RUNNER" 2>&1)" || rc_parallel=$?

    assert_eq "$rc_serial" "1" "the mixed fixture set must exit 1 at jobs=1"
    assert_eq "$rc_parallel" "$rc_serial" "exit code must not depend on the worker count"
    assert_eq "$out_parallel" "$out_serial" "the transcript must not depend on the worker count"
    assert_contains "$out_serial" "2 passed, 2 failed" "the mixed set must score 2 pass / 2 fail"
    assert_contains "$out_serial" "test-c-vacuous.sh (exited 0 but made no assertions)" \
        "the vacuity guard must still fire under the scheduler"
    log_pass "jobs=1 and jobs=4 agree byte-for-byte on transcript, exit code and failure set"
}

# ---------------------------------------------------------------------------
# 3. No interleaving. This is what the main-printer design buys.
# ---------------------------------------------------------------------------

test_output_blocks_never_interleave() {
    local temp="$1"
    local gates="$temp/gates"
    local out seen expected
    mkdir -p "$gates"
    mk_fixture "$gates" "test-alpha.sh" \
        'echo "alpha-1"' 'sleep 0.4' 'echo "alpha-2"' 'sleep 0.4' 'echo "alpha-3"' \
        'echo "PASS: alpha emitted three lines"'
    mk_fixture "$gates" "test-beta.sh" \
        'echo "beta-1"' 'sleep 0.4' 'echo "beta-2"' 'sleep 0.4' 'echo "beta-3"' \
        'echo "PASS: beta emitted three lines"'

    # --verbose is the hostile case: it replays each test's whole log, so a
    # worker that printed directly to the terminal would splice the two.
    out="$(RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=4 "$RUNNER" --verbose 2>&1)"
    seen="$(printf '%s\n' "$out" | grep -oE '^(alpha|beta)-[0-9]' | paste -sd' ' -)"
    expected="alpha-1 alpha-2 alpha-3 beta-1 beta-2 beta-3"
    assert_eq "$seen" "$expected" "each test's lines must stay contiguous and in glob order"
    log_pass "two concurrent tests emit contiguous, glob-ordered blocks under --verbose"
}

# ---------------------------------------------------------------------------
# 4. The W/S hold-back, and the control that proves it is doing the work.
# ---------------------------------------------------------------------------

test_scanners_never_overlap_writers() {
    local temp="$1"
    local gates="$temp/gates"
    local sentinel="$temp/writer.sentinel"
    local rc_scheduled=0 rc_unscheduled=0 out_scheduled out_unscheduled
    mkdir -p "$gates"

    # The writer holds a sentinel for 2s, exactly as the two real writers hold
    # a fixture file inside .ci/scripts and scripts.
    mk_fixture "$gates" "test-w-writer.sh" \
        "touch \"$sentinel\"" 'sleep 2' "rm -f \"$sentinel\"" \
        'echo "PASS: writer held and released its fixture"'
    # The scanner reds if it sees the sentinel, exactly as a recursive copy of a
    # directory reds when a file vanishes underneath it.
    mk_fixture "$gates" "test-x-scanner.sh" \
        'sleep 1' \
        "if [[ -e \"$sentinel\" ]]; then" \
        '    echo "writer fixture was present while the scanner ran" >&2' \
        '    exit 1' \
        'fi' \
        'echo "PASS: scanner saw a quiet tree"'

    out_scheduled="$(RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=4 \
        RUN_ALL_WRITERS="test-w-writer.sh" RUN_ALL_SCANNERS="test-x-scanner.sh" \
        "$RUNNER" 2>&1)" || rc_scheduled=$?
    assert_eq "$rc_scheduled" "0" "with the W/S schedule the scanner must never see the writer's fixture"
    assert_contains "$out_scheduled" "2 passed, 0 failed" "both fixtures must pass under the schedule"
    log_pass "the S set is held back until the W chain has released the tree"

    # THE CONTROL. Drop both fixtures into T -- which is what a flat pool is --
    # and the same two must collide. Without this, a runner that ran everything
    # serially, or one whose scanner check never fired, would look identical.
    out_unscheduled="$(RUN_ALL_GATES_DIR="$gates" RUN_ALL_JOBS=4 \
        RUN_ALL_WRITERS="" RUN_ALL_SCANNERS="" \
        "$RUNNER" 2>&1)" || rc_unscheduled=$?
    assert_eq "$rc_unscheduled" "1" "control failed: a flat pool must reproduce the collision this schedule prevents"
    assert_contains "$out_unscheduled" "writer fixture was present while the scanner ran" \
        "control failed: the collision must be the reported reason"
    log_pass "control: without the schedule the same two fixtures collide, so the green above is the hold-back"
}

log_test "test-run-all-parallel"

with_temp_dir test_pool_runs_tests_concurrently
with_temp_dir test_jobs_one_and_jobs_four_agree
with_temp_dir test_output_blocks_never_interleave
with_temp_dir test_scanners_never_overlap_writers

log_pass "all tests passed"
