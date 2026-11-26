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
# THE PER-LEASE TMPDIR (agent/plans/PLAN-host-temp-disposal.md D1), before anything that re-execs, so the export rides every shell and its children. A shell that STARTS with `$PWD` inside `*/.claude/worktrees/<id>` gets TMPDIR set to the lease's own directory `<base>/<first 8 characters of the id without "agent-">` (`make_lease` creates it; base is `$REDIACC_LEASE_TMP_BASE` or `/var/tmp/r<uid>`). The test runs once, at shell start, so a shell that later `cd`s into a lease keeps the TMPDIR it started with, and its children inherit that. It acts only while TMPDIR is unset or still the harness's `$CLAUDE_CODE_TMPDIR`: a TMPDIR that pytest, vitest or a gate narrowed is left alone. The base and the lease dir must each be a real directory (not a symlink) owned by this uid, the refusal `_private_dir` in worktree_lease.py applies, since `/var/tmp` is world-writable and another local user can plant either name; anything else is never exported. The mode bits are not read here (bash has no stat builtin, and a fork breaks the cost contract): `_private_dir` refuses group or other bits when the lease is made, and only the owner or root can loosen them afterwards. COST: parameter expansions and file tests, no fork, so the steady state stays free.
case ${PWD:-} in
    */.claude/worktrees/?*)
        if [[ -z ${TMPDIR:-} || ${TMPDIR:-} == "${CLAUDE_CODE_TMPDIR:-}" ]]; then
            __lt_id=${PWD#*/.claude/worktrees/}
            __lt_id=${__lt_id%%/*}
            __lt_id=${__lt_id#agent-}
            __lt_base=${REDIACC_LEASE_TMP_BASE:-/var/tmp/r$UID}
            __lt_dir=$__lt_base/${__lt_id:0:8}
            if [[ ! -L $__lt_base && -d $__lt_base && -O $__lt_base && ! -L $__lt_dir && -d $__lt_dir && -O $__lt_dir ]]; then
                export TMPDIR=$__lt_dir
            fi
            unset __lt_id __lt_base __lt_dir
        fi
        ;;
    *) ;;
esac
# THE .pth LOADER (agent/plans/PLAN-tooling-speed.md D6), before the supervisor: a
# `PYTHONPATH=...` command replaces the path exported below, and a .pth file in the
# user site directory reaches python3 anyway. This writes one there, beside a copy
# of pth_loader.py, and appends this repo to ~/.claude/resprofile/pth-roots, the
# only roots the loader acts for (pth_loader.py says why it never walks up from the
# cwd instead). Its own supervisor-free condition, since a shell with no bashcov-sup
# still runs python3; the re-exec'd child (__BASHCOV_SUP is its parent) finds it
# done already. Inline rather than a sourced file: these trees are Python, and this
# file is the one bash shim BASH_ENV needs (.language-policy-allowlist).
#
# COST, because every non-interactive bash runs this. The steady state is three
# `read`s and no fork: the user site path is cached in ~/.claude/resprofile/pth-site,
# and the loader is copied only when its version line differs. python3 runs once,
# to learn the user site path, and only while no cached path names an existing
# directory; it is the user site of whichever python3 was on PATH then. Every
# read and write puts `2>/dev/null` BEFORE its own redirect, since bash reports a
# failed open on the stderr in force when it opens, and a file is tested with -f,
# since a directory in its place reads as a read error.
if [[ ${WORKLIST_PROFILE:-} != off && $- != *i* && ${__BASHCOV_SUP:-} != "$PPID" ]]; then
    __rp_repo=${BASH_SOURCE[0]%/.claude/hooks/profile/bash_env.sh}
    __rp_dir="$HOME/.claude/resprofile"
    __rp_src="$__rp_repo/.claude/hooks/profile/pth_loader.py"
    if [[ -n $__rp_repo && -r $__rp_src ]]; then
        __rp_have=0
        if [[ -f $__rp_dir/pth-roots ]]; then
            while IFS= read -r __rp_line; do
                [[ $__rp_line == "$__rp_repo" ]] && {
                    __rp_have=1
                    break
                }
            done 2>/dev/null <"$__rp_dir/pth-roots"
        fi
        if ((! __rp_have)); then
            mkdir -p "$__rp_dir" 2>/dev/null && printf '%s\n' "$__rp_repo" 2>/dev/null >>"$__rp_dir/pth-roots"
        fi
        __rp_site=''
        [[ -f $__rp_dir/pth-site ]] && IFS= read -r __rp_site 2>/dev/null <"$__rp_dir/pth-site"
        if [[ -z $__rp_site || ! -d $__rp_site ]]; then
            __rp_site=$(WORKLIST_PROFILE=off python3 -c 'import site; print(site.getusersitepackages() if site.ENABLE_USER_SITE else "")' 2>/dev/null)
            if [[ -n $__rp_site ]] && mkdir -p "$__rp_site" "$__rp_dir" 2>/dev/null; then
                printf '%s\n' "$__rp_site" 2>/dev/null >"$__rp_dir/pth-site"
            fi
        fi
        if [[ -n $__rp_site && -d $__rp_site ]]; then
            __rp_want='' __rp_got=''
            IFS= read -r __rp_want 2>/dev/null <"$__rp_src"
            [[ -f $__rp_site/rediacc_resprofile_loader.py ]] && IFS= read -r __rp_got 2>/dev/null <"$__rp_site/rediacc_resprofile_loader.py"
            if [[ $__rp_want != "$__rp_got" ]]; then
                cp -f "$__rp_src" "$__rp_site/rediacc_resprofile_loader.py.$$" 2>/dev/null &&
                    mv -f "$__rp_site/rediacc_resprofile_loader.py.$$" "$__rp_site/rediacc_resprofile_loader.py" 2>/dev/null
            fi
            [[ -f $__rp_site/rediacc_resprofile.pth ]] ||
                printf 'import rediacc_resprofile_loader\n' 2>/dev/null >"$__rp_site/rediacc_resprofile.pth"
        fi
    fi
    unset __rp_repo __rp_dir __rp_src __rp_have __rp_line __rp_site __rp_want __rp_got
fi
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
    [[ -x $__bashcov_bin ]] &&
        # THE RE-EXEC RUNS "$BASH", AND "$BASH" IS DERIVED FROM argv[0]. A bash started
        # as `exec -a python3 bash -c ...` gets BASH=<python3 on PATH>, and the re-exec
        # below would replace the shell with that program, which then reads the -c
        # string as its own (measured 2026-10-27: a SyntaxError from python3). So the
        # shell is profiled only when "$BASH" is the very binary running, by inode
        # (`-ef` follows /proc/self/exe to the executable, with no fork); otherwise it
        # runs unprofiled, never as another program. No /proc means no profiling.
        [[ -n ${BASH:-} && $BASH -ef /proc/self/exe ]]
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
    # PYTHONPATH RIDES THE ONE SEAM THAT IS PROVEN TO ARRIVE. `sitecustomize.py` is
    # imported by `site` at interpreter startup, which is the only way to record a
    # plain `python3` without rewriting the command -- and a PreToolUse hook cannot
    # rewrite it. Measured 2026-09-03 before this line existed: three `python3 -c
    # pass` calls added ZERO records, so "every Python invocation leaves a record"
    # was false for anything that does not import wl_core.
    #
    # Delivered from HERE rather than from the settings env block for the reason the
    # comment above records: BASH_ENV arrives from that block, a PATH set there did
    # not. Prepended, never replacing: run.sh sets PYTHONPATH=src, and clobbering a
    # caller's value to profile it would be a profiler changing what it measures.
    # Cost, measured over 20 invocations each: 23.2 ms -> 26.5 ms per python3.
    __bashcov_py="$__bashcov_repo/.claude/hooks/profile/py"
    [[ -r $__bashcov_py/sitecustomize.py ]] &&
        export PYTHONPATH="$__bashcov_py${PYTHONPATH:+:$PYTHONPATH}"
    # THE SHAPE, and what it deliberately is NOT. The record needs an identity or
    # bash.jsonl cannot be ranked -- 35 MB a day whose only mention in the tree was
    # its own writer. `$0` is a path, which is public; BASH_EXECUTION_STRING is a
    # command line, which in a public repo can carry a secret, so it is never used.
    # A shell with no script gets a fixed literal, not its arguments.
    if [[ -n ${BASH_EXECUTION_STRING+x} ]]; then
        __bashcov_shape='sh:-c'
    elif [[ $0 != "$BASH" && $0 != bash && -r $0 && -f $0 ]]; then
        __bashcov_shape=${0#"$__bashcov_repo"/}
        [[ $__bashcov_shape == /* ]] && __bashcov_shape='<external>'
        __bashcov_shape="sh:$__bashcov_shape"
    else
        __bashcov_shape='sh:-s'
    fi
    export BASHCOV_SHAPE="$__bashcov_shape"
    # THE PER-CALL ID. One Bash tool call is one process tree, and bash.jsonl rows
    # carried nothing that groups them (grouping by parent pid gave a max of 1630,
    # not a per-call count). The first profiled shell of a call exports
    # `<pid>-<start ns>`; every descendant inherits it, so wl_resprofile's fold
    # counts one call's processes by id. A malformed inherited value is replaced, and so is a well-formed one whose pid is not an ancestor.
    # A well-formed id is kept only while the pid it names is one of this shell's own
    # ancestors (a walk up /proc/<pid>/stat, bounded, no fork): an id inherited from
    # a shell that is not in this call's tree (a parent that exported one, a daemon
    # started by an earlier call) would otherwise merge two calls into one count.
    __bashcov_keep=0
    if [[ ${BASHCOV_CALL:-} =~ ^([0-9]+)-[0-9]+$ ]]; then
        __bashcov_p=$$
        for __bashcov_c in {1..64}; do
            if [[ $__bashcov_p == "${BASH_REMATCH[1]}" ]]; then
                __bashcov_keep=1
                break
            fi
            ((__bashcov_p > 1)) || break
            read -r __bashcov_l 2>/dev/null <"/proc/$__bashcov_p/stat" || break
            __bashcov_l=${__bashcov_l##*) }
            __bashcov_l=($__bashcov_l)
            __bashcov_p=${__bashcov_l[1]:-0}
        done
    fi
    ((__bashcov_keep)) || {
        __bashcov_t=${EPOCHREALTIME:-0}
        export BASHCOV_CALL="$$-${__bashcov_t/./}000"
    }
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
