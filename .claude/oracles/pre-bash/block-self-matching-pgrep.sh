#!/usr/bin/env bash
# Block a wait loop whose `pgrep -f` pattern matches the waiting shell itself.
#
# WHY A HOOK AND NOT A DOCUMENT. This is written down already, in full, at
# docs/agent-reference/TRAPS.md ("A `pgrep -f <pattern>` guard inside a shell
# whose own command line contains that pattern waits forever"), where it is
# recorded as costing 317 minutes. It was also recorded a second time, in
# block-shell-background-waiter.sh's own header: "three rounds chasing
# 'respawning' waiters that were its own pgrep wrappers self-matching". On
# 2026-08-26 a session read neither and launched TWO more, which ran 70 and 63
# minutes past conditions that had already been satisfied. A trap written down
# three times and hit anyway is a trap that needs a gate.
#
# WHAT MAKES IT INVISIBLE. `pgrep -f` matches full command lines, and the
# waiting shell's own command line CONTAINS the pattern, because the pattern is
# part of the command being run. So pgrep always finds at least itself, the
# negation is permanently false, and the loop cannot exit. Nothing looks wrong
# from outside: the Stop hook's liveness check reports "silent but its OS
# process is VERIFIED ALIVE (a loop that prints only at the end is healthy)",
# which is a CORRECT reading of a loop that is genuinely running. A wedged loop
# and a patient one are indistinguishable by liveness; only the exit condition
# tells them apart, and nothing checks that.
#
# THE TEST IS THE BUG ITSELF, which is what makes this precise rather than a
# keyword ban: run the pattern as a regex against the command that contains it.
# If it matches, pgrep will match the waiter too. The documented remedy -- a
# bracket class, `[t]est-hooks.sh` -- makes the regex NOT match its own literal
# text, so a correctly written waiter passes here by construction rather than by
# an allowlist someone has to maintain.
#
# SCOPE: loops only. A one-shot `pgrep -cf X` is contaminated the same way (it
# counts the caller, so it reads one too high) but it costs a wrong number
# rather than an unbounded wait, and blocking every diagnostic pgrep would be
# the over-matching this repo has paid for repeatedly. The message says so.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# A loop, and a pgrep that matches on the full command line (-f, in any flag
# cluster). Either alone is fine.
# THE pgrep MUST BE IN THE LOOP'S CONDITION, not merely somewhere in the same
# command as the word "while". Testing the two independently made this refuse a
# one-shot `pgrep -cf` diagnostic that happened to sit in the same line as a
# worklist message containing the ordinary English word "while" -- a line that
# loops over nothing. That is the sixth mention-as-execution false positive of
# this session, this time in the guard written to stop the previous one.
#
# A loop condition runs from the keyword to the `; do` that closes it, so that
# is the span to search. `[^;]*` keeps it to a single condition rather than
# letting a later, unrelated pgrep pair up with an earlier loop.
# ANCHORED TO COMMAND POSITION 2026-08-28, found by
# check:ci-guard-mention-anchoring. The old group's own [[:space:]] alternative
# defeated it: ANY word followed by a space before `until` matched, so
# "TRAPS.md explains why until pgrep -xf never exits" refused as if it were the
# loop itself. This narrows PROSE only -- the real loop, at line start or after
# a separator, is still caught by the control below.
printf '%s' "$CMD" | grep -qE '(^|[;&|(]|&&|\|\|)[[:space:]]*(until|while)[^;]*pgrep[[:space:]]+-[a-zA-Z]*f' || exit 0

# The pattern is the first argument after the flag cluster: quoted either way,
# or bare up to the next whitespace.
PATS=$(printf '%s' "$CMD" |
    grep -oE "pgrep[[:space:]]+-[a-zA-Z]*f[[:space:]]+('[^']*'|\"[^\"]*\"|[^[:space:];|&)]+)" |
    sed -E "s/^pgrep[[:space:]]+-[a-zA-Z]*f[[:space:]]+//; s/^'(.*)'$/\1/; s/^\"(.*)\"$/\1/")

while IFS= read -r PAT; do
    [ -z "$PAT" ] && continue
    # An unparseable regex is not a verdict: allow what cannot be judged.
    printf '%s' "$CMD" | grep -qE -- "$PAT" 2>/dev/null || continue
    cat >&2 <<MSG
BLOCKED: this wait loop can never exit. Its pgrep pattern matches itself.

  pattern: ${PAT}

\`pgrep -f\` matches FULL COMMAND LINES, and this shell's own command line
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

A one-shot \`pgrep -cf X\` is NOT blocked, but it counts the caller too, so
subtract one or use the bracket form there as well.
MSG
    exit 2
done <<<"$PATS"

exit 0
