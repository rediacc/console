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
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'sleep[[:space:]]+[0-9]+[^|;&]*(&&|;)[[:space:]]*[^|;&]*gh[[:space:]]+run[[:space:]]+(view|list)'; then
    echo '❌ BLOCKED: CI polling pattern detected (sleep then gh run view/list). Polling chews through context and re-fetches the same job tree over and over. Use ONE of: (a) read the existing background watch task output at the path printed when it started, and wait for the completion notification automatically; (b) arm the canonical terminal-state watch from .claude/skills/ci-watch/SKILL.md with run_in_background:true -- note that it waits for the same run_attempt to be complete TWICE, because a watchdog re-run puts a completed run back in progress. Do NOT use gh run watch as the wake-up -- it has dropped silently on terminal runs (observed 4/4); a process exit on terminal state is the reliable notification. If you are EDITING documentation that describes this pattern rather than polling, use the Write tool instead of a shell heredoc.' >&2
    exit 2
fi
exit 0
