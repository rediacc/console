"""Block a wait loop whose `/proc/<pid>` liveness check has a fallback PID that is always alive.

WHY A HOOK AND NOT A DOCUMENT. Found live: task `b9fd3td29` wedged for over 24 hours during a Writer-F autopilot-removal batch, 2026-09-21/22, on exactly this shape. It was found by the agent that wrote it. This is the same TRAP FAMILY as `block_self_matching_pgrep.py` -- an unsatisfiable, invisible-from-outside wait-loop exit condition -- reached by a different mechanism, so it
earns its own entry in docs/agent-reference/TRAPS.md rather than a paragraph added to that one.

WHAT MAKES IT INVISIBLE. The waiting shell's own OS process is genuinely alive and genuinely sleeping in a loop, so a liveness check on the PROCESS reports it as healthy -- correctly, exactly as `block_self_matching_pgrep.py`'s own docstring already explains for its own trap. Only the exit CONDITION distinguishes a wedged loop from a patient one, and this condition contains a
sub-clause that is a disguised constant: `$(cat X || echo N)` reads as "the real PID, or a sensible fallback", but when `N` is a PID that is ITSELF always alive, the fallback branch is not a fallback at all. It is the answer, always, and the "real PID" branch never gets a chance to matter.

THE TEST IS THE BUG ITSELF. Only two literals are provably alive for as long as a loop could run: `1` (init, alive on every live Linux system -- the incident's own literal) and `$$` (the waiting shell's own PID, alive by definition for the loop's whole lifetime, and arguably the single most common way this actually gets written). Any OTHER literal integer, INCLUDING `0`, is not
provably always-alive by construction -- `0` is in fact provably NEVER alive (`/proc/0` never exists), which is exactly why it is this guard's own safe-control case rather than a finding.

=============================================================================
THIS GUARD HAS NO BASH TWIN
=============================================================================

`TWIN = None` is a sentinel, not an oversight, matching the precedent `block_prose_style_edit.py` set on 2026-09-06 (that guard's own docstring: "THIS GUARD HAS NO BASH TWIN, AND IT IS THE FIRST ONE THAT DOES NOT").
What replaces the oracle: a dedicated per-guard suite beside it, `test-block_unsatisfiable_pid_wait.py`, which `test_every_port_has_a_present_twin` requires of any guard declaring `TWIN = None`; and the `DEFECT` below, planted by `test_the_differential_can_fail`, which compares the guard against ITSELF-WITH-A-BUG rather than against bash.

SCOPE, DELIBERATELY NARROW. `/proc/<pid>` existence tests only (`-e`/`-d`); `kill -0 $(...)` is the identical bug spelled differently and is a named, undetected gap -- see docs/agent-reference/TRAPS.md's Residue line for this trap. Loops only: a one-shot `if [ -e /proc/$(...) ]` costs one wrong read, not an unbounded wait, and is out of scope for the same reason
`block_self_matching_pgrep.py` leaves a one-shot `pgrep -cf` alone. A bare `cat <path> || echo <default>` used OUTSIDE a `/proc/` test is the ordinary, extremely common "read a value or use a default" idiom and must never be caught -- the `/proc/` requirement in the anchor is load-bearing, not incidental. A fallback the guard cannot resolve statically (a variable, e.g. `echo
"$FALLBACK_PID"`) reads as unexaminable and is allowed, matching this repo's "fail toward allowing when a claim cannot be resolved statically" convention (see `block_self_matching_pgrep.py`'s own port note on an unparseable regex not being a verdict).

WHY A REGEX PLUS A HAND-WRITTEN BALANCED-PAREN SCAN, NOT A FULL SHELL AST. `block_self_matching_pgrep.py` sets the precedent this follows: anchor the loop condition by position (keyword to `; do`), then do the small amount of string surgery a regex alone cannot do reliably -- here, matching nested parens inside `$( ... )` and splitting on a top-level `||` without crossing into a
quoted string.
"""

import os
import re

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = None
ORDER = 44

