"""Block launching a long-lived waiter/watcher with a shell `&` instead of the
harness's run_in_background.

WHY. On 2026-08-08 a session launched wl_wait.py with a trailing `&`. A
shell-backgrounded process is untracked: the harness cannot notify on its
exit, so the waiter fires into the void and the session stops hearing
cross-session mail without any visible failure. The same session then spent
three rounds chasing "respawning" waiters that were its own pgrep wrappers
self-matching. Every instruction file already says run_in_background: true;
instructions demonstrably did not hold under load, so this hook does.

SCOPE IS DELIBERATELY NARROW: only the known long-lived instruments
(wl_wait.py today) followed by a backgrounding `&`. A general `&` ban would
be wrong -- `cmd1 & cmd2 & wait` fan-outs and `disown` teardowns are
legitimate. `&&` never matches (the regex requires a NON-& character or
end-of-line after the single `&`).

PORT NOTE ON THE awk STRIPPER'S UNINITIALISED STATE. `indoc` and `delim` are
never assigned before use, so the first record is judged with `indoc == 0` and
`delim == ""`. The port names them explicitly, which is the same behaviour
written down rather than inherited from the language.

PORT NOTE ON `print` VERSUS THE SUBSTITUTION. awk's `print` TERMINATES every
record it emits, input newline or not, and the surrounding `$( )` then strips
the trailing newlines again. Both steps are spelled out below (`_awk_out` then
`_command_substitution`) because a port that joined the records with newlines
would agree on every multi-line input and differ on a one-line one. `_awk_out`
is reached through `shellscan` rather than `hookio`: `hookio` re-exports the
primitives its own guards needed and awk's output rule was not one of them, and
a private second copy here would be exactly the drift `hookio`'s header argues
against.
"""

import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-shell-background-waiter.sh"
ORDER = 14

# NOT stripped when the heredoc feeds a shell (`| bash`, `| sh`, `bash <<`),
# because there the body IS the command and stripping it would open a bypass.
# Remove this test and `bash <<'EOF' ... wl_wait.py & ... EOF` -- a real command,
# not a document -- walks straight through.
DEFECT = ("if not hookio.grep_q(FEEDS_SHELL, cmd):", "if False:")

FEEDS_SHELL = r"\|[" + hookio.SPACE + r"]*(bash|sh|zsh)\b|\b(bash|sh|zsh)[" + hookio.SPACE + r"]+<<"

# The heredoc opener awk looks for, and the prefix/suffix `gsub` strips off it
# to recover the delimiter NAME.
HEREDOC_OPEN = r"<<-?'?[A-Za-z_][A-Za-z0-9_]*'?"
HEREDOC_TRIM = r"^<<-?'?|'$"

WAITER_BACKGROUNDED = r"wl_wait\.py[^&|;]*&([^&]|$)"

MESSAGE = (
    "❌ BLOCKED: wl_wait.py must NOT be launched with a shell `&`. A shell-backgrounded "
    "process is untracked -- the harness can never notify you when it fires, so you stop "
    "hearing cross-session mail silently. Launch it as a harness background task instead: "
    "run the plain command `python3 .claude/hooks/stop/wl_wait.py <session-prefix> "
    "--timeout 60` with run_in_background: true on the Bash tool call. (Also: to check "
    "whether one is already running, match the PYTHON process, not your own wrapper: "
    'ps -eo pid,args | grep "[p]ython3.*wl_wait" -- a bare pgrep -f self-matches the Bash '
    "tool wrapper containing your pattern text.)"
)

_LAUNCH = "python3 .claude/hooks/stop/wl_wait.py d1589e0b --timeout 60"

