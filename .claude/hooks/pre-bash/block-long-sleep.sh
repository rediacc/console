#!/usr/bin/env bash
# Block long FOREGROUND sleeps (catches the sleep+gh-run-view polling pattern).
#
# Two corrections landed 2026-08-25, both found while landing console#574.
#
# 1. It read the FIRST sleep in the command (`head -1`), not the longest. The
#    sanctioned watch contains `sleep 20` in its error arm and `sleep 90` in its
#    stability arm, so it passed this guard purely because of the order the arms
#    happen to appear in. Reordering the case would have blocked the repo's own
#    recommended recipe. It now takes the MAXIMUM, which is what "do not sleep
#    longer than N" was always supposed to mean.
#
# 2. A long sleep is only expensive in the FOREGROUND, where it stalls the
#    session. In a harness background task it costs nothing and is exactly how a
#    terminal-state watch is supposed to idle between polls. The cap is
#    therefore raised for run_in_background, which is what makes the attempt-
#    stable watch (same run_attempt seen twice, 90s apart) expressible at all.
#    block-ci-polling.sh still catches real foreground polling shapes.
# Known false positive, shared with block-ci-polling.sh and accepted for the
# same reason: this reads the command TEXT, so a command that merely describes
# a long sleep -- a commit message quoting the recipe, a doc edit -- is blocked
# as if it were one. Taking the maximum widened that slightly (the first-sleep
# reading used to let such text through by accident). Narrowing it to exempt
# heredoc bodies would exempt the shape most likely to hide a real long sleep,
# so it stays; write the file with the Write tool and pass it by path instead.
FG_MAX=20
BG_MAX=120

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command' 2>/dev/null)
BG=$(printf '%s' "$INPUT" | jq -r '.tool_input.run_in_background // false' 2>/dev/null)

# The MAXIMUM sleep in the command, not the first one.
SLEEP_VAL=$(printf '%s' "$CMD" | grep -oE 'sleep +[0-9]+' | grep -oE '[0-9]+' | sort -n | tail -1)

LIMIT=$FG_MAX
[ "$BG" = "true" ] && LIMIT=$BG_MAX

if [[ -n "$SLEEP_VAL" && "$SLEEP_VAL" -gt "$LIMIT" ]]; then
    if [ "$BG" = "true" ]; then
        echo "❌ BLOCKED: sleep ${SLEEP_VAL}s exceeds ${BG_MAX}s even for a background task. A watch that idles this long is not polling, it is asleep; tighten the interval." >&2
    else
        echo "❌ BLOCKED: Do not use sleep > ${FG_MAX}s in the foreground -- it stalls the session, and it is half of the sleep+gh-run-view polling pattern. To wait on CI, run .ci/scripts/ci/ci-trace.py --wait with run_in_background:true: it owns its own polling interval, so you never write a sleep at all. The CI watchdog auto-retries transient failures and attempt 2 lands on the SAME Console CI run; the script reads the head's rollup, so that rerun replaces the old attempt. Do NOT rely on gh run watch: it has dropped silently on terminal runs (observed 4/4); a process exit on terminal state is the reliable notification. Also: a PostToolUse hook auto-cancels old CI runs on every git push, so you never need to cancel manually." >&2
    fi
    exit 2
fi
exit 0
