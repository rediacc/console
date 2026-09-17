"""Block a wait loop whose `pgrep -f` pattern matches the waiting shell itself.

WHY A HOOK AND NOT A DOCUMENT. This is written down already, in full, at
docs/agent-reference/TRAPS.md ("A `pgrep -f <pattern>` guard inside a shell
whose own command line contains that pattern waits forever"), where it is
recorded as costing 317 minutes. It was also recorded a second time, in
block-shell-background-waiter.sh's own header: "three rounds chasing
'respawning' waiters that were its own pgrep wrappers self-matching". On
2026-08-26 a session read neither and launched TWO more, which ran 70 and 63
minutes past conditions that had already been satisfied. A trap written down
three times and hit anyway is a trap that needs a gate.

WHAT MAKES IT INVISIBLE. `pgrep -f` matches full command lines, and the
waiting shell's own command line CONTAINS the pattern, because the pattern is
part of the command being run. So pgrep always finds at least itself, the
negation is permanently false, and the loop cannot exit. Nothing looks wrong
from outside: the Stop hook's liveness check reports "silent but its OS
process is VERIFIED ALIVE (a loop that prints only at the end is healthy)",
which is a CORRECT reading of a loop that is genuinely running. A wedged loop
and a patient one are indistinguishable by liveness; only the exit condition
tells them apart, and nothing checks that.

THE TEST IS THE BUG ITSELF, which is what makes this precise rather than a
keyword ban: run the pattern as a regex against the command that contains it.
If it matches, pgrep will match the waiter too. The documented remedy -- a
bracket class, `[t]est-hooks.sh` -- makes the regex NOT match its own literal
text, so a correctly written waiter passes here by construction rather than by
an allowlist someone has to maintain.

SCOPE: loops only. A one-shot `pgrep -cf X` is contaminated the same way (it
counts the caller, so it reads one too high) but it costs a wrong number
rather than an unbounded wait, and blocking every diagnostic pgrep would be
the over-matching this repo has paid for repeatedly. The message says so.

PORT NOTE ON "AN UNPARSEABLE REGEX IS NOT A VERDICT". The bash spells that as
`grep -qE -- "$PAT" 2>/dev/null || continue`, where a malformed ERE makes grep
exit 2 with a message the redirect eats, and the `||` treats that exactly like
"did not match". In Python the same input raises `re.error` from `compile`,
which would come out of a hook as a traceback rather than as an allow, so the
compile is guarded and the exception folded into the same `continue`. Losing
that would turn a user typing `pgrep -f '['` into a crashed guard.

PORT NOTE ON ERE VERSUS PYTHON'S DIALECT. The pattern being tested is the
USER's, run as a regex against the user's own command line, so the two engines
must agree on it for the verdict to agree. They do for everything the corpus
contains, and the shapes where they would not (a POSIX back-reference, an
interval on an unsupported atom) are shapes `pgrep -f` would itself reject.
This is stated rather than asserted: the differential is what pins it, and it
compares against real grep on every case.
"""

import re

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-self-matching-pgrep.sh"
ORDER = 15

# THE TEST IS THE BUG ITSELF. Without it every wait loop with a `pgrep -f` is refused, including the documented remedy -- the bracket class that makes the regex not match its own literal text -- so the guard would refuse the very form its own message tells you to write.
DEFECT = ("if not _matches(pat, cmd):\n            continue", "if False:\n            continue")

# A loop, and a pgrep that matches on the full command line (-f, in any flag cluster). Either alone is fine. THE pgrep MUST BE IN THE LOOP'S CONDITION, not merely somewhere in the same command as the word "while". Testing the two independently made this refuse a one-shot `pgrep -cf` diagnostic that happened to sit in the same line as a worklist message containing the ordinary
# English word "while" -- a line that loops over nothing. That is the sixth mention-as-execution false positive of this session, this time in the guard written to stop the previous one.
#
# A loop condition runs from the keyword to the `; do` that closes it, so that
# is the span to search. `[^;]*` keeps it to a single condition rather than
# letting a later, unrelated pgrep pair up with an earlier loop. ANCHORED TO COMMAND POSITION 2026-08-28, found by check:ci-guard-mention-anchoring. The old group's own [[:space:]] alternative defeated it: ANY word followed by a space before `until` matched, so "TRAPS.md explains why until pgrep -xf never exits" refused as if it were the loop itself. This narrows PROSE only -- the
# real loop, at line start or after a separator, is still caught by the control below.
LOOP_WITH_PGREP = hookio.rx(r"(^|[;&|(]|&&|\|\|)[{S}]*(until|while)[^;]*pgrep[{S}]+-[a-zA-Z]*f")