EDGE_CASES = [
    ("the shape from 2026-08-08", _LAUNCH + " &"),
    ("the same launch without the ampersand", _LAUNCH),
    # `&&` never matches: the regex requires a NON-& character or end-of-line
    # after the single `&`.
    ("&& is not backgrounding", _LAUNCH + " && echo done"),
    # A general `&` ban would be wrong; only the known instrument counts.
    ("an unrelated fan-out", "sleep 1 & sleep 2 & wait"),
    # The quote stripper, and the fd-redirect stripper that was caught as a live
    # false positive during this hook's own proving run.
    ("prose quoting the rule", "echo 'never launch wl_wait.py & like this'"),
    ("a redirect is not a background", _LAUNCH + " 2>&1"),
    # Measured 2026-09-01: a session writing its recovery document with
    # `worklist.py --state <<'EOF'` was blocked because the DOCUMENT contained
    # the sentence "never with a shell `&`".
    (
        "a quoted-delimiter heredoc body is a document",
        "worklist.py --state d1589e0b <<'EOF'\nnever start wl_wait.py & from a shell\nEOF",
    ),
    (
        "a bare-delimiter heredoc body is a document too",
        "worklist.py --state d1589e0b <<EOF\nnever start wl_wait.py & from a shell\nEOF",
    ),
    # ... and the bypass that stripping must not open.
    ("a heredoc feeding a shell IS the command", "bash <<'EOF'\nwl_wait.py &\nEOF"),
    ("a heredoc piped into a shell", "cat <<'EOF' | bash\nwl_wait.py &\nEOF"),
]


def _strip_heredoc_bodies(text):
    """The awk program, record for record.

    Also strip HEREDOC BODIES, which are data rather than commands. Caught as a
    live false positive: a session writing its recovery document with
    `worklist.py --state <<EOF ... EOF` was blocked because the DOCUMENT explained
    this very rule, so the hook forbade documenting itself. Quoted-delimiter
    heredocs are never expanded or executed.
    """
    records, _ = hookio._records(text)
    out = []
    indoc = False
    delim = ""
    for record in records:
        match = re.search(HEREDOC_OPEN, record)
        if match and not indoc:
            # `d = substr($0, RSTART, RLENGTH)` then `gsub` for the name.
            delim = re.sub(HEREDOC_TRIM, "", match.group(0))
            indoc = True
            out.append(record)
            continue
        if indoc and record == delim:
            indoc = False
            continue
        if indoc:
            continue
        out.append(record)
    return shellscan._awk_out(out)


def run(ev):
    cmd = ev.raw("tool_input", "command")

    # Strip quoted strings so an `&` inside a commit message or echo cannot
    # false-positive, and strip fd-redirect forms (2>&1, >&2, 3>&-) whose `&` is
    # not backgrounding -- caught as a live false positive during the hook's own
    # proving run; then look for <waiter> ... & at a command boundary.
    # ORDER MATTERS, and getting it wrong reopened the very false positive the heredoc
    # stripper below was added to close. Quote-stripping runs `s/'[^']*'//g`, which turns a
    # QUOTED heredoc delimiter `<<'EOF'` into a bare `<<` -- so the awk stripper then finds no
    # delimiter name, never enters the body, and scans the document as command text. It worked
    # for `<<EOF` and failed for `<<'EOF'`, which is the form this repo's own guidance uses.
    #
    # Measured 2026-09-01: a session writing its recovery document with
    # `worklist.py --state <<'EOF'` was blocked because the DOCUMENT contained the sentence
    # "never with a shell `&`" -- the hook forbidding its own documentation, a second time.
    #
    # So heredoc bodies come off the RAW command first; quotes and redirects after.
    stripped = cmd
    if not hookio.grep_q(FEEDS_SHELL, cmd):
        stripped = hookio._command_substitution(_strip_heredoc_bodies(stripped))

    # NOW the quotes and redirects, on whatever survived the heredoc strip.
    stripped = hookio.sed_sub(r"'[^']*'", "", stripped)
    stripped = hookio.sed_sub(r'"[^"]*"', "", stripped)
    stripped = hookio.sed_sub(r"[0-9]*>&[0-9-]*", "", stripped)
    # The three `-e` expressions are one sed invocation in the original, wrapped
    # in `$( )`. Applying them one after another over the whole text is the same
    # thing because each is line-local, and the substitution's newline-stripping
    # is spelled out rather than left to sed's own missing-newline handling.
    stripped = hookio._command_substitution(stripped)

    if hookio.grep_q(WAITER_BACKGROUNDED, stripped):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
