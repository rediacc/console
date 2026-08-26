#!/bin/bash
# `worktree remove` must tear the devbox down BEFORE it deletes the directory.
#
# THE BUG THIS PINS. The container is found by a label whose VALUE is the
# worktree's absolute path (com.rediacc.devbox.worktree, .ci/lib/devbox.sh).
# `remove_worktree` killed tmux, deleted the directory and deleted the branch --
# and never stopped the devbox. After the directory is gone, devbox_worktree()
# (`cd "$path" && pwd -P`) yields nothing, the filter becomes
# `label=...worktree=`, `docker ps -aq` matches nothing, and teardown reports
# "No devbox container for this worktree" and returns 0. The container is
# orphaned with nothing able to name it again.
#
# ORDER IS THE INVARIANT, not presence. A teardown that runs AFTER
# `git worktree remove` looks identical in a call log that only checks "was
# devbox remove called?" -- and it leaks every time. So this asserts the
# SEQUENCE, the same way check-setup-idempotency's submodule check does.
#
# HERMETIC: git, docker and run.sh are all shimmed onto PATH. Nothing here
# touches a real worktree or a real container.
#
# WHAT THIS CANNOT SEE: it drives the lifted `remove_worktree` body, so it does
# not prove that `prune` reaches the same function, nor that devbox_remove
# actually removes anything -- devbox.sh's own gates own that.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

SUT="$REPO_ROOT/scripts/dev/worktree.sh"
[[ -f "$SUT" ]] || log_fail "subject under test is missing: $SUT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Build a harness that lifts the two real function bodies and drives them
# against shims, so the SHIPPED ordering is what runs -- not a copy of it.
build_harness() { # build_harness <docker-info-rc> <devbox-remove-rc>
    local docker_rc="$1" remove_rc="$2" dir="$WORK/h"
    rm -rf "$dir"
    mkdir -p "$dir/bin"

    cat >"$dir/bin/docker" <<DOCKER
#!/bin/bash
[ "\$1" = "info" ] && exit $docker_rc
exit 0
DOCKER
    cat >"$dir/bin/git" <<'GIT'
#!/bin/bash
for a in "$@"; do
  if [ "$a" = "worktree" ]; then echo "git-worktree" >>"$CALLS"; fi
done
exit 0
GIT
    cat >"$dir/bin/tmux" <<'TMUX'
#!/bin/bash
exit 1
TMUX
    cat >"$dir/run.sh" <<RUNSH
#!/bin/bash
echo "devbox-remove" >>"\$CALLS"
exit $remove_rc
RUNSH
    chmod +x "$dir/bin/docker" "$dir/bin/git" "$dir/bin/tmux" "$dir/run.sh"

    {
        echo 'set -u'
        echo 'log_info() { :; }'
        echo 'log_warn() { :; }'
        echo 'log_error() { echo "ERR: $*" >&2; }'
        echo 'tmux_session_exists() { return 1; }'
        echo "ROOT_DIR='$dir'"
        # Lift the REAL bodies, column-0 `name() {` .. column-0 `}`.
        sed -n '/^devbox_teardown_available() {/,/^}/p' "$SUT"
        sed -n '/^remove_worktree() {/,/^}/p' "$SUT"
    } >"$dir/harness.sh"

    grep -q 'remove_worktree()' "$dir/harness.sh" ||
        log_fail "could not lift remove_worktree from $SUT (its shape changed)"
    grep -q 'devbox_teardown_available()' "$dir/harness.sh" ||
        log_fail "could not lift devbox_teardown_available from $SUT"
    echo "$dir"
}

run_removal() { # run_removal <dir>; sets RC and CALLS_OUT
    local dir="$1"
    : >"$dir/calls"
    RC=0
    CALLS="$dir/calls" PATH="$dir/bin:$PATH" \
        bash -c "source '$dir/harness.sh'; remove_worktree '$dir/wt' sess br" \
        >/dev/null 2>&1 || RC=$?
    CALLS_OUT="$(cat "$dir/calls" 2>/dev/null || true)"
}

