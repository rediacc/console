#!/bin/bash
# Cross-cutting test runner for every quality-gate test.
#
# Invoked via `npm run test:quality-gates`. Runs every
# .ci/scripts/test/gates/test-*.sh (the new BLOCKER / advisory / age-check
# gate tests) and reports pass/fail count. Exits non-zero on any failure.
#
# NOTE: this runner only executes gate tests. The other bash tests under
# .ci/scripts/test/ (install script, linux packages, etc.) are run by
# separate CI jobs with different timing / infrastructure needs.
#
# WHY THIS RUNS IN PARALLEL, AND WHY THE SCHEDULE MATTERS MORE THAN THE DEGREE.
# Serially the battery took about 18 minutes of the Security job's 20-minute
# budget, so the step was one slow test away from a timeout rather than one slow
# test away from a slow run. The obvious fix -- fan the tests out over the
# runner's cores -- is unsafe as a flat pool, and the reason is specific rather
# than general: two of these tests WRITE INTO THE REAL TREE, because the code
# they exercise hardcodes the real tree and cannot be pointed at a fixture.
#
#   test-gate-paths-exist.sh   plants and deletes .ci/scripts/.gate-paths-exist{,-noise}-fixture.<pid>.ts
#   test-gate-anti-vacuity.sh  plants and deletes scripts/.gate-anti-vacuity-fixture.ts
#
# The <pid> in the first pair is not decoration: this schedule serialises the W
# chain within ONE battery, and two independent batteries (two sessions) used to
# collide on fixed filenames -- each trap deleting the other's fixture, which
# read as "the detector is broken". The pid makes those two runs disjoint; the
# schedule below still handles the in-battery half.
#
# Meanwhile a good dozen other tests RECURSIVELY ENUMERATE those same two
# directories -- `cp -r`, `find`, `grep -r`, or a gate that does one of those on
# their behalf. A file that appears or vanishes mid-enumeration is a hard error
# (`cp: cannot stat`, grep exit 2), and under `set -euo pipefail` that is a
# one-shot red which passes on the very next serial re-run. That is a flake
# manufactured by the runner, and lowering the worker count does not remove it:
# with two workers the collision is rarer and just as real.
#
# So the tests are scheduled in three sets rather than pooled flat:
#
#   W (writers)  the two above, run as one serial chain, exclusive against S
#   S (scanners) everything that reads the real .ci/scripts or scripts tree,
#                pool-safe among themselves because they only read, released
#                only once the W chain has finished
#   T (temp)     everything else -- env-seam plus mktemp fixtures, isolated by
#                construction, safe to run against anything
#
# The W chain starts at t=0 (it also holds the longest single test, so
# longest-first would put it there anyway), T fills the remaining slots while it
# runs, and S drains after it. Wall time becomes max(W chain, longest T) plus
# the S drain instead of the sum of all 86.
#
# OUTPUT IS PRINTED BY MAIN ONLY. Workers write to $RESULTS_DIR/<idx>.log and
# then atomically publish $RESULTS_DIR/<idx>.rc; they never touch the terminal.
# Main walks the indices in ascending order and prints each finished test's
# block, so the transcript is byte-for-byte the shape a serial run produced, in
# the same order, with no interleaving and no locking.
#
# Usage:
#   ./run-all.sh                      # run all gate tests
#   ./run-all.sh --verbose            # show stdout of each test
#   ./run-all.sh 'test-blocker*.sh'   # run only matching tests
#
# Environment seams (all optional; the defaults are what CI runs):
#   RUN_ALL_JOBS       worker count. 1 degenerates to a serial run through this
#                      same code path, which is what the determinism control uses.
#   RUN_ALL_GATES_DIR  directory of gate tests to run
#   RUN_ALL_WRITERS    space-separated W membership, overriding the list below
#   RUN_ALL_SCANNERS   space-separated S membership, overriding the list below

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATES_DIR="${RUN_ALL_GATES_DIR:-$SCRIPT_DIR/gates}"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared test-runner colour / status helpers
source "$SCRIPT_DIR/lib/test-helpers.sh"

# `wait -n` IS the scheduler. Bash 4.3 introduced it, but before 5.1 it could
# overlook a job that had already exited before the call, which turns the slot
# loop into either a hang or a silent over-subscription. Fail loudly instead of
# falling back to serial: a quiet fallback would make the speedup depend on
# which shell happens to be installed and nobody would ever notice it was gone.
# Every caller is Linux (CI is ubuntu-latest, the operator is WSL2); there is no
# macOS caller to keep on bash 3.2.
if ((BASH_VERSINFO[0] < 5)) || { ((BASH_VERSINFO[0] == 5)) && ((BASH_VERSINFO[1] < 1)); }; then
    log_fail "run-all.sh needs bash >= 5.1 for 'wait -n' (found $BASH_VERSION)"