# THE TEST IS THE BUG ITSELF. Without it, every /proc/$(cat X || echo N) inside a wait loop is refused regardless of N, including the safe case (N=0, which is provably NEVER alive) and the unexaminable case (N is a variable the guard could not resolve). Nullifying this turns the incident's own fire-case into a silent allow.
DEFECT = ("if _is_provably_always_alive(fallback):", "if False:")

# A loop condition runs from the keyword to the `; do` that closes it -- the same span `block_self_matching_pgrep.py`'s LOOP_WITH_PGREP anchors to, for the same reason: a mention of the pattern in prose elsewhere on the line must not pair up with an unrelated loop.
LOOP_HEAD = hookio.rx(r"(^|[;&|(]|&&|\|\|)[{S}]*(until|while)\b")
DO_CLOSE = hookio.rx(r";[{S}]*do\b")

# THE PROCFS SEAM. This guard never READS procfs; it RECOGNISES the procfs liveness idiom inside somebody else's command text. That still makes the path a platform-sensitive constant, and in the direction that is hardest to notice: on a machine whose procfs is not at `/proc` (macOS has none at all, and a container can bind one under a different root), the wait loops people
# actually write are spelled against THAT root, the prefilter below misses every one of them, and this guard degrades to an unconditional ALLOW that still reads green in every test that runs on a default Linux box. A guard that silently finds nothing is the failure mode `proc.py`'s own backend seam was written for; the difference here is only that the divergence lands in a
# pattern rather than in a read. So the root is named once, read from the environment, and both the prefilter and the anchor below are BUILT from it rather than each carrying their own copy. Exercise the non-default path with REDIACC_PID_WAIT_PROCFS and the anchor follows; a second hard-coded spelling would not.
#
# EDGE_CASES and the test suite beside this file are written against the DEFAULT spelling on purpose: they are the evidence about the shape this guard ships with, and re-deriving their fixtures from the override would make them agree with any value of it, including a wrong one.
PROCFS_ENV = "REDIACC_PID_WAIT_PROCFS"
PROCFS_ROOT = (os.environ.get(PROCFS_ENV) or "/proc").rstrip("/") or "/proc"
PROCFS_PREFIX = PROCFS_ROOT + "/"

# -e or -d immediately (optionally through one straight quote) in front of <procfs>/$( -- NOT a bare "-e $(...)" (the ordinary default-value idiom, explicitly out of scope per the module docstring), and NOT a mention of <procfs>/$( outside a -e/-d test.
PROC_TEST_OPEN = hookio.rx(r"-[ed][{S}]+\"?" + re.escape(PROCFS_PREFIX) + r"\$\(")

# The LEFT half of a top-level `||` inside the substitution must be EXACTLY a `cat` of one path token (no pipe, no further command), with an optional `2>/dev/null`. A pipeline, a `;`, or an `&&` join is a DIFFERENT idiom -- see EDGE_CASES.
LEFT_IS_BARE_CAT = hookio.rx(r"^[{S}]*cat[{S}]+[^|;&{S}]+([{S}]*2>[{S}]*/dev/null)?[{S}]*$")
RIGHT_IS_ECHO = hookio.rx(r"^[{S}]*echo[{S}]+(-[A-Za-z]+[{S}]+)?(\S+)[{S}]*$")

MESSAGE = """BLOCKED: this wait loop can never exit. Its /proc/ liveness check has a fallback PID that is always alive.

  clause: %s
  fallback PID: %s

A `cat <pidfile> || echo <N>` substitution used inside a /proc/<pid> existence
test reads as "the real PID, or a sensible fallback" -- but %s is alive for as
long as this loop could possibly run, so the fallback branch is not a
fallback. It is the answer, always, and the pidfile's real content never gets
a chance to matter. The condition is a disguised constant and the loop cannot
exit.

This has already cost this project 24+ hours once (task b9fd3td29). It is in
docs/agent-reference/TRAPS.md.

Pick one:

  1. Write the pidfile BEFORE the loop starts and drop the `||` fallback
     entirely -- a missing pidfile is a hard error, not a value to guess.
  2. Treat a missing pidfile as "not started yet, keep waiting":
       until [ ! -s out.pid ] || ! [ -e /proc/$(cat out.pid) ]; do sleep 5; done
  3. Wait on the harness instead. A Bash call with run_in_background: true
     notifies you when it exits; you do not need a PID-based watcher for it.

A fallback to 0 is NOT blocked (/proc/0 never exists, so it is an honest
"not yet started" default), and neither is a fallback the guard cannot
resolve statically (a variable rather than a literal).
"""

