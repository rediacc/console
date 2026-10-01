"""Block long FOREGROUND sleeps (catches the sleep+gh-run-view polling pattern).

Two corrections landed 2026-08-25, both found while landing console#574.

1. It read the FIRST sleep in the command (`head -1`), not the longest. The
   sanctioned watch contains `sleep 20` in its error arm and `sleep 90` in its
   stability arm, so it passed this guard purely because of the order the arms
   happen to appear in. Reordering the case would have blocked the repo's own
   recommended recipe. It now takes the MAXIMUM, which is what "do not sleep
   longer than N" was always supposed to mean.

2. A long sleep is only expensive in the FOREGROUND, where it stalls the
   session. In a harness background task it costs nothing and is exactly how a
   terminal-state watch is supposed to idle between polls. The cap is
   therefore raised for run_in_background, which is what makes the attempt-
   stable watch (same run_attempt seen twice, 90s apart) expressible at all.
   block-ci-polling.sh still catches real foreground polling shapes.

COMMAND POSITION, NOT TEXT (2026-10-01, #8e5a6452). The guard used to grep the raw command, so the word inside a QUOTED argument was read as a pause: a `printf` writing commit-message prose that named a 600-second sleep, and a worklist `--add "<text naming one>"`, were refused although neither runs anything. It now asks `shellscan._analyse` for the commands bash would run.
A `sleep` is judged only where it is the command, after `do`, `then`, `!`, `timeout N`, `nohup`, `env`, `sudo` and the other prefixes the walk strips. The walk still descends into `sh -c` payloads, `eval`, substitutions, and a heredoc, here-string or `echo`/`cat` pipe fed to a shell, so every way of RUNNING a sleep is still seen.

Two places keep the old text match, because a narrowing there would fail silently. A HEREDOC BODY is still scanned whatever reads it, under the operator's 2026-08-25 ruling pinned in tests/hookcases.py: a heredoc is where a genuine long sleep would hide, so a commit message passed as `-F - <<EOF` that quotes one is still refused (write the message with the Write tool and pass it by path).
The operands of a command that runs them ELSEWHERE (`ssh`, `docker`, `podman`, `kubectl`, `watch`) are also scanned as text, since the walk does not follow a remote shell.

The duration is read the way `sleep` reads it: every operand is summed, each with an optional `s`/`m`/`h`/`d` suffix, so `sleep 1m` is sixty seconds and `sleep infinity` never ends.

RE-CONFIRMED 2026-08-27. Nine sibling guards were routed through lib/command-scan.sh that day to stop them matching prose, and this one was routed with them. The suite case pinning the 2026-08-25 ruling turned red and reverted it: the shared scanner drops heredoc bodies, which is the option the ruling names as the most tempting and the worst. The pin worked as designed.

PORT NOTE ON THE COMPARISON, and the transliteration OUTLIVED the bug it faithfully copied. `[[ "$SLEEP_VAL" -gt "$LIMIT" ]]` was bash ARITHMETIC, so a value with a leading zero was read as OCTAL: `024` was twenty, not twenty-four, and the command was allowed even though `sleep` itself waits twenty-four seconds. `08` and `09` are not valid octal at all, so bash printed `[[: 08:
value too great for base` on stderr and the test evaluated false -- the guard both complained and permitted.

This port reproduced all of that, correctly, because a port's job is to answer what its twin answers. THE TWIN WAS THEN FIXED (2026-09-06): it forces base ten
with `10#`, so `024` now blocks and `08` is allowed silently. Faithfulness is to
the twin as it IS, so `_arith` was changed with it, in the same breath. Keeping the octal reading here would have turned a shared bug into a divergence and the differential would have caught it -- which is the differential working.

"AND NO CASE HERE PROVOKES IT" WAS THE WRONG ANSWER, corrected here after the divergence was found by hand rather than by the suite. A port that differs from its twin on an input the corpus never carries is a difference nothing reports, which is exactly the class this whole workstream is built against. So the input is DECLARED in `KNOWN_DIVERGENCES` below: the harness runs it,
requires the exit code and stdout to match, and requires stderr to keep differing -- so the declaration cannot rot into an excuse for a match.
"""

import math
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 13

FG_MAX = 20
BG_MAX = 120

# Correction 1, undone: reading the FIRST sleep instead of the largest is exactly what let the sanctioned watch through on the accident of arm order.
DEFECT = ("ordered[-1]", "ordered[0]")

FG_MESSAGE = (
    "❌ BLOCKED: Do not use sleep > %ss in the foreground -- it stalls the session, and it "
    "is half of the sleep+gh-run-view polling pattern. To wait on CI, run "
    ".ci/scripts/ci/ci-trace.py --wait with run_in_background:true: it owns its own polling "
    "interval, so you never write a sleep at all. The CI watchdog auto-retries transient "
    "failures and attempt 2 lands on the SAME Console CI run; the script reads the head's "
    "rollup, so that rerun replaces the old attempt. Do NOT rely on gh run watch: it has "
    "dropped silently on terminal runs (observed 4/4); a process exit on terminal state is "
    "the reliable notification. Also: a PostToolUse hook auto-cancels old CI runs on every "
    "git push, so you never need to cancel manually." % FG_MAX
)

