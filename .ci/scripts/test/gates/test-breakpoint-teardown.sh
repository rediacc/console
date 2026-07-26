#!/bin/bash
# Prove that breakpoint teardown kills what it started and NOTHING ELSE, and
# that it is safe to run again.
#
# THE BUG CLASS THIS TARGETS, by name. The deleted .github/actions/tmate action
# tore down with:
#     pkill -f "tmate.*new-session"
#     rm -f /tmp/tmate-*.log
# Both reach outside their own job. On a runner hosting two concurrent jobs,
# the first one to finish killed the other's live session and deleted its logs,
# and the victim job saw an unexplained disconnect. A pattern-kill cannot tell
# "my process" from "a process that looks like mine", so
# .ci/breakpoint/lib/breakpoint-common.sh records PIDs and kills only those.
#
# That is a property no amount of reading proves, so this file starts REAL
# processes: some recorded in the state dir, one deliberately not, and then
# checks which ones survive.
#
# Idempotence gets the same treatment. Teardown runs from `if: always()` and
# again from the nightly sweeper, so "already clean" is the NORMAL second call.
# A second run that exits 1 turns every swept session into a red workflow, and
# a red-by-default gate is one nobody reads.
#
# HOME is a temp dir in every invocation below, deliberately: stop-breakpoint.sh
# ends with `rm -f ~/.cloudflared/*.json`, which on a developer laptop would
# take out real cloudflared credentials. See the FINDING note on that in the
# summary; this file must not be the thing that demonstrates it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

STOP="$REPO_ROOT/.ci/breakpoint/scripts/stop-breakpoint.sh"
WORKFLOW="$REPO_ROOT/.ci/breakpoint/workflow/breakpoint.yml"

[[ -x "$STOP" ]] || log_fail "subject under test is missing or not executable: $STOP"

# bp_alive <pid>
# A killed child of THIS shell is a zombie until it is reaped, and `kill -0`
# succeeds on a zombie -- so the naive liveness test reports every successfully
# killed process as still running. Read the process state instead.
bp_alive() {
    local pid="$1" state
    kill -0 "$pid" 2>/dev/null || return 1
    state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
    [[ "$state" == Z* ]] && return 1
    [[ -n "$state" ]] || return 1
    return 0
}

# bp_wait_gone <pid> -- poll for up to ~10s, then give up. Bounded on purpose:
# an unbounded `wait` on a process teardown failed to kill hangs the suite
# instead of failing it.
bp_wait_gone() {
    local pid="$1" i
    for ((i = 0; i < 20; i++)); do
        bp_alive "$pid" || return 0
        sleep 0.5
    done
    return 1
}

# start_sleeper -- background `sleep`, pid on stdout.
#
# The >/dev/null is load-bearing, not tidiness: this function is called through
# command substitution, so a child that inherits the substitution's stdout pipe
# keeps it open and `$(start_sleeper)` blocks for the full 300s.
start_sleeper() {
    sleep 300 >/dev/null 2>&1 &
    echo $!
}

# record_pid <state-dir> <name> <pid> -- write the pidfile exactly as
# bp_record_pid does, without sourcing breakpoint-common.sh (the test must
# exercise the FILE LAYOUT contract, not share an implementation with it).
record_pid() {
    mkdir -p "$1/pids"
    echo "$3" >"$1/pids/$2.pid"
}

# run_stop <tmp> [extra env...] -- invoke teardown against the temp state dir.
# Sets STOP_RC and STOP_OUT.
STOP_RC=0
STOP_OUT=""
run_stop() {
    local tmp="$1"
    shift
    STOP_RC=0
    STOP_OUT="$(env -i PATH="$PATH" HOME="$tmp/home" RUNNER_TEMP="$tmp" "$@" \
        bash "$STOP" 2>&1)" || STOP_RC=$?
}

# =============================================================================
# a) recorded pids are killed
# =============================================================================
test_kills_recorded_pids() {
    local tmp="$1" state pid_tmate pid_origin
    mkdir -p "$tmp/home"
    state="$tmp/breakpoint"

    pid_tmate="$(start_sleeper)"
    pid_origin="$(start_sleeper)"
    record_pid "$state" tmate "$pid_tmate"
    record_pid "$state" origin "$pid_origin"

    bp_alive "$pid_tmate" || log_fail "fixture is broken: sleeper $pid_tmate never started"
    bp_alive "$pid_origin" || log_fail "fixture is broken: sleeper $pid_origin never started"

    run_stop "$tmp"
    assert_exit_code 0 "$STOP_RC" "teardown with live recorded pids must succeed: $STOP_OUT"

    bp_wait_gone "$pid_tmate" || log_fail "tmate pid $pid_tmate survived teardown"
    bp_wait_gone "$pid_origin" || log_fail "origin pid $pid_origin survived teardown"
    wait "$pid_tmate" 2>/dev/null || true
    wait "$pid_origin" 2>/dev/null || true

    [[ -d "$state" ]] && log_fail "teardown left the state dir $state behind"
    log_pass "teardown kills every recorded pid and removes the state dir"
}