EDGE_CASES = [
    # The incident's own shape.
    (
        "the incident's own shape",
        (
            'until grep -q "ci-dead-bash" out.log && [ "$(tail -c 200 out.log | wc -c)" -gt 0 ] '
            "&& ! [ -e /proc/$(cat out.log.pid 2>/dev/null || echo 1) ]; do sleep 5; done"
        ),
    ),
    (
        "minimal fire, unnegated",
        "until [ -e /proc/$(cat x.pid 2>/dev/null || echo 1) ]; do sleep 5; done",
    ),
    ("$$ fallback", "until ! [ -e /proc/$(cat x.pid 2>/dev/null || echo $$) ]; do sleep 5; done"),
    (
        "quoted path form",
        'until ! [ -e "/proc/$(cat x.pid 2>/dev/null || echo 1)" ]; do sleep 5; done',
    ),
    ("-d instead of -e", "until ! [ -d /proc/$(cat x.pid || echo 1) ]; do sleep 5; done"),
    (
        "while form fires the same as until",
        "while ! [ -e /proc/$(cat x.pid 2>/dev/null || echo 1) ]; do sleep 5; done",
    ),
    # CONTROL: the safe literal.
    (
        "CONTROL: a fallback of 0 is safe",
        "until ! [ -e /proc/$(cat x.pid 2>/dev/null || echo 0) ]; do sleep 5; done",
    ),
    # CONTROL: an arbitrary other literal is a documented gap, not a finding.
    (
        "CONTROL: an arbitrary literal PID is a documented gap",
        "until ! [ -e /proc/$(cat x.pid || echo 54321) ]; do sleep 5; done",
    ),
    # CONTROL: an unexaminable variable fallback.
    (
        "CONTROL: a variable fallback is unexaminable",
        'until ! [ -e /proc/$(cat x.pid 2>/dev/null || echo "$FALLBACK_PID") ]; do sleep 5; done',
    ),
    # CONTROL: not a loop at all.
    (
        "CONTROL: a one-shot check is out of scope",
        "if [ -e /proc/$(cat x.pid 2>/dev/null || echo 1) ]; then echo dead; fi",
    ),
    # CONTROL: a `;`-joined echo is a different idiom (always runs, not a fallback).
    (
        "CONTROL: a semicolon join is a different bug",
        "until [ -e /proc/$(cat x.pid 2>/dev/null; echo 1) ]; do sleep 5; done",
    ),
    # CONTROL: an `&&`-joined echo only runs on success, not a fallback at all.
    (
        "CONTROL: an && join is not a fallback",
        "until [ -e /proc/$(cat x.pid 2>/dev/null && echo 1) ]; do sleep 5; done",
    ),
    # Correct remedy #1: no fallback at all.
    (
        "CONTROL: the pidfile-first remedy",
        "until [ -s out.pid ] && ! [ -e /proc/$(cat out.pid) ]; do sleep 5; done",
    ),
    # Correct remedy #2: missing pidfile means keep waiting.
    (
        "CONTROL: the not-started-yet remedy",
        "until [ ! -s out.pid ] || ! [ -e /proc/$(cat out.pid) ]; do sleep 5; done",
    ),
    # CONTROL: kill -0 is the same mechanism, different string -- a named v1 gap.
    (
        "CONTROL: kill -0 form is a documented v1 gap",
        "until ! kill -0 $(cat x.pid 2>/dev/null || echo 1) 2>/dev/null; do sleep 5; done",
    ),
    # CONTROL: the ordinary default-value idiom, no /proc/ at all.
    (
        "CONTROL: a non-proc default is not this bug",
        "until [ -e $(cat config_path.txt 2>/dev/null || echo default.conf) ]; do sleep 2; done",
    ),
    # CONTROL: prose mention, not a real loop.
    (
        "CONTROL: prose mention is not the trap",
        'echo "never write /proc/$(cat x.pid || echo 1) into a wait loop"',
    ),
    # CONTROL: unbalanced substitution is not a verdict.
    (
        "CONTROL: an unparseable substitution",
        "until ! [ -e /proc/$(cat x.pid || echo 1 ; do sleep 5; done",
    ),
    # CONTROL: a pipeline on the left is a different, more ambiguous shape.
    (
        "CONTROL: a pipeline on the left is not a bare cat",
        "until ! [ -e /proc/$(cat x.pid | grep -q 1 || echo 1) ]; do sleep 5; done",
    ),
    ("a loop with no /proc/ check at all", "until [ -s out.txt ]; do sleep 5; done"),
]