fi

VERBOSE=false
PATTERN="test-*.sh"

while (($# > 0)); do
    case "$1" in
        --verbose | -v)
            VERBOSE=true
            shift
            ;;
        *)
            PATTERN="$1"
            shift
            ;;
    esac
done

# --- membership ------------------------------------------------------------
#
# Both lists are BY NAME, so a pattern-subset run ('test-gate-*.sh') classifies
# correctly without any extra bookkeeping. Everything not named here is T.

# W: writes into the real tree while it runs. Adding to this list is cheap;
# leaving something off it is a flake.
WRITER_TESTS=(
    test-gate-paths-exist.sh
    test-gate-anti-vacuity.sh
    # Swaps the REAL .ci/scripts/version/resolve-version.sh for a stub and
    # restores it (two sites: test-generate-tag-inputs.sh:289 and :311), because
    # generate-tag.sh is invoked via `cd "$REPO_ROOT"` and has no fixture seam.
    # It was classified T on the strength of its own comment at :277-279, which
    # says the test "cannot disturb a shared tree" -- true of the tag namespace
    # it avoids writing, false of the working tree it overwrites. Left in T it
    # reddened gate-test:claude-hooks with a bash syntax error in a file that
    # parses clean, because a concurrent gate read a script mid-restore.
    test-generate-tag-inputs.sh
)

# S: reads or copies the real .ci/scripts / scripts tree, directly or through
# the gate it drives. Written longest-first so the cost of the tail is legible
# here; the scheduler itself spawns S in glob order, which costs nothing because
# the members ahead of the long pole run in seconds.
SCANNER_TESTS=(
    test-dead-bash.sh
    test-ci-parity.sh
    test-review-status.sh
    test-suppression-liveness.sh
    test-ci-runner.sh
    test-profiler-coverage.sh
    test-runner-advice.sh
    test-overrides-reasons.sh
    test-greenlight.sh
    test-knip-blockers.sh
    test-scope-gate-outputs.sh
    test-label-inventory.sh
    test-swallowed-failures.sh
    test-trap-registry.sh
    test-breakpoint-portability.sh
    test-autopilot-breakpoint-alignment.sh
    test-label-references.sh
    test-autopilot-workflow-invariants.sh
    test-dead-case-arms.sh
    test-tutorial-render-queue.sh
    test-shell-counter-increment.sh
)

if [[ -n "${RUN_ALL_WRITERS+x}" ]]; then
    # BLOCKER: intentional word splitting of the injected W list into an array; quoting would make the whole space-separated string one member and the seam would silently classify nothing
    # shellcheck disable=SC2206
    # BLOCKER: intentional word splitting of the injected W list
    WRITER_TESTS=($RUN_ALL_WRITERS)
fi
if [[ -n "${RUN_ALL_SCANNERS+x}" ]]; then
    # BLOCKER: intentional word splitting of the injected S list into an array; quoting would make the whole space-separated string one member and the seam would silently classify nothing
    # shellcheck disable=SC2206
    # BLOCKER: intentional word splitting of the injected S list
    SCANNER_TESTS=($RUN_ALL_SCANNERS)
fi

# THE BATTERY MAY NOT LEAVE A MARK ON THE TREE, and this is here rather than in a
# static rule because a static rule cannot see the interesting cases.
#
# A gate test that rewrites a TRACKED file is not merely untidy. It is visible to
# every other gate sharing the tree, and this repo runs ~294 of them at 20x
# concurrency: on 2026-09-03 test-devcontainer-pin-freshness.sh drove `--upgrade`
# against the real .devcontainer/Dockerfile and restored it from a trap, and
# check:ci-setup-idempotency -- a gate with nothing to do with devcontainers --
# reported "setup --check changed the working tree", naming a command that never
# writes that file. The reader was sent into run.sh. It is also a hazard outside
# CI, because this working tree usually holds another session's uncommitted work
# and a test can be interrupted between its mutation and its restore.
#
# Snapshot before and after the WHOLE battery rather than per test: one pair of
# git calls instead of 128, and the delta names the file, which is enough to find
# the culprit with a targeted re-run. Untracked noise is excluded because several
# tests legitimately plant fixtures inside the tree (gate-paths-exist needs its
# scan fixture to be scanned); a TRACKED file changing is the defect.
BATTERY_REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain 2>/dev/null | grep -v '^??' | sort); }
TREE_BEFORE="$(tree_state)"

