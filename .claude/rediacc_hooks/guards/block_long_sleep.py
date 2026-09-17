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

Known false positive, shared with block-ci-polling.sh and accepted for the same reason: this reads the command TEXT, so a command that merely describes a long sleep -- a commit message quoting the recipe, a doc edit -- is blocked as if it were one. Taking the maximum widened that slightly (the first-sleep reading used to let such text through by accident). Narrowing it to exempt
heredoc bodies would exempt the shape most likely to hide a real long sleep, so it stays; write the file with the Write tool and pass it by path instead.

RE-CONFIRMED 2026-08-27. Nine sibling guards were routed through lib/command-scan.sh that day to stop them matching prose, and this one was routed with them. The suite case pinning the 2026-08-25 ruling turned red and reverted it: the shared scanner drops heredoc bodies, which is the option the ruling names as the most tempting and the worst. The pin worked as designed.

PORT NOTE ON THE COMPARISON, and the transliteration OUTLIVED the bug it faithfully copied. `[[ "$SLEEP_VAL" -gt "$LIMIT" ]]` was bash ARITHMETIC, so a value with a leading zero was read as OCTAL: `024` was twenty, not twenty-four, and the command was allowed even though `sleep` itself waits twenty-four seconds. `08` and `09` are not valid octal at all, so bash printed `[[: 08:
value too great for base` on stderr and the test evaluated false -- the guard both complained and permitted.

This port reproduced all of that, correctly, because a port's job is to answer what its twin answers. THE TWIN WAS THEN FIXED (2026-09-06): it forces base ten
with `10#`, so `024` now blocks and `08` is allowed silently. Faithfulness is to
the twin as it IS, so `_arith` was changed with it, in the same breath. Keeping the octal reading here would have turned a shared bug into a divergence and the differential would have caught it -- which is the differential working.

"AND NO CASE HERE PROVOKES IT" WAS THE WRONG ANSWER, corrected here after the divergence was found by hand rather than by the suite. A port that differs from its twin on an input the corpus never carries is a difference nothing reports, which is exactly the class this whole workstream is built against. So the input is DECLARED in `KNOWN_DIVERGENCES` below: the harness runs it,
requires the exit code and stdout to match, and requires stderr to keep differing -- so the declaration cannot rot into an excuse for a match.
"""

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-long-sleep.sh"
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
    ("a tab between sleep and its argument is not matched", "sleep\t45"),
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


def _numeric(value):
    """`sort -n`'s key: the leading decimal number, leading zeros and all."""
    return int(value) if value.isdigit() else 0


def run(ev):
    cmd = ev.raw("tool_input", "command")
    bg = ev.flag("tool_input", "run_in_background")

    # The MAXIMUM sleep in the command, not the first one.
    #
    # PORT NOTE ON THE PIPELINE. `grep -oE 'sleep +[0-9]+'` uses a literal SPACE and not `[[:space:]]`, so `sleep\t45` is not a sleep as far as this guard is concerned. The second grep then keeps only the digits, and `sort -n | tail -1` picks the largest -- GNU sort falls back to a byte-wise comparison for equal keys, which is why the key below carries the record itself as its
    # tiebreaker.
    spans = hookio.grep_o(r"sleep +[0-9]+", cmd)
    digits = hookio.grep_o(r"[0-9]+", hookio._grep_out(spans))
    ordered = sorted(digits, key=lambda record: (_numeric(record), record))
    sleep_val = ordered[-1] if ordered else ""

    limit = FG_MAX
    if bg == "true":
        limit = BG_MAX

    value = _arith(sleep_val) if sleep_val != "" else None
    if sleep_val != "" and value is not None and value > limit:
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