# THE TEST IS THE BUG ITSELF: only a fallback provably alive for the whole time the loop could run counts. "1" (init) is the incident's own literal; "$$" (the waiting shell's own PID) is the same defect and arguably the single most common way this actually gets written by an agent -- both caught here. Any OTHER literal integer, INCLUDING 0, is NOT provably always-alive by
# construction (0 is provably NEVER alive, which is why it is the safe control) and is deliberately left unblocked -- see EDGE_CASES and the module docstring's SCOPE section.
def _is_provably_always_alive(token):
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        token = token[1:-1]
    return token in ("$$", "1")


def _extract_subst(text, open_paren_idx):
    """Balanced $( ... ) scan from the '(' at open_paren_idx. None if unbalanced -- an unparseable substitution is not a verdict, same convention as block_self_matching_pgrep's unparseable-regex handling: fail toward allow."""
    depth = 0
    in_sq = in_dq = False
    for i in range(open_paren_idx, len(text)):
        ch = text[i]
        if in_sq:
            in_sq = ch != "'"
            continue
        if in_dq:
            if ch == '"' and text[i - 1] != "\\":
                in_dq = False
            continue
        if ch == "'":
            in_sq = True
        elif ch == '"':
            in_dq = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1 : i]
    return None


def _split_top_level_or(body):
    """First `||` outside quotes, or None. `;`- and `&&`-joined fallbacks are a DIFFERENT idiom (only a fallback that ACTUALLY substitutes on cat failure matters) and correctly never split here."""
    in_sq = in_dq = False
    i = 0
    while i < len(body) - 1:
        ch = body[i]
        if in_sq:
            in_sq = ch != "'"
        elif in_dq:
            if ch == '"' and body[i - 1] != "\\":
                in_dq = False
        elif ch == "'":
            in_sq = True
        elif ch == '"':
            in_dq = True
        elif ch == "|" and body[i + 1] == "|":
            return body[:i], body[i + 2 :]
        i += 1
    return None


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "" or PROCFS_PREFIX not in cmd or "$(" not in cmd:
        return hookio.ALLOW

    for head in re.finditer(LOOP_HEAD, cmd):
        close = re.search(DO_CLOSE, cmd[head.end() :])
        cond_end = head.end() + close.start() if close else len(cmd)
        condition = cmd[head.end() : cond_end]  # SCOPE: loops only

        for anchor in re.finditer(PROC_TEST_OPEN, condition):
            open_idx = anchor.end() - 1  # index of the '(' in "$("
            body = _extract_subst(condition, open_idx)
            if body is None:
                continue  # unbalanced: not a verdict, keep scanning

            split = _split_top_level_or(body)
            if split is None:
                continue  # no top-level `||`: `;`/`&&`/no-fallback, not this bug
            left, right = split

            if not re.match(LEFT_IS_BARE_CAT, left):
                continue  # not a bare `cat <path>`: a pipeline etc, not this bug
            m = re.match(RIGHT_IS_ECHO, right)
            if not m:
                continue  # not `echo <literal>`

            fallback = m.group(2)
            if _is_provably_always_alive(fallback):
                ev.warn_raw(MESSAGE % (anchor.group(0) + body + ")", fallback, fallback))
                return hookio.DENY

    return hookio.ALLOW
