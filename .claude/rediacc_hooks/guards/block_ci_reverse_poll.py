"""Block reverse CI polling: gh run view ... --jq then a wait.

The guidance POINTS AT the ci-watch skill rather than embedding a copy of the loop. It used to embed one, and on 2026-08-25 that copy was found to be one of nine divergent versions across the repo, several of them handing out a form
that exits on the first `status == completed` -- which is not terminal,
because the watchdog re-runs a transient failure and bumps run_attempt.


NOT ROUTED THROUGH `shellscan`, and that is a decision rather than an oversight. On 2026-08-27 nine sibling guards moved to the shared scanner to stop them matching prose. This one did not: the scanner drops heredoc bodies, and the operator ruled on 2026-08-25 -- four scored options -- that this guard keeps its prose false positive. It fails LOUDLY (a blocked command that names its
workaround) while every narrowing fails SILENTLY, and a heredoc is exactly where a real one would hide. test-hooks.sh pins that ruling with a case asserting exit 2, and that case is what caught the attempt.

PORT NOTE, because two details of the bash are invisible once it is Python. There is no `[ -z "$CMD" ] && exit 0` here, so an event with no command reaches the pattern as the four characters `null` (see `hookio._jq_raw`) and is scanned. And `echo "$CMD" | grep` appends a newline, which is why `grep_q_line` is used rather than `grep_q`: on an empty command the two differ, one giving
grep a single empty record and the other giving it none.
"""

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-ci-reverse-poll.sh"
ORDER = 12

# The line whose loss the differential must notice: with the `&&[[:space:]]*sleep` tail gone the pattern still matches every `gh run view N --jq`, so the guard refuses a plain read of a run. Chosen because it is the half that makes this a POLLING guard rather than a `gh run view` ban. A SOURCE substring pair, not an evaluated one. The first cut of this computed the two halves with
# the same expression the pattern uses, which reads well and cannot work: the planter searches the module's TEXT, and the text holds `hookio.BLANK`, not its value. Caught on the first run.
DEFECT = ("&&[{B}]*sleep", "&&[{B}]*")

PATTERN = hookio.rx(r"gh[{B}]+run[{B}]+view[{B}]+[0-9]+[^|;&]*--jq[^|;&]*&&[{B}]*sleep")

MESSAGE = (
    "❌ BLOCKED: Reverse polling pattern (gh run view followed by sleep). "
    "Polling chews through context. Run .ci/scripts/ci/ci-trace.py --wait with "
    "run_in_background:true -- it keys on the PR head, so a watchdog re-run and a "
    "superseded run are both handled structurally. Do NOT use gh run watch -- it has "
    "dropped silently on terminal runs (observed 4/4)."
)

EDGE_CASES = [
    (
        "the pinned prose ruling: a heredoc still fires",
        "cat <<EOF\ngh run view 1 --jq .x && sleep 30\nEOF",
    ),
    (
        "quoted prose still fires, by the same ruling",
        "echo 'gh run view 1 --jq .status && sleep 30'",
    ),
    ("a plain run view is not polling", "gh run view 123 --json status"),
    ("--jq with no wait after it", "gh run view 123 --jq .status"),
    ("a separator between them is not the && shape", "gh run view 1 --jq .s; sleep 30"),
    # The case the planted defect needs, and it is a real shape rather than a test-shaped one: reading a run and then doing something that is not a wait. Without it nothing in the whole corpus could tell the pattern with its `sleep` tail from the pattern without it, and the anti-vacuity control said so on the first run rather than at review time.
    ("--jq then a command that is not a wait", "gh run view 1 --jq .status && echo done"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if hookio.grep_q_line(PATTERN, cmd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
