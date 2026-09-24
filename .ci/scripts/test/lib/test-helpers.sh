#!/bin/bash
# Shared test assertion helpers for .ci/scripts/test/test-*.sh scripts.
#
# Usage:
#   source "$(dirname "$0")/lib/test-helpers.sh"
#   with_temp_dir test_my_case
#   log_pass "my case"
#
# Convention: every test function is named test_* and is called at the bottom
# of the test file. On pass, call log_pass "<name>". On fail, call log_fail
# which exits 1 immediately (tests are designed to halt on first failure for
# clear diagnostic output).

# Guard against double-sourcing.
[[ -n "${__TEST_HELPERS_SH_SOURCED:-}" ]] && return 0
readonly __TEST_HELPERS_SH_SOURCED=1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() { echo -e "${GREEN}PASS:${NC} $*"; }
log_fail() {
    echo -e "${RED}FAIL:${NC} $*" >&2
    exit 1
}
log_test() { echo -e "${YELLOW}TEST:${NC} $*"; }
# info/error were ASSUMED by callers before they existed here:
# test-shell-counter-increment.sh (retired in W7 P5; its port is
# test_gate_shell_counter_increment.py) called both under `set -uo pipefail`
# (no -e), so every run printed `log_info: command not found` and its report
# would have said the same instead of naming the offending file (found
# 2026-08-08 by the run-all parallelization agent). Defined once, centrally.
log_info() { echo -e "${YELLOW}INFO:${NC} $*"; }
log_error() { echo -e "${RED}ERROR:${NC} $*" >&2; }

# assert_eq <actual> <expected> [<message>]
assert_eq() {
    local actual="$1" expected="$2" msg="${3:-}"
    if [[ "$actual" != "$expected" ]]; then
        log_fail "${msg:-values differ}: expected '$expected', got '$actual'"
    fi
}

# assert_contains <haystack> <needle> [<message>]
assert_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" != *"$needle"* ]]; then
        log_fail "${msg:-substring missing}: '$needle' not in \"$haystack\""
    fi
}

# assert_not_contains <haystack> <needle> [<message>]
assert_not_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" == *"$needle"* ]]; then
        log_fail "${msg:-unexpected substring present}: '$needle' in \"$haystack\""
    fi
}

# describe_exit <code> -- "143 (KILLED by SIGTERM)" rather than a bare "143".
#
# A BARE NUMBER SENDS THE READER TO THE WRONG PLACE. 143 is 128+15: nothing in the
# subject chose it, something killed the subject, and a reader who does not do
# that arithmetic in their head goes looking for the branch that returns 143.
# There is none. 160 is outside the band on purpose -- 128+32 is past the last
# real signal, so a genuine exit status of 159 or above is left alone rather than
# renamed into a signal that does not exist.
describe_exit() {
    local code="$1" n name
    if [[ "$code" -gt 128 && "$code" -lt 160 ]]; then
        n=$((code - 128))
        case "$n" in
            1) name=SIGHUP ;; 2) name=SIGINT ;; 3) name=SIGQUIT ;; 6) name=SIGABRT ;;
            9) name=SIGKILL ;; 11) name=SIGSEGV ;; 13) name=SIGPIPE ;; 14) name=SIGALRM ;;
            15) name=SIGTERM ;; 24) name=SIGXCPU ;; 25) name=SIGXFSZ ;;
            *) name="signal $n" ;;
        esac
        printf '%s (KILLED by %s)' "$code" "$name"
    else
        printf '%s' "$code"
    fi
}

# assert_exit_code <expected> <actual> [<message>]
assert_exit_code() {
    local expected="$1" actual="$2" msg="${3:-}"
    if [[ "$actual" -ne "$expected" ]]; then
        log_fail "${msg:-wrong exit code}: expected $expected, got $(describe_exit "$actual")"
    fi
}

# with_temp_dir <fn> [args...]
#
# Creates a temp dir, sets TEMP to its path, invokes <fn> (which may reference
# TEMP), and cleans up on exit. Nests safely (each call makes a fresh dir).
with_temp_dir() {
    local fn="$1"
    shift
    local TEMP
    TEMP="$(mktemp -d)"
    # BLOCKER: expanding TEMP now is intentional — we want the specific temp path bound into the trap handler, not a reference that would read an empty variable after the function returns
    # shellcheck disable=SC2064
    # BLOCKER: expanding TEMP now is intentional — we want the specific path
    # captured in the trap, not the variable's later value
    trap "rm -rf '$TEMP'" EXIT
    "$fn" "$TEMP" "$@"
    rm -rf "$TEMP"
    trap - EXIT
}

