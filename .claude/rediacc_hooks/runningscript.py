"""Shared machinery for the two "is a shell script currently running" guards.

WHY THIS EXISTS NOW AND NOT AT PORT TIME. `block_bash_write_to_running_script.py` (pre-bash) and `block_edit_of_running_script.py` (pre-edit) each carried their own copy of `pattern_for` and the pgrep loop, because their bash twins duplicated them too and a port whose job was fidelity did not get to unify what its twin kept apart: each half was judged against its own oracle, and unifying
them would have made a passing differential prove nothing about which guard actually ran. Both twins' own docstrings named the day this was allowed to change: "unifying is a P6 change, once there is no twin left to diverge from." PLAN-retire-bash-oracles A3 deleted the last twin, so this is that change.

WHAT MOVED HERE, verbatim except for the one difference that was a bug rather than a style choice: `HOOK_CHAIN`, `META`, `pattern_for` and `live_shells`. `block_edit_of_running_script.py`'s `pattern_for` built its regex through `hookio.rx()` and its sibling built the identical string by hand-concatenating `hookio.SPACE`; the two produce byte-identical patterns, and this module keeps the
`rx()` form since that is the one `hookio.rx`'s own docstring asks every guard with a space-class fragment to use.

WHAT DID NOT MOVE. Each guard keeps its own `run()`, its own `MESSAGE`, its own `EDGE_CASES`/`FIXTURES`/`ENVS` and its own fixture world -- the pre-edit guard's `ENVS`-driven two-process world is not shared with the pre-bash guard's, because the two chains see different payload shapes and drive the fixture through different entry points. Only the pattern-building and the process-table
scan are one piece of logic now instead of two.
"""

import re

from rediacc_hooks import hookio, proc

# `.claude/hooks/<chain>/` or the chain head itself: a hook-chain sibling evaluating THIS very call is not a running job, it is the chain doing its job, and excluding it is not a loophole -- see either guard's own docstring for the incident this closes.
HOOK_CHAIN = r"\.claude/hooks/((pre-bash|pre-edit|pre-ask|post-bash)/|chain-head\.sh)"

# The characters `sed 's/[.[\*^$()+?{}|]/\\&/g'` escapes. Note that inside a
# POSIX bracket expression a backslash is an ORDINARY character, so `\` is a member of the set rather than an escape.
META = r"([.\[\\*^$()+?{}|])"


def pattern_for(base):
    """`(^|[/[:space:]])[<first>]<escaped rest>`, built exactly as the bash twins did.

    BRACKET CLASS ON THE FIRST CHARACTER, and it is not decoration: without it this pgrep matches the shell running this very hook, whose command line contains the path it was handed. That is the self-matching trap block-self-matching-pgrep.sh exists for.

    ANCHOR TO A PATH BOUNDARY. A bare basename matches any process whose command line merely CONTAINS it as a substring (`ver.sh` inside a running `wslServer.sh`). The basename must start at the beginning, after a `/`, or after whitespace.

    ESCAPE THE DOTS. `.` is a regex wildcard and the basename was interpolated raw, so a one-letter name plus the shell suffix produced `[x].sh` -- which for `b` matches **/bin/bash**, i.e. every bash process alive. Measured on the twin 2026-09-01: an edit was refused naming `/bin/bash --init-file ...` as the job it would corrupt, with no such script running.
    """
    esc = re.sub(META, r"\\\1", base[1:])
    return hookio.rx(r"(^|[/{S}])[") + base[:1] + r"]" + esc


def live_shells(pat, limit):
    """The `for RPID in $(pgrep -f -- "$PAT")` loop, as its accumulated text.

    `pgrep -af` matches any process whose ARGUMENTS mention the name, which is the very trap this guard exists to prevent, wearing a different hat: a running `claude -p '<huge prompt text>'` invocation can carry a filename embedded in its prompt and be scored as "executing" it, though no interpreter is running the script at all.

    A process is RUNNING the script only if an interpreter is executing it. So require the matching process to BE a shell, and the name to sit in the first few argv slots where a script argument lives, rather than buried in a prose payload.
    """
    try:
        pids = proc.pgrep_full(pat)
    except (proc.ProcError, re.error):
        # `pgrep ... 2>/dev/null` in a `$( )`: a pattern pgrep refuses, or a process table it cannot read, both yield an empty word list and the loop simply never runs.
        pids = []
    running = ""
    for rpid in pids:
        if not proc.is_shell(rpid):
            continue
        rargs = proc.cmdline_tr(rpid)
        if rargs is None:
            rargs = ""
        # `cut -d' ' -f1-4`: the first four SPACE-delimited fields, with runs of spaces counting as empty fields exactly as cut reads them.
        first4 = " ".join(rargs.split(" ")[:4])
        if not hookio.grep_q(pat, first4):
            continue
        if hookio.grep_q(HOOK_CHAIN, rargs):
            continue
        running += "%d %s\n" % (rpid, rargs[:80])
    # `$(printf '%s' "$running" | head -N)`
    kept = running.split("\n")[:limit] if running != "" else []
    return hookio._command_substitution("\n".join(kept))
