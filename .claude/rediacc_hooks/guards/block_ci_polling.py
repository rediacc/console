"""Block CI polling: a wait, then gh run view/list.

The guidance below deliberately POINTS AT the ci-watch skill instead of
embedding a copy of the watch loop. It used to embed one, and that copy went
stale on 2026-08-25: the recipe it handed out exited on the first
`status == completed`, which is not terminal, because the watchdog re-runs a
transient failure and bumps `run_attempt`. Six places held that same snippet
and all six had to be corrected at once. One source, many pointers.

Known false positive, accepted deliberately: this matches per line, so a
command that merely DESCRIBES the polling pattern (editing these docs, or a
patch script carrying the old snippet as a search string) is blocked too. The
check is not narrowed to avoid it, because every narrowing that would let the
doc edit through also opens a hole for the habit this guards against, and the
workaround is trivial (write the file with the Write tool instead).


NOT ROUTED THROUGH `shellscan`, and that is a decision rather than an
oversight. On 2026-08-27 nine sibling guards moved to the shared scanner to
stop them matching prose. This one did not: the scanner drops heredoc bodies,
and the operator ruled on 2026-08-25 -- four scored options -- that this guard
keeps its prose false positive. It fails LOUDLY (a blocked command that names
its workaround) while every narrowing fails SILENTLY, and a heredoc is exactly
where a real one would hide. test-hooks.sh pins that ruling with a case
asserting exit 2, and that case is what caught the attempt.

PORT NOTE. The two guards in this pair look interchangeable and are not: this
one wants the wait FIRST and `gh run view|list` after it, its sibling
`block_ci_reverse_poll` wants them the other way round and additionally
requires `--jq`. Reproduced as two separate patterns rather than merged, for
the reason the sibling's header gives about one source and many pointers: a
merged pattern would be a third spelling neither file could be checked against.
"""

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-ci-polling.sh"
ORDER = 11

# Dropping the SUBCOMMAND makes every `gh run <anything>` after a wait a refusal, so re-running a failed job on a delay is blocked as if it were polling. It is the half that names WHICH gh calls re-fetch the job tree.
#
# The separator was the first candidate and it does not work: `[^|;&]*` on
# either side of it already cannot cross a separator, so making `(&&|;)`
# optional changes nothing any realistic command can see. The anti-vacuity control said so rather than the defect being taken on trust.
DEFECT = ("run[{B}]+(view|list)", "run[{B}]+")

PATTERN = hookio.rx(r"sleep[{B}]+[0-9]+[^|;&]*(&&|;)[{B}]*[^|;&]*gh[{B}]+run[{B}]+(view|list)")

MESSAGE = (
    "❌ BLOCKED: CI polling pattern detected (sleep then gh run view/list). Polling "
    "chews through context and re-fetches the same job tree over and over. Use ONE of: "
    "(a) read the existing background watch task output at the path printed when it "
    "started, and wait for the completion notification automatically; (b) run "
    ".ci/scripts/ci/ci-trace.py --wait with run_in_background:true -- it keys on the PR "
    "head and reads statusCheckRollup, so a watchdog re-run replaces the old attempt "
    "instead of fooling the watch. Do NOT use gh run watch as the wake-up -- it has "
    "dropped silently on terminal runs (observed 4/4); a process exit on terminal state "
    "is the reliable notification. If you are EDITING documentation that describes this "
    "pattern rather than polling, use the Write tool instead of a shell heredoc."
)

EDGE_CASES = [
    # The 2026-08-25 ruling, pinned here as well as in the suite: prose fires.
    ("prose in a heredoc still fires", "cat <<EOF\nsleep 60 && gh run list\nEOF"),
    ("quoted prose still fires", "echo 'sleep 60; gh run view 1'"),
    # The shapes that must NOT fire, which is the half a block-only corpus cannot see.
    ("a wait with no gh after it", "sleep 60 && echo done"),
    ("gh run view with no wait before it", "gh run view 123"),
    ("a pipe between them is not the separator this matches", "sleep 60 | gh run list"),
    ("the reverse order belongs to the sibling guard", "gh run view 1 --jq .s && sleep 60"),
    # A wait then a gh run subcommand that is NOT view or list. Re-running a failed job on a delay re-fetches nothing, so the twin allows it, and without this case nothing in the corpus could tell the subcommand list
    # from "any gh run at all".
    ("a wait then a rerun is not polling", "sleep 5 && gh run rerun 123"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if hookio.grep_q_line(PATTERN, cmd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