# with_fake_gh <gh_output_file> <fn> [args...]
#
# Shims `gh` on PATH with a fake binary that cats <gh_output_file>. Use to
# isolate tests from GitHub API. <gh_output_file> should contain the exact
# stdout the real `gh api` call would produce.
with_fake_gh() {
    local output_file="$1"
    local fn="$2"
    shift 2
    local BIN
    BIN="$(mktemp -d)"
    cat >"$BIN/gh" <<FAKE
#!/bin/bash
cat "$output_file"
FAKE
    chmod +x "$BIN/gh"
    local OLD_PATH="$PATH"
    export PATH="$BIN:$PATH"
    "$fn" "$@"
    export PATH="$OLD_PATH"
    rm -rf "$BIN"
}

# assert_vacuous_tree_fails <runner_fn> <dir> <needle> <label>
#
# The anti-vacuity case every gate-test that takes a ROOT override owes: point
# the gate at an EMPTY tree and prove it reds. Without it the override is an
# escape hatch, and the gate that uses it reports clean for a corpus it never
# saw -- which is the whole failure class .ci/scripts/test/gates/
# `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py` exists to police.
#
# Extracted 2026-09-02 because a third copy appeared and check:ci-shape-
# duplication caught it. Only the `run_check`-shaped harnesses fit: the runner
# must return the gate's EXIT CODE and leave its output in $LAST_OUT. A harness
# whose runner returns the output on stdout instead (test_gate_bws_map.py's
# run_gate) has a different contract and keeps its own copy -- one copy is not
# duplication, and forcing one return contract onto two is how a shared helper
# becomes worse than the repetition it replaced.
assert_vacuous_tree_fails() {
    local runner_fn="$1" dir="$2" needle="$3" label="$4"
    mkdir -p "$dir/empty"
    local rc=0
    "$runner_fn" "$dir/empty" || rc=$?
    assert_exit_code 1 "$rc" "$label"
    assert_contains "$LAST_OUT" "$needle" "says the check has nothing to assert"
    log_pass "empty tree fails (anti-vacuity), it does not pass silently"
}

# with_fake_bin <spec> <fn> [args...]
#
# Runs <fn> with PATH replaced by a temp directory holding ONLY the binaries <spec>
# names. Everything else -- docker, node, npm, npx, nvcc, aws, ssh, rsync, curl, wget --
# is then absent by construction rather than by hope, which is what lets a gate test for
# code that drives a GPU, a VM and an S3 bucket run in a few seconds on a CI runner that
# has none of them.
#
# WHY A DENYLIST WOULD NOT DO. The obvious version shadows the handful of binaries a test
# means to avoid and leaves the rest of PATH intact. That proves nothing about the
# binaries nobody thought to name, and the interesting failures are exactly those: a
# module that quietly reaches for `curl` on a machine that happens to have it. Emptying
# PATH and re-admitting by name inverts the burden, so a new dependency announces itself
# as a "command not found" in the test rather than as a silent success.
#
# <spec> is a space-separated list of tokens:
#   name        a fake that RECORDS its argv and exits 0
#   name!<n>    a fake that records its argv and exits <n>
#   +name       the REAL binary, resolved from the caller's PATH and symlinked in
#
# The `+` form exists because shell code cannot run without some text utilities, and
# faking `grep` would test the fake. Admitting them BY NAME keeps the property that
# matters: the set of external commands a test tolerates is written down in the test.
#
# Inside <fn>: $FAKE_BIN_DIR is the directory on PATH, and fake_bin_record <name>
# prints what that fake was called with, one invocation per line.
with_fake_bin() {
    local spec="$1"
    local fn="$2"
    shift 2
    local FAKE_ROOT
    FAKE_ROOT="$(mktemp -d)"
    mkdir -p "$FAKE_ROOT/bin" "$FAKE_ROOT/records"
    export FAKE_BIN_DIR="$FAKE_ROOT/bin"
    export FAKE_BIN_RECORDS="$FAKE_ROOT/records"

    local token name code real
    for token in $spec; do
        if [[ "$token" == +* ]]; then
            name="${token#+}"
            real="$(command -v "$name" || true)"
            [[ -n "$real" ]] || log_fail "with_fake_bin: +$name requested but no such binary on PATH"
            ln -s "$real" "$FAKE_BIN_DIR/$name"
            continue
        fi
        name="${token%%!*}"
        code=0
        [[ "$token" == *"!"* ]] && code="${token#*!}"
        # The fake uses bash BUILTINS only. Reaching for printf(1) or tee(1) here would
        # need those on the very PATH this helper just emptied, so the recorder would
        # fail exactly in the environment it exists to create.
        cat >"$FAKE_BIN_DIR/$name" <<FAKE
#!/bin/bash
printf '%s\n' "\$*" >>"$FAKE_BIN_RECORDS/$name"
exit $code
FAKE
        chmod +x "$FAKE_BIN_DIR/$name"
    done

    # THE PROBE RUNS IN A SUBSHELL, and that is not a style choice. log_fail exits, and
    # an exit from inside a function that had already replaced PATH left the EXIT trap
    # with_temp_dir installed running `rm` with `rm` no longer reachable: a real failure
    # was followed by a spurious "rm: command not found" and a leaked temp dir. Changing
    # PATH only inside a subshell means the outer shell's PATH was never touched, so
    # nothing has to be put back on the way out.
    #
    # The cost is that <fn> cannot export state to its caller. None of the media gate
    # tests need to -- a probe asserts and returns -- and `set -e` still propagates a
    # subshell failure outward, so an assertion that fires still stops the test.
    (
        export PATH="$FAKE_BIN_DIR"
        "$fn" "$@"
    )
    unset FAKE_BIN_DIR FAKE_BIN_RECORDS
    rm -rf "$FAKE_ROOT"
}