# The pattern is the first argument after the flag cluster: quoted either way, or bare up to the next whitespace.
PATTERN_ARG = (
    r"pgrep["
    + hookio.SPACE
    + r"]+-[a-zA-Z]*f["
    + hookio.SPACE
    + r"]+('[^']*'|\"[^\"]*\"|[^"
    + hookio.SPACE
    + r";|&)]+)"
)

STRIP_VERB = hookio.rx(r"^pgrep[{S}]+-[a-zA-Z]*f[{S}]+")

MESSAGE = """BLOCKED: this wait loop can never exit. Its pgrep pattern matches itself.

  pattern: %s

`pgrep -f` matches FULL COMMAND LINES, and this shell's own command line
contains that pattern, because the pattern is written in the command. pgrep
therefore always finds at least one process -- this one -- so the condition
never flips and the loop runs until something kills it. It looks healthy the
whole time: the Stop hook reports "VERIFIED ALIVE (a loop that prints only at
the end is healthy)", which is true and useless, because a wedged loop and a
patient loop are identical from outside.

This has now cost this project 317 minutes once, three rounds of chasing
"respawning" waiters once, and two waiters running 70 and 63 minutes past their
conditions on 2026-08-26. It is in docs/agent-reference/TRAPS.md.

Pick one:

  1. Do not wait on a process at all. Wait on what it PRODUCES:
       until [ -s out.txt ]; do sleep 5; done
  2. Wait on the harness instead. A Bash call with run_in_background: true
     notifies you when it exits; you do not need a watcher for it.
  3. If you must match a process, hide the pattern from itself with a
     bracket class, which matches the process but not this literal text:
       until ! pgrep -f '[t]est-suite.sh' >/dev/null; do sleep 5; done

A one-shot `pgrep -cf X` is NOT blocked, but it counts the caller too, so
subtract one or use the bracket form there as well.
"""

EDGE_CASES = [
    ("the self-matching loop", "until pgrep -f wl_wait.py; do sleep 5; done"),
    ("the same with a negation", "while ! pgrep -f test-suite.sh; do sleep 5; done"),
    ("a quoted pattern", "until pgrep -f 'test-suite.sh' >/dev/null; do sleep 5; done"),
    ("a double-quoted pattern", 'until pgrep -f "test-suite.sh"; do sleep 5; done'),
    # The documented remedy, which must pass BY CONSTRUCTION.
    (
        "the bracket-class remedy",
        "until ! pgrep -f '[t]est-suite.sh' >/dev/null; do sleep 5; done",
    ),
    # SCOPE: loops only.
    ("a one-shot diagnostic is not blocked", "pgrep -cf wl_wait"),
    # The 2026-08-28 anchoring, in the sentence that found it.
    (
        "prose naming the trap is not the trap",
        "echo 'TRAPS.md explains why until pgrep -xf never exits'",
    ),
    # An unparseable regex is not a verdict: allow what cannot be judged.
    ("an unparseable pattern", "until pgrep -f '[' ; do sleep 5; done"),
    ("a flag cluster with f in it", "until pgrep -af wl_wait.py; do sleep 5; done"),
    ("a loop with no pgrep at all", "until [ -s out.txt ]; do sleep 5; done"),
]


def _matches(pattern, text):
    """`printf '%s' "$CMD" | grep -qE -- "$PAT" 2>/dev/null`.

    False for a pattern grep would refuse, which the `|| continue` above turns
    into "not a verdict". See the port note in the module docstring.
    """
    try:
        return hookio.grep_q(pattern, text)
    except re.error:
        return False


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    if not hookio.grep_q(LOOP_WITH_PGREP, cmd):
        return hookio.ALLOW

    # `grep -oE ... | sed -E "...; ...; ..."`: three expressions, each applied
    # ONCE per record (no `g` flag), in order.
    pats = []
    for match in hookio.grep_o(PATTERN_ARG, cmd):
        text = re.sub(STRIP_VERB, "", match, count=1)
        text = re.sub(r"^'(.*)'$", r"\1", text, count=1)
        text = re.sub(r'^"(.*)"$', r"\1", text, count=1)
        pats.append(text)
    joined = hookio._command_substitution(hookio._sed_out(pats, terminated=bool(pats)))

    records, _ = hookio._records(hookio._here_string(joined))
    for pat in records:
        if pat == "":
            continue
        # An unparseable regex is not a verdict: allow what cannot be judged.
        if not _matches(pat, cmd):
            continue
        ev.warn_raw(MESSAGE % pat)
        return hookio.DENY

    return hookio.ALLOW
