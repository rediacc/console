#!/usr/bin/env bash
# Block CI polling: sleep then gh run view/list.
#
# The guidance below deliberately POINTS AT the ci-watch skill instead of
# embedding a copy of the watch loop. It used to embed one, and that copy went
# stale on 2026-08-25: the recipe it handed out exited on the first
# `status == completed`, which is not terminal, because the watchdog re-runs a
# transient failure and bumps `run_attempt`. Six places held that same snippet
# and all six had to be corrected at once. One source, many pointers.
#
# Known false positive, accepted deliberately: this matches per line, so a
# command that merely *describes* the polling pattern (editing these docs, or a
# patch script carrying the old snippet as a search string) is blocked too. The
# check is not narrowed to avoid it, because every narrowing that would let the
# doc edit through also opens a hole for the habit this guards against, and the
# workaround is trivial (write the file with the Write tool instead).
#
#
# NOT ROUTED THROUGH lib/command-scan.sh, and that is a decision rather than an
# oversight. On 2026-08-27 nine sibling guards moved to the shared scanner to
# stop them matching prose. This one did not: the scanner drops heredoc bodies,
# and the operator ruled on 2026-08-25 -- four scored options -- that this guard
# keeps its prose false positive. It fails LOUDLY (a blocked command that names
# its workaround) while every narrowing fails SILENTLY, and a heredoc is exactly
# where a real one would hide. test-hooks.sh pins that ruling with a case
# asserting exit 2, and that case is what caught the attempt.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'sleep[[:space:]]+[0-9]+[^|;&]*(&&|;)[[:space:]]*[^|;&]*gh[[:space:]]+run[[:space:]]+(view|list)'; then
    echo '❌ BLOCKED: CI polling pattern detected (sleep then gh run view/list). Polling chews through context and re-fetches the same job tree over and over. Use ONE of: (a) read the existing background watch task output at the path printed when it started, and wait for the completion notification automatically; (b) run .ci/scripts/ci/ci-trace.py --wait with run_in_background:true -- it keys on the PR head and reads statusCheckRollup, so a watchdog re-run replaces the old attempt instead of fooling the watch. Do NOT use gh run watch as the wake-up -- it has dropped silently on terminal runs (observed 4/4); a process exit on terminal state is the reliable notification. If you are EDITING documentation that describes this pattern rather than polling, use the Write tool instead of a shell heredoc.' >&2
    exit 2
fi
exit 0