test_teardown_runs_before_the_directory_is_deleted() {
    log_test "devbox teardown must precede git worktree remove"
    local dir
    dir="$(build_harness 0 0)"
    run_removal "$dir"
    [[ "$RC" -eq 0 ]] || log_fail "a clean removal should succeed, got rc=$RC"
    # ANTI-VACUITY: both calls must actually be present, or "order" is trivial.
    grep -q 'devbox-remove' <<<"$CALLS_OUT" || log_fail "devbox teardown never ran at all"
    grep -q 'git-worktree' <<<"$CALLS_OUT" || log_fail "git worktree remove never ran; the order test is vacuous"
    local first
    first="$(head -1 <<<"$CALLS_OUT")"
    [[ "$first" == "devbox-remove" ]] ||
        log_fail "ORDER WRONG: '$first' ran first. After the directory is gone the container's label value is unrecoverable and it is orphaned forever."
    log_pass "teardown runs first: $(tr '\n' ' ' <<<"$CALLS_OUT")"
}

test_failed_teardown_aborts_the_removal() {
    log_test "a FAILED teardown must abort, not press on"
    local dir
    dir="$(build_harness 0 1)"
    run_removal "$dir"
    [[ "$RC" -ne 0 ]] ||
        log_fail "removal returned 0 despite teardown failing; refusing is recoverable, orphaning is not"
    grep -q 'git-worktree' <<<"$CALLS_OUT" &&
        log_fail "the worktree was deleted anyway after teardown failed -- this is the orphan"
    log_pass "a failed teardown aborts before the directory is touched"
}

test_no_docker_keeps_todays_behaviour() {
    log_test "a docker-less machine must behave exactly as before"
    # `docker info` failing means no daemon: there is no container to orphan, so
    # removal must proceed rather than start refusing where it always worked.
    local dir
    dir="$(build_harness 1 1)"
    run_removal "$dir"
    [[ "$RC" -eq 0 ]] || log_fail "removal must still succeed with no docker daemon, got rc=$RC"
    grep -q 'devbox-remove' <<<"$CALLS_OUT" &&
        log_fail "teardown was attempted with no docker daemon"
    grep -q 'git-worktree' <<<"$CALLS_OUT" ||
        log_fail "the worktree was NOT removed on a docker-less machine; behaviour changed"
    log_pass "no daemon: teardown skipped, removal proceeds"
}

test_control_ordering_can_fail() {
    log_test "CONTROL: move teardown after the delete and the order test MUST go red"
    # By CONSTRUCTION: a harness whose remove_worktree calls them in the WRONG
    # order. If the assertion cannot see that, it is not testing order.
    local dir="$WORK/ctl"
    rm -rf "$dir"
    mkdir -p "$dir/bin"
    cat >"$dir/harness.sh" <<'CTL'
set -u
remove_worktree() {
  echo "git-worktree" >>"$CALLS"
  echo "devbox-remove" >>"$CALLS"
  return 0
}
CTL
    : >"$dir/calls"
    CALLS="$dir/calls" bash -c "source '$dir/harness.sh'; remove_worktree a b c" >/dev/null 2>&1
    local first
    first="$(head -1 <"$dir/calls")"
    [[ "$first" == "git-worktree" ]] ||
        log_fail "CONTROL DID NOT FIRE: the wrong-order harness did not produce the wrong order"
    log_pass "control fires: the assertion distinguishes the two orderings"
}

test_teardown_runs_before_the_directory_is_deleted
test_failed_teardown_aborts_the_removal
test_no_docker_keeps_todays_behaviour
test_control_ordering_can_fail

echo
log_pass "worktree devbox-teardown gate: 4/4"
echo "  Blind spot: drives the lifted remove_worktree body only. It does not"
echo "  prove prune reaches the same function, nor that devbox_remove actually"
echo "  removes a container -- devbox.sh's own gates own that."
