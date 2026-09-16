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
SELFTEST_ONLY=false
PATTERN="test-*.sh"

while (($# > 0)); do
    case "$1" in
        --verbose | -v)
            VERBOSE=true
            shift
            ;;
        --selftest)
            SELFTEST_ONLY=true
            shift
            ;;
        *)
            PATTERN="$1"
            shift
            ;;
    esac
done

# --- the tree guard's classifier, and its controls -------------------------
#
# WHY THESE ARE FUNCTIONS. Both were written inline inside the end-of-run guard,
# where nothing could reach them: the guard only executes when the tree actually
# moved mid-run, so the only way to exercise it was to race a real write against
# a real battery. That is how both of its bugs were found, by hand, twice --
# and a proof you have to stage by hand is a proof that is not in the tree. Named
# and called from the guard, they can be driven directly by the controls below.

# changed_paths_between <before> <after> -- tracked paths that differ, sorted,
# one per line. The `|| true` is LOAD-BEARING: `diff` exits 1 whenever its inputs
# differ, which is always true at the only call site, and under `set -euo
# pipefail` a non-zero pipeline inside a command substitution aborts the script
# before the summary ever prints. Dropping it killed this runner silently once
# already; `guard_selftest` below now fails if it is dropped again.
changed_paths_between() {
    { diff <(printf '%s\n' "$1") <(printf '%s\n' "$2") || true; } |
        sed -n 's/^[<>] *[A-Z?! ][A-Z?! ] *//p' | sort -u
}