EDGE_CASES = [
    ("a foreground sleep over the cap", "sleep 45"),
    ("a foreground sleep at the cap is allowed", "sleep 20"),
    # Correction 1: the largest wins, not the first.
    ("the maximum wins, not the first", "sleep 20; sleep 90"),
    # Correction 2: the background cap is higher, which is what makes the attempt-stable watch expressible at all.
    (
        "the same command in the background is under the higher cap",
        {"tool_input": {"command": "sleep 20; sleep 90", "run_in_background": True}},
    ),
    (
        "a background sleep over the background cap",
        {"tool_input": {"command": "sleep 300", "run_in_background": True}},
    ),
    # The leading zero the PORT NOTE is about: bash reads this as twenty.
    ("a leading zero is read as octal", "sleep 024"),
    ("no sleep at all", "gh run view 123"),
    # A tab separates words for bash, so since the command-position reading this IS a 45-second sleep.
    ("a tab between sleep and its argument is a sleep", "sleep\t45"),
    # #8e5a6452: the word inside a quoted argument is prose, not a command.
    ("quoted prose naming a sleep", "printf '%s\\n' 'which sleep 600 s (a full run)' > msg.txt"),
    ("a minute suffix", "sleep 1m"),
    ("a heredoc body is still scanned", "git commit -F - <<'M'\nwhich sleep 600 s\nM"),
]

# NO DECLARED DIVERGENCES, and the one that used to be here is worth recording as an absence. It was `sleep 08`: not valid octal, so the twin wrote a bash arithmetic error naming its own file and line number and then evaluated FALSE, permitting the command. The port agreed on the decision and said nothing, so the stderr difference was declared rather than faked -- emitting a path
# and a line number belonging to the file being replaced is a fabrication, not a transliteration.
#
# The twin was fixed on 2026-09-06 to force base ten. It no longer errors, both sides now allow `08` silently, and the divergence dissolved rather than being waived. An empty list is the honest state; the harness still asserts it, so a new divergence cannot arrive unannounced.
KNOWN_DIVERGENCES = []


def _arith(value):
    """The twin's `$(( 10#value ))`: base ten, leading zeros and all.

    This used to emulate bash's OCTAL reading of a leading zero, because that is what the twin did. The twin was fixed on 2026-09-06 to force base ten, so this follows it. `08` and `09` are ordinary numbers now on both sides, and neither implementation writes an arithmetic error.
    """
    return int(value, 10)


_UNIT = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
_OPERAND = re.compile(r"^([0-9]+(?:\.[0-9]*)?|\.[0-9]+)([smhd]?)$")
# The text match kept for heredoc bodies and remote operands: a literal SPACE, as the original `grep -oE 'sleep +[0-9]+'` had it.
_TEXT_SLEEP = re.compile(r"sleep +([0-9]+)")
# Commands that run their operands somewhere the walk does not follow (a remote shell, a container, a repeated `sh -c`).
_ELSEWHERE = frozenset(("ssh", "docker", "podman", "kubectl", "watch"))


def _duration(argv):
    """What `sleep` itself waits for these operands: their sum, `infinity` as inf, None when no operand is a duration."""
    total = 0.0
    found = False
    for arg in argv:
        if arg.lower() in ("inf", "infinity"):
            return math.inf
        match = _OPERAND.match(arg)
        if match is None:
            continue
        number = match.group(1)
        value = _arith(number) if number.isdigit() else float(number)
        total += value * _UNIT[match.group(2)]
        found = True
    return total if found else None


def _heredoc_bodies(cmd):
    """Every heredoc body in `cmd`, whatever command reads it (the 2026-08-25 ruling)."""
    lexer = shellscan._Lexer(cmd)
    lexer.tokens()
    return [
        cmd[hd.body_start : hd.body_end]
        for hd in lexer.heredocs
        if hd.body_start is not None and hd.body_end is not None
    ]


def _sleeps(cmd):
    """Every sleep in `cmd`, in seconds: the commands bash runs, then the text kept on purpose."""
    found = []
    for run_ in shellscan._analyse(cmd).runs:
        base = run_.name.rsplit("/", 1)[-1]
        if base == "sleep":
            seconds = _duration(run_.argv)
            if seconds is not None:
                found.append(seconds)
        elif base in _ELSEWHERE:
            found.extend(_arith(m) for m in _TEXT_SLEEP.findall(" ".join(run_.argv)))
    for body in _heredoc_bodies(cmd):
        found.extend(_arith(m) for m in _TEXT_SLEEP.findall(body))
    return found


def _label(seconds):
    if seconds == math.inf:
        return "infinity"
    return "%d" % seconds if seconds == int(seconds) else "%g" % seconds


def run(ev):
    cmd = ev.raw("tool_input", "command")
    bg = ev.flag("tool_input", "run_in_background")

    # The MAXIMUM sleep in the command, not the first one.
    ordered = sorted(_sleeps(cmd))
    value = ordered[-1] if ordered else None

    limit = FG_MAX
    if bg == "true":
        limit = BG_MAX

    sleep_val = _label(value) if value is not None else ""
    if value is not None and value > limit:
        if bg == "true":
            ev.warn(
                "❌ BLOCKED: sleep %ss exceeds %ss even for a background task. A watch that "
                "idles this long is not polling, it is asleep; tighten the interval."
                % (sleep_val, BG_MAX)
            )
        else:
            ev.warn(FG_MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