cd "$GATES_DIR"
shopt -s nullglob
# BLOCKER: intentional glob expansion of user-supplied $PATTERN into the TEST_FILES array; quoting would prevent shopt nullglob from filtering non-matches
# shellcheck disable=SC2206
# BLOCKER: intentional glob expansion of user-supplied $PATTERN
TEST_FILES=($PATTERN)
shopt -u nullglob

if ((${#TEST_FILES[@]} == 0)); then
    log_fail "No test files matched pattern: $PATTERN in $GATES_DIR"
fi

# --- worker count ----------------------------------------------------------
#
# 4 on ubuntu-latest. Capped at 8 locally so a bare `npm run
# check:ci-quality-gates` on a 20-core box does not fork-bomb npx/tsx: several
# of these tests shell out to node, and 20 concurrent node startups cost more in
# contention than they buy in parallelism.
CPUS=4
if command -v nproc >/dev/null 2>&1; then
    CPUS="$(nproc)"
fi
JOBS="${RUN_ALL_JOBS:-0}"
if ((JOBS <= 0)); then
    JOBS="$CPUS"
    if ((JOBS > 8)); then
        JOBS=8
    fi
fi

RESULTS_DIR="$(mktemp -d)"
# BLOCKER: expanding RESULTS_DIR now binds the specific path into the trap, so cleanup removes the directory this run created even if the variable is later reassigned
# shellcheck disable=SC2064
# BLOCKER: expanding RESULTS_DIR now binds the specific path into the trap
trap "rm -rf '$RESULTS_DIR'" EXIT

WRITERS_DONE="$RESULTS_DIR/writers.done"

pass=0
fail=0
assertions_total=0
failed_tests=()
printed=0

# log_pass() colours its output, so a PASS line starts with a real ESC byte.
# The previous pattern spelled that byte '\x1b', which POSIX ERE does not
# interpret as an escape -- GNU grep read it as the literal text "x1b", so this
# summary matched NOTHING and every colour-emitting gate test contributed zero
# visible evidence to the non-verbose run. The counter was still right, which is
# why it went unnoticed: "20 passed" with no assertions listed looks identical to
# 20 tests that assert nothing. $'...' puts the actual byte in the pattern.
PASS_RE=$'^(\033\\[0;32m)?PASS:'

# in_list <needle> <item>... -- membership without an associative array, so the
# injected seams stay plain strings.
in_list() {
    local needle="$1" item
    shift
    for item in "$@"; do
        if [[ "$item" == "$needle" ]]; then
            return 0
        fi
    done
    return 1
}

# run_one <idx> -- a WORKER. Never prints. Publishes the exit status last, and
# publishes it atomically (tmp + mv), so main can treat the presence of <idx>.rc
# as proof that <idx>.log is complete.
run_one() {
    local idx="$1" rc=0
    "./${TEST_FILES[idx]}" >"$RESULTS_DIR/$idx.log" 2>&1 || rc=$?
    printf '%s\n' "$rc" >"$RESULTS_DIR/$idx.rc.part"
    mv -f "$RESULTS_DIR/$idx.rc.part" "$RESULTS_DIR/$idx.rc"
}

# run_chain <idx>... -- the W set as ONE background unit, serial inside. The
# done-marker is written after the last member's .rc, which is what makes it a
# safe release signal for S: when it exists, no real-tree writer is still alive.
run_chain() {
    local idx
    for idx in "$@"; do
        run_one "$idx"
    done
    : >"$WRITERS_DONE"
}

# print_block <idx> -- MAIN ONLY. This is the serial runner's per-test block,
# unchanged in shape, reading a finished log instead of running the test inline.
print_block() {
    local idx="$1"
    local test_file="${TEST_FILES[idx]}"
    local log="$RESULTS_DIR/$idx.log" rc_file="$RESULTS_DIR/$idx.rc"
    local rc assertions

    log_test "$test_file"
    if [[ ! -f "$rc_file" ]]; then
        # ANTI-VACUITY. A test that was never scheduled, or whose worker died
        # before publishing, is a FAILURE and never a skip. A scheduling bug has
        # to present as red, otherwise it presents as a shorter green run and
        # that is the exact shape of a gate that stopped gating.
        fail=$((fail + 1))
        failed_tests+=("$test_file (no result recorded)")
        if [[ -f "$log" ]]; then
            cat "$log"
        fi
        echo -e "${RED}FAIL:${NC} $test_file produced no result: the scheduler never completed it" >&2
    else
        rc="$(cat "$rc_file")"
        if [[ "$rc" == "0" ]]; then
            # Count the assertions the test actually made. A test that exits 0
            # without emitting a single PASS is vacuous -- it asserted nothing and
            # must not be reported as a passing gate.
            assertions="$(grep -acE "$PASS_RE" "$log" || true)"
            if ((assertions == 0)); then
                fail=$((fail + 1))
                failed_tests+=("$test_file (exited 0 but made no assertions)")
                cat "$log"
                # Not log_fail: that exits, and the remaining tests still need to run.
                echo -e "${RED}FAIL:${NC} $test_file exited 0 without a single PASS: line" >&2
            else
                pass=$((pass + 1))
                assertions_total=$((assertions_total + assertions))
                if [[ "$VERBOSE" == "true" ]]; then
                    cat "$log"
                else
                    grep -aE "$PASS_RE" "$log" || true
                fi
            fi
        else
            fail=$((fail + 1))
            failed_tests+=("$test_file")
            cat "$log"
        fi
    fi
    rm -f "$log" "$rc_file"
    printed=$((printed + 1))
    echo ""
}

# drain_ready -- print every finished test whose turn has come. Strictly
# ascending, so the transcript and the "Failed tests:" list are in glob order
# regardless of which worker finished first.
drain_ready() {
    while ((printed < ${#TEST_FILES[@]})) && [[ -f "$RESULTS_DIR/$printed.rc" ]]; do
        print_block "$printed"
    done
}

live_jobs() {
    jobs -pr | wc -l
}

# wait_for_slot -- block until a worker slot frees. The `|| true` is mandatory:
# `wait -n` returns the finished job's exit status, and a red gate test must not
# kill the runner under `set -e`.
wait_for_slot() {
    while (($(live_jobs) >= JOBS)); do
        wait -n || true
        drain_ready
    done
}

wait_for_writers() {
    # If the chain's subshell died without its marker, stop waiting rather than
    # hang: the missing .rc files then surface through print_block as failures,
    # which is the loud outcome.
    while [[ ! -f "$WRITERS_DONE" ]] && (($(live_jobs) > 0)); do
        wait -n || true
        drain_ready
    done
    drain_ready
}

drain_all() {
    while (($(live_jobs) > 0)); do
        wait -n || true
        drain_ready
    done
    drain_ready
    # Anything still unprinted has no .rc and never will; print_block scores it
    # as a failure.
    while ((printed < ${#TEST_FILES[@]})); do
        print_block "$printed"
    done
}

# --- schedule --------------------------------------------------------------

writer_idx=()
scanner_idx=()
temp_idx=()
for idx in "${!TEST_FILES[@]}"; do
    name="${TEST_FILES[idx]}"
    if in_list "$name" "${WRITER_TESTS[@]}"; then
        writer_idx+=("$idx")
    elif in_list "$name" "${SCANNER_TESTS[@]}"; then
        scanner_idx+=("$idx")
    else
        temp_idx+=("$idx")
    fi
done

if ((${#writer_idx[@]} > 0)); then
    run_chain "${writer_idx[@]}" &
else
    : >"$WRITERS_DONE"
fi

for idx in "${temp_idx[@]}"; do
    wait_for_slot
    run_one "$idx" &
done

wait_for_writers

for idx in "${scanner_idx[@]}"; do
    wait_for_slot
    run_one "$idx" &
done

drain_all

# The self-guard on the guard. print_block is the only thing that increments
# `printed`, and it is also the only thing that scores a test, so a printed
# count short of the file count means the scheduler dropped work silently.
if ((printed != ${#TEST_FILES[@]})); then
    log_fail "scheduler printed $printed of ${#TEST_FILES[@]} test blocks; results were lost"
fi

TREE_AFTER="$(tree_state)"
if [[ "$TREE_BEFORE" != "$TREE_AFTER" ]]; then
    echo ""
    echo "✗ the battery CHANGED TRACKED FILES in the working tree:"
    diff <(printf '%s\n' "$TREE_BEFORE") <(printf '%s\n' "$TREE_AFTER") | sed 's/^/    /' || true
    echo "  A gate test must work on a COPY. The validator it drives should take a path"
    echo "  seam (as check-devcontainer-pin-freshness.ts takes DEVCONTAINER_DOCKERFILE)"
    echo "  so the test can hand it a fixture instead of the tracked file. Find the"
    echo "  culprit by re-running tests one at a time against the file named above."
    fail=$((fail + 1))
    failed_tests+=("the battery itself: it left a tracked file modified")
fi

echo "=============================================="
echo "Quality-gate tests: $pass passed, $fail failed ($assertions_total assertions)"
echo "=============================================="

if ((fail > 0)); then
    echo "Failed tests:"
    printf '  - %s\n' "${failed_tests[@]}"
    exit 1
fi