# battery_could_have_written -- reads paths on stdin, exits 0 if ANY is under a
# tree this battery writes. That question is the whole diagnosis: the battery is
# blamed only for paths it plausibly touched, and everything else is reported as
# an unknown concurrent writer, which in a checkout several sessions share is
# what the evidence actually supports.
battery_could_have_written() {
    local cp
    while IFS= read -r cp; do
        [[ -z "$cp" ]] && continue
        case "$cp" in
            .ci/* | scripts/* | packages/* | .github/*) return 0 ;;
        esac
    done
    return 1
}

# guard_selftest -- controls over the two functions above. Runs on EVERY battery
# invocation, before any test, for the same reason `check_pytest.py` runs its
# own: a verdict from an instrument that cannot fail is worse than no verdict,
# and this instrument decides who gets blamed for a moved tree.
guard_selftest() {
    local n=0 bad=0 got
    _c() {
        n=$((n + 1))
        if [[ "$2" != "$3" ]]; then
            echo "FAIL  $1: got '$2', wanted '$3'" >&2
            bad=$((bad + 1))
        fi
    }

    # A path under a tree the battery writes -> the battery is blamed.
    got=no
    printf '%s\n' ".ci/scripts/x.ts" | battery_could_have_written && got=yes
    _c "a .ci path blames the battery" "$got" "yes"
    got=no
    printf '%s\n' "scripts/x.ts" | battery_could_have_written && got=yes
    _c "so does a scripts path" "$got" "yes"

    # A path outside them -> an unknown writer. THIS is the arm the false
    # accusation of 2026-09-08 lacked: the driver edited .claude/settings.json
    # from another terminal and the battery was handed a remediation for a file
    # no gate test touches.
    got=no
    printf '%s\n' ".claude/settings.json" | battery_could_have_written && got=yes
    _c "a .claude path does NOT blame the battery" "$got" "no"
    got=no
    printf '%s\n' "docs/x.md" | battery_could_have_written && got=yes
    _c "nor does a docs path" "$got" "no"

    # Mixed: one plausible path is enough, because the battery may have written
    # its own while a peer wrote the other.
    got=no
    printf '%s\n' ".claude/settings.json" ".ci/scripts/x.ts" |
        battery_could_have_written && got=yes
    _c "a mixed set still blames the battery" "$got" "yes"

    # Empty input must not blame anyone. An `in`-style test that answered yes
    # here would make every clean run an accusation.
    got=no
    printf '' | battery_could_have_written && got=yes
    _c "an empty set blames nobody" "$got" "no"

    # THE EXTRACTOR, against real `git status --porcelain` shapes: two-column
    # status prefix, and ` M ` vs `M  ` vs `?? ` all stripped the same way.
    got="$(changed_paths_between " M a/one.ts" "$(printf ' M a/one.ts\nM  b/two.ts')")"
    _c "a new modified path is extracted" "$got" "b/two.ts"
    got="$(changed_paths_between "$(printf ' M a/one.ts\n M b/two.ts')" " M a/one.ts")"
    _c "a path that stopped differing is extracted too" "$got" "b/two.ts"

    # SORTED AND DEDUPLICATED, both observable only with more than one line.
    # A single-line control cannot see `sort -u` at all: dropping it left the
    # first two controls green, so these two were added to make it falsifiable.
    got="$(changed_paths_between " M b/two.ts" " M a/one.ts" | tr '\n' ',')"
    _c "the extracted paths come out sorted" "$got" "a/one.ts,b/two.ts,"
    got="$(changed_paths_between " M a/one.ts" "M  a/one.ts" | tr '\n' ',')"
    _c "and a path named on both sides appears once" "$got" "a/one.ts,"

    # AND THE `|| true`, WHICH NEEDS A FRESH PROCESS TO BE PROVABLE AT ALL.
    # `diff` exits 1 here by construction -- the inputs always differ at the real
    # call site, that is why the guard is running -- so without `|| true` the
    # assignment aborts the script before the summary prints. That is the silent
    # death this runner already suffered once.
    #
    # WHY `bash -c` AND NOT A SUBSHELL. This function is invoked as
    # `if ! guard_selftest`, and bash disables errexit for the whole body of a
    # command tested that way -- INCLUDING inside a command substitution that
    # re-runs `set -e` itself. Both weaker forms were tried against a subject
    # with the `|| true` deliberately removed and both PASSED: vacuous controls
    # reporting a proof they had not made. Only a separate process starts with a
    # clean errexit, so the mutant is what the child's silence measures.
    export -f changed_paths_between
    got="$(bash -c 'set -euo pipefail
        cp="$(changed_paths_between "$1" "$2")"
        printf "reached:%s" "$(printf "%s" "$cp" | tr "\n" ",")"' _ \
        " M a/one.ts" " M b/two.ts" 2>/dev/null)" || true
    export -n changed_paths_between
    _c "the extractor survives a differing diff under set -e" \
        "$got" "reached:a/one.ts,b/two.ts"

    unset -f _c
    if ((bad)); then
        echo "FAIL: $bad of $n tree-guard control(s) failed" >&2
        return 1
    fi
    echo "tree-guard selftest: $n control(s) passed"
    return 0
}

if ! guard_selftest; then
    echo "REFUSING TO RUN: the tree guard's own controls failed, so its verdict about" >&2
    echo "who moved the tree could not be trusted. Fix the classifier above." >&2
    exit 1
fi
$SELFTEST_ONLY && exit 0

# --- membership ------------------------------------------------------------
#
# Membership is BY NAME, so a pattern-subset run ('test-gate-*.sh') classifies
# correctly without any extra bookkeeping. Anything unclassified is T.
#
# ---------------------------------------------------------------------------
# THE ISOLATION CONTRACT (W2.4b). This runner is one of TWO schedulers over the
# same 147 gate tests. The other is scripts/ci-runner/pool.ts, whose header
# carries the contract's single definition; read it there rather than restating
# it here, because a definition living in two places is the thing this change
# exists to remove.
#
# In one line: `mutex: [r]` is an EXCLUSIVE claim on resource r, `reads: [r]` is
# a SHARED one, and two gates may overlap unless one holds r exclusively and the
# other holds r at all. That is exactly the W / S / T schedule below, so the
# three sets are DERIVED from the manifest rather than typed out here:
#
#   W = declares a `tree:` resource under `mutex`   (the real-tree writers)
#   S = declares a `tree:` resource under `reads`   (the scanners)
#   T = declares neither                            (fixture-isolated)
#
# WHY IT MOVED. The two schedulers decided isolation SEPARATELY, and they
# disagreed. Measured 2026-09-06 at commit ac817a647: this file honoured all
# three writers, while the manifest registered them with no `mutex` at all --
# zero of the 147 qualityGateTest entries carried one -- so `npm run ci` ran the
# exact combination the header above calls "a flake manufactured by the runner".
# Driven against the real pool, those three gates overlapped each other in every
# pairing. The disagreement was invisible because nothing compared the two, and
# it could not be fixed by editing one of them: a hand list inside a runner is
# not something the other runner can read. Driver contract section 7 states the
# same requirement, that adding a gate must not require an edit to a runner file.
#
# THE FALLBACK BELOW IS TEMPORARY AND LOUD. The mutex/reads declarations are a
# registry change and the registry has a single writer; until it lands, this file
# would otherwise lose the isolation it has today, which is the one outcome worse
# than the disagreement. So it falls back to the previous hand lists and SAYS SO
# on stderr. Delete the two *_FALLBACK arrays and the fallback branch in the same
# change that lands the declarations.
# ---------------------------------------------------------------------------

REPO_ROOT_FOR_LOCK="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GATES_LOCK="$REPO_ROOT_FOR_LOCK/scripts/ci-runner/gates.lock.json"

# classify_from_lock <mutex|reads> -- basenames of gate tests whose manifest entry
# declares a `tree:` resource under that claim strength, one per line. Empty when
# the lock is unreadable or declares nothing; the CALLER decides what that means,
# because "no declarations yet" and "lock is broken" must not silently become the
# same thing as "nothing needs isolating".
classify_from_lock() {
    python3 - "$GATES_LOCK" "$1" <<'CLASSIFY' 2>/dev/null || true
import json, os, sys

lock_path, claim = sys.argv[1], sys.argv[2]
try:
    with open(lock_path, encoding="utf-8") as fh:
        entries = json.load(fh)
except (OSError, ValueError):
    raise SystemExit(0)
if not isinstance(entries, list):
    raise SystemExit(0)

for entry in entries:
    if not isinstance(entry, dict):
        continue
    run = entry.get("run")
    if not isinstance(run, str) or ".ci/scripts/test/gates/" not in run:
        continue
    claimed = entry.get(claim)
    if not isinstance(claimed, list):
        continue
    if not any(isinstance(r, str) and r.startswith("tree:") for r in claimed):
        continue
    # A `run` is a command line in the general case, so take the word that
    # actually names the script rather than assuming it is the whole string.
    for word in run.split():
        if word.startswith(".ci/scripts/test/gates/"):
            print(os.path.basename(word))
            break
CLASSIFY
}

# W: writes into the real tree while it runs. Adding to this list is cheap;
# leaving something off it is a flake.
#
# FALLBACK COPY -- see the block above. The reasons stay with the entries because
# they are the only record of why each one is here, and each names the exact line
# that does the writing, which is what a `tree:` resource has to be derived from.
WRITER_TESTS_FALLBACK=(
    # Plants and deletes .ci/scripts/.gate-paths-exist{,-noise}-fixture.<pid>.ts;
    # test-gate-paths-exist.sh:71 sets FIXTURE_DIR to the real .ci/scripts.
    test-gate-paths-exist.sh
    # Plants and deletes scripts/.gate-anti-vacuity-fixture.ts
    # (test-gate-anti-vacuity.sh:393). Its harness also COPIES scripts/ and
    # .ci/scripts/ into a fixture, so it READS the resource the other two write,
    # which is why it stays exclusive against them under a path-scoped contract.
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
    # Backs up the REAL CLAUDE.md and scripts/data/doc-registry.md, drives
    # `gen-docs --write` over them, and restores with `cp "$BACKUP" "$TARGET"`
    # (test-docs-gen.sh:55 and :98). Both files are read by other gates while it
    # runs, so left in the pool it corrupts a concurrent reader.
    #
    # It was UNREGISTERED until 2026-09-06 and nothing said so, because
    # check-pool-writer-safety.sh could not report it: its parse had gone empty
    # against this file's post-W2.4b shape, and the anti-vacuity refusal that
    # exists for exactly that case called a log_fail() that does not exist, so
    # the gate exited 127 rather than refusing. Two failures had to be repaired
    # before this one line became visible.
    test-docs-gen.sh
)

# S: reads or copies the real .ci/scripts / scripts tree, directly or through
# the gate it drives. Written longest-first so the cost of the tail is legible
# here; the scheduler itself spawns S in glob order, which costs nothing because
# the members ahead of the long pole run in seconds.
SCANNER_TESTS_FALLBACK=(
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

# A READ LOOP, and it is worth saying why it is neither of the two shorter
# spellings, because both were tried and both are wrong here.
#
# NOT `ARR=($(cmd))`, which the two env seams below do use. Those split a VARIABLE
# the operator typed; this splits COMMAND OUTPUT, which is SC2207 and a different
# hazard: a test filename carrying a space would be silently split into two
# non-existent members and both would then be classified as T, quietly losing the
# isolation this block exists to establish. `check:ci-shell-lint` catches it.
#
# NOT `mapfile -t`, which is what shellcheck suggests for SC2207 and what this
# code said for about an hour. `mapfile` is bash 4+, and `check:ci-shell-commands`
# bans it repo-wide for the ubuntu-slim CI image, prescribing this exact loop in
# its own fix line. Taking shellcheck's advice traded one gate's finding for
# another's; the loop satisfies both. (This file already refuses to run below bash
# 5.1, so `mapfile` would have WORKED here and still been a policy violation --
# which is the kind of green a reviewer would have had no reason to question.)
read_lines_into() {
    local -n _dest="$1"
    local _line
    _dest=()
    while IFS= read -r _line; do
        [[ -n "$_line" ]] && _dest+=("$_line")
    done
}
read_lines_into WRITER_TESTS < <(classify_from_lock mutex)
read_lines_into SCANNER_TESTS < <(classify_from_lock reads)

# THE FALLBACK IS CONSULTED LAST, AFTER THE ENV SEAMS, and the ordering is not
# cosmetic. Put ahead of them it still fires when RUN_ALL_WRITERS has already
# decided membership, so its notice lands in the stderr of a run whose isolation
# was never in doubt -- and test-run-all-parallel.sh captures runner output with
# `2>&1` and compares it byte-for-byte, so a diagnostic printed on a run that did
# not need it is a diagnostic that ends up inside an assertion. Speak only when
# nothing else has spoken.
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

if [[ -z "${RUN_ALL_WRITERS+x}" && -z "${RUN_ALL_SCANNERS+x}" ]] &&
    ((${#WRITER_TESTS[@]} == 0)) && ((${#SCANNER_TESTS[@]} == 0)); then
    # NOT silent, and not a line that scrolls past either: it names the exact file
    # that has to change to make it stop, so the fallback cannot become permanent
    # by nobody noticing it is still there.
    echo "run-all.sh: no 'tree:' isolation declared in scripts/ci-runner/gates.lock.json;" >&2
    echo "  falling back to the hand-maintained W/S lists in this file. This is the" >&2
    echo "  pre-W2.4b behaviour and is expected ONLY until the registry change lands" >&2
    echo "  the mutex/reads declarations. Delete the *_FALLBACK arrays and this branch" >&2
    echo "  in that same change." >&2
    WRITER_TESTS=("${WRITER_TESTS_FALLBACK[@]}")
    SCANNER_TESTS=("${SCANNER_TESTS_FALLBACK[@]}")
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
# `|| true` ON THE GREP, and leaving it out cost a CI round. Under `set -euo
# pipefail`, a grep that filters EVERYTHING out exits 1, and `T="$(tree_state)"`
# then aborts the whole battery -- before its first line of output, so CI showed
# `run-all.sh` exit 1 with nothing else at all. It passed locally for the worst
# possible reason: a developer's tree nearly always has SOME modified file, so
# the grep matched and returned 0. A CLEAN checkout is the case that breaks it,
# and a clean checkout is exactly what CI has.
# `|| true` ON THE GIT CALL TOO, and it is the same bug one stage upstream.
# `set -o pipefail` makes the pipeline take git's status, so anywhere git itself
# exits non-zero -- a directory that is not a work tree, a broken .git, git absent
# from PATH -- the whole battery aborts at this line with exit 128 and NOT ONE BYTE
# of output, before its first test runs. Found 2026-09-06 driving this runner
# against a fixture tree, which is exactly the setup the RUN_ALL_GATES_DIR seam
# exists to allow. The comment above already describes this failure shape for the
# grep and it is worth stating that the fix was applied to only one of the two
# stages: a pipefail hazard is per-stage, so guarding the last one that can fail is
# not guarding the pipeline. An unavailable git yields an empty snapshot on BOTH
# sides, so the before/after comparison stays honest rather than firing spuriously.
tree_state() { (cd "$BATTERY_REPO_ROOT" && { git status --porcelain 2>/dev/null || true; } | { grep -v '^??' || true; } | sort); }
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

# THE EMPTY-SET CHECK ABOVE DOES NOT CATCH EVERY EMPTY SET, and the gap is only
# visible once you know how nullglob decides. It drops a word that IS a glob and
# matches nothing; a word containing no glob metacharacter is not a glob, so it
# survives verbatim. `test-{a,b}.sh` is exactly that shape -- brace expansion is
# NOT applied to the result of a parameter expansion, so the braces stay literal
# and `{}` and `,` are not glob characters. The array is then one entry long, the
# check above passes, and the run dies at `./test-{a,b}.sh: No such file or
# directory` from line 266 with a shell error naming no cause.
#
# The DIRECTION was already safe -- it counted as a failed test with 0 assertions
# rather than a short green -- so this changes the diagnostic, not the verdict.
for f in "${TEST_FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        log_fail "Pattern '$PATTERN' yielded '$f', which is not a file in $GATES_DIR. A pattern with no glob character is taken literally (brace expansion does not apply to \$PATTERN), so it is not filtered by nullglob."
    fi
done

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
    # WHO CHANGED IT IS NOT KNOWABLE FROM A BEFORE/AFTER DIFF ALONE, and asserting
    # the battery did it was wrong on 2026-09-08: the driver edited
    # `.claude/settings.json` from another terminal while this ran, and the battery
    # was accused plus handed a remediation -- "take a path seam" -- for a file no
    # gate test touches and for which no such seam exists. In a checkout several
    # sessions and agents write concurrently, which is this repo's normal state,
    # that is a false accusation with a misleading fix attached.
    #
    # So the message splits on a CHECKABLE fact: is a changed path one this battery
    # could plausibly have written? Under the trees the gate tests and their
    # subjects live in, it is still blamed on the battery. Anything else is an
    # unknown concurrent writer -- which is what the evidence actually supports.
    # EITHER WAY THE RUN STILL FAILS: a verdict from a tree that moved underneath
    # it is suspect whoever moved it, so this narrows the diagnosis without
    # softening the refusal.
    # `|| true` IS REQUIRED, and its absence killed this script silently the first
    # time: `diff` exits 1 when the inputs differ -- which is ALWAYS true here, that
    # is why we are in this branch -- and under `set -e` with `pipefail` a non-zero
    # pipeline in a command substitution aborts the run before the summary block
    # ever prints. The original guard carried the same `|| true` on its own diff for
    # exactly this reason. Caught by driving a real concurrent write, not by reading.
    changed_paths="$(changed_paths_between "$TREE_BEFORE" "$TREE_AFTER")"
    plausible=0
    if printf '%s\n' "$changed_paths" | battery_could_have_written; then
        plausible=1
    fi
    echo ""
    if ((plausible)); then
        echo "✗ the battery CHANGED TRACKED FILES in the working tree:"
        diff <(printf '%s\n' "$TREE_BEFORE") <(printf '%s\n' "$TREE_AFTER") | sed 's/^/    /' || true
        echo "  A gate test must work on a COPY. The validator it drives should take a path"
        echo "  seam (as check-devcontainer-pin-freshness.ts takes DEVCONTAINER_DOCKERFILE)"
        echo "  so the test can hand it a fixture instead of the tracked file. Find the"
        echo "  culprit by re-running tests one at a time against the file named above."
        fail=$((fail + 1))
        failed_tests+=("the battery itself: it left a tracked file modified")
    else
        echo "✗ TRACKED FILES CHANGED while the battery ran, by an UNKNOWN WRITER:"
        diff <(printf '%s\n' "$TREE_BEFORE") <(printf '%s\n' "$TREE_AFTER") | sed 's/^/    /' || true
        echo "  None of those paths is under a tree this battery writes, so the battery is"
        echo "  probably not the culprit -- a concurrent session or agent most likely is."
        echo "  The verdict is STILL SUSPECT: the tree moved underneath the run. Re-run on"
        echo "  a quiet tree before believing this result."
        fail=$((fail + 1))
        failed_tests+=("an unknown writer changed the tree mid-run; verdict suspect")
    fi
fi

echo "=============================================="
echo "Quality-gate tests: $pass passed, $fail failed ($assertions_total assertions)"
echo "=============================================="

if ((fail > 0)); then
    echo "Failed tests:"
    printf '  - %s\n' "${failed_tests[@]}"
    exit 1
fi