# =============================================================================
# b) a second teardown is not an error
# =============================================================================
test_second_teardown_is_clean() {
    local tmp="$1" state pid
    mkdir -p "$tmp/home"
    state="$tmp/breakpoint"

    pid="$(start_sleeper)"
    record_pid "$state" cloudflared "$pid"

    # GITHUB_RUN_ID is set for BOTH calls so the second one still has a
    # derivable identity and walks the whole script (the sweeper's shape) rather
    # than taking the early "nothing to do" exit. That is the call that has to
    # be green, and the early exit would hide it.
    run_stop "$tmp" GITHUB_RUN_ID=990011
    assert_exit_code 0 "$STOP_RC" "first teardown must succeed: $STOP_OUT"
    bp_wait_gone "$pid" || log_fail "recorded pid $pid survived the first teardown"
    wait "$pid" 2>/dev/null || true

    run_stop "$tmp" GITHUB_RUN_ID=990011
    assert_exit_code 0 "$STOP_RC" "SECOND teardown against clean state must exit 0, not 1: $STOP_OUT"
    log_pass "a second teardown over already-clean state exits 0 (sweeper re-run is normal)"
}

# =============================================================================
# c) no state dir at all
# =============================================================================
test_no_state_dir_at_all() {
    local tmp="$1"
    mkdir -p "$tmp/home"
    [[ -d "$tmp/breakpoint" ]] && log_fail "fixture is broken: the state dir should not exist yet"

    run_stop "$tmp"
    assert_exit_code 0 "$STOP_RC" "teardown with no state at all must exit 0: $STOP_OUT"
    assert_contains "$STOP_OUT" "nothing to stop" "it should say why there was nothing to do"
    log_pass "teardown with no state dir and no derivable identity exits 0"
}

# =============================================================================
# d) a stale pidfile
# =============================================================================
test_stale_pidfile_is_not_an_error() {
    local tmp="$1" state pid
    mkdir -p "$tmp/home"
    state="$tmp/breakpoint"

    # A pid that has already exited: the normal state after a runner reboot, or
    # when the process died on its own before teardown ran.
    sleep 0.1 &
    pid=$!
    wait "$pid" 2>/dev/null || true
    bp_alive "$pid" && log_fail "fixture is broken: pid $pid should be gone already"

    record_pid "$state" tmate "$pid"
    record_pid "$state" cloudflared "$pid"

    run_stop "$tmp"
    assert_exit_code 0 "$STOP_RC" "a stale pidfile must not fail teardown: $STOP_OUT"
    assert_not_contains "$STOP_OUT" "No such process" "a stale pid must not leak a kill(1) error"
    log_pass "a stale pidfile is handled silently and exits 0"
}

# =============================================================================
# e) BLAST RADIUS -- the assertion the deleted tmate action would have failed
# =============================================================================
test_does_not_touch_unrecorded_processes() {
    local tmp="$1" state pid_mine pid_theirs
    mkdir -p "$tmp/home"
    state="$tmp/breakpoint"

    pid_mine="$(start_sleeper)"
    # A process breakpoint never started and never recorded. It is the same
    # `sleep` binary with the same argv as the recorded one, on purpose: that is
    # exactly what a concurrent job's tmate looked like to `pkill -f`.
    pid_theirs="$(start_sleeper)"
    record_pid "$state" tmate "$pid_mine"

    run_stop "$tmp"
    assert_exit_code 0 "$STOP_RC" "teardown must succeed: $STOP_OUT"
    bp_wait_gone "$pid_mine" || log_fail "recorded pid $pid_mine survived teardown"
    wait "$pid_mine" 2>/dev/null || true

    if ! bp_alive "$pid_theirs"; then
        log_fail "BLAST RADIUS: teardown killed unrecorded pid $pid_theirs (a concurrent job's process)"
    fi
    kill "$pid_theirs" 2>/dev/null || true
    wait "$pid_theirs" 2>/dev/null || true
    log_pass "an identical-looking process breakpoint never recorded is left alive"
}

# =============================================================================
# f) static: neither banned construct is back
# =============================================================================
test_no_pattern_kill_or_tmp_glob() {
    local body
    body="$(cat "$STOP")"

    # Present in the header comment as an explanation of what NOT to do, so the
    # grep has to look at code only.
    local code
    code="$(grep -vE '^[[:space:]]*#' "$STOP")"

    assert_not_contains "$code" "pkill -f" "pkill -f reaches into a concurrent job's processes"
    assert_not_contains "$code" "pkill" "no pattern-kill of any shape"
    assert_not_contains "$code" "rm -f /tmp/" "an rm glob under /tmp reaches another job's files"
    assert_not_contains "$code" "killall" "killall is a pattern-kill by another name"

    # And the reason is written down where the next editor will see it.
    assert_contains "$body" "KILLS ONLY RECORDED PIDS" "the header must state the rule it obeys"
    log_pass "stop-breakpoint.sh contains no pkill / killall / rm -f /tmp glob"
}

# =============================================================================
# g) static: teardown actually runs on the paths that matter
# =============================================================================
test_workflow_teardown_is_always() {
    local step
    [[ -f "$WORKFLOW" ]] || log_fail "workflow template is missing: $WORKFLOW"

    # `if: always()` is what makes teardown run after a FAILED or CANCELLED
    # session. Without it the tunnel outlives the job on exactly the runs where
    # something went wrong -- the runs most likely to have left a shell open.
    step="$(grep -A 2 '^      - name: Teardown$' "$WORKFLOW")"
    [[ -n "$step" ]] || log_fail "no 'Teardown' step found in $WORKFLOW"
    assert_contains "$step" "if: always()" "the Teardown step must carry if: always()"
    log_pass "workflow Teardown step is guarded by if: always()"
}

with_temp_dir test_kills_recorded_pids
with_temp_dir test_second_teardown_is_clean
with_temp_dir test_no_state_dir_at_all
with_temp_dir test_stale_pidfile_is_not_an_error
with_temp_dir test_does_not_touch_unrecorded_processes
test_no_pattern_kill_or_tmp_glob
test_workflow_teardown_is_always
