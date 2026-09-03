# shellcheck shell=bash
# BASH_ENV for the resource profiler: re-exec this shell under bashcov-sup.
#
# WHY A SUPERVISOR AND NOT AN EXIT TRAP. Bash has ONE EXIT trap slot; a script's own
# `trap ... EXIT` silently replaces anything set here, `exec` bypasses it entirely,
# and the single richest target (.claude/hooks/stop/test-worklist-v5.sh:60) has such
# a trap. A record written by a PARENT the script cannot touch survives all of that,
# `set -o posix`, `builtin trap`, and `kill -9`. Verified on the real target: 889/0
# with 152 records where the trap design produced zero.
#
# CONTRACTS. Never changes the exit code (the supervisor exits like the child,
# re-raising a signal). Never prints. Never reads argv beyond re-exec'ing it; the
# record carries pids, counters and kernel symbol names only. Every path ends in `:`
# so the status of the last command here cannot leak into an empty script's status.
# Off switch: WORKLIST_PROFILE=off. Skipped when interactive or when no supervisor
# binary is on PATH. Hooks under .claude/hooks/ ARE profiled (operator ruling).
{
    __bashcov_x=0
    [[ $- == *x* ]] && __bashcov_x=1
    set +x
} 2>/dev/null
if [[ ${WORKLIST_PROFILE:-} == off ]]; then
    :
elif [[ ${__BASHCOV_SUP:-} == "$PPID" ]]; then
    unset __BASHCOV_SUP
elif [[ $- != *i* ]] && {
    # Explicit paths, not PATH: the settings env block delivers BASH_ENV to the tool
    # shell but a PATH set there did not arrive (verified 2026-09-03), and a lookup
    # that depends on the caller's PATH would silently profile nothing.
    __bashcov_bin="$HOME/.local/share/rediacc/bin/bashcov-sup"
    [[ -x $__bashcov_bin ]] || __bashcov_bin=/usr/local/bin/bashcov-sup
    [[ -x $__bashcov_bin ]]
}; then
    # Records go to the time-based corpus: ~/.claude/resprofile/<repo-slug>/<day>/bash.jsonl,
    # keyed on the repo this file lives in so a second worktree gets its own folder.
    __bashcov_repo=${BASH_SOURCE[0]%/.claude/hooks/profile/bash_env.sh}
    __bashcov_slug=${__bashcov_repo#/}
    __bashcov_slug=${__bashcov_slug//\//-}
    printf -v __bashcov_day '%(%Y-%m-%d)T' -1
    __bashcov_dir="$HOME/.claude/resprofile/$__bashcov_slug/$__bashcov_day"
    [[ -d $__bashcov_dir ]] || mkdir -p "$__bashcov_dir" 2>/dev/null
    export BASHCOV_OUT="$__bashcov_dir/bash.jsonl"
    __bashcov_f=''
    for __bashcov_c in a b e f k m n p t u v B C E H P T; do [[ $- == *$__bashcov_c* ]] && __bashcov_f+=$__bashcov_c; done
    ((__bashcov_x)) && __bashcov_f+=x
    __bashcov_o=()
    [[ -o pipefail ]] && __bashcov_o=(-o pipefail)
    [[ -n $__bashcov_f ]] && __bashcov_f=-$__bashcov_f
    if [[ -n ${BASH_EXECUTION_STRING+x} ]]; then
        exec "$__bashcov_bin" -- "$BASH" $__bashcov_f "${__bashcov_o[@]}" -c "$BASH_EXECUTION_STRING" "$0" "$@"
    elif [[ $0 != "$BASH" && $0 != bash && -r $0 && -f $0 ]]; then
        exec "$__bashcov_bin" -- "$BASH" $__bashcov_f "${__bashcov_o[@]}" -- "$0" "$@"
    else
        exec "$__bashcov_bin" -- "$BASH" $__bashcov_f "${__bashcov_o[@]}" -s -- "$@"
    fi
fi
if ((__bashcov_x)); then set -x; else :; fi