# fake_bin_record <name>
#
# Every invocation of the fake <name> made since with_fake_bin started, one line per
# call, arguments joined by spaces. Empty output means it was never called, which is a
# claim worth asserting in its own right -- "nvcc was never invoked" is the whole point
# of the CUDA module's skip path.
#
# Pure bash: it is called while PATH holds only the fakes, so `cat` may not exist.
fake_bin_record() {
    local name="$1"
    local f="${FAKE_BIN_RECORDS:-}/$name"
    [[ -f "$f" ]] || return 0
    printf '%s\n' "$(<"$f")"
}

# ---------------------------------------------------------------------------
# THE RUNNING TALLY: `ok`, `no`, and one verdict.
#
# Three gate tests carried this byte-identical -- test-toolchain.sh,
# test-run-sh.sh and test-devbox-probes.sh, the last since retired -- each with
# its own `fails=0`,
# `count=0`, `ok()`, `no()` and a verdict block differing only in the subject
# label. They were diffed before this was written; there is no divergence.
#
# WHY THE VOCABULARY MOVED HERE RATHER THAN THE CALL SITES MOVING TO
# log_pass/log_fail: those three speak `ok`/`no` at roughly a hundred call
# sites. Rewriting them all to this file's older vocabulary is not a
# consolidation, it is a rewrite with its own defect budget, and the duplication
# being removed is the SCAFFOLDING, not the spelling.
#
# ALL THREE WERE CONVERTED IN ONE CHANGE, and that is a rule rather than a
# preference. .ci/scripts/lib/gate-controls.sh was extracted for this same shape
# after check:ci-shape-duplication caught a `_c()` tally at three copies -- and
# the extraction converted ONE. That took the count to two, under the gate's
# threshold of three, so the gate went quiet while the new library's own header
# asserted the job was done. The other two were found months later by a
# different route. Converting a subset is how a gate gets silenced instead of
# satisfied.
tally_fails=0
tally_count=0

ok() {
    tally_count=$((tally_count + 1))
    echo "PASS: $1"
}

no() {
    tally_count=$((tally_count + 1))
    tally_fails=$((tally_fails + 1))
    echo "FAIL: $1" >&2
}

# The verdict, byte-identical to what the three printed by hand. Callers `exit`
# on its status so a caller that forgets cannot report green by falling off the
# end of the script.
tally_finish() {
    local subject="$1"
    echo
    if [[ "$tally_fails" -eq 0 ]]; then
        echo "✓ $subject: $tally_count control(s) passed"
        return 0
    fi
    echo "✗ $subject: $tally_fails of $tally_count control(s) failed" >&2
    return 1
}
