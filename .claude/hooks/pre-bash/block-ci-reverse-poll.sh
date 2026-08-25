#!/usr/bin/env bash
# Block reverse CI polling: gh run view ... --jq then sleep.
#
# The guidance POINTS AT the ci-watch skill rather than embedding a copy of the
# loop. It used to embed one, and on 2026-08-25 that copy was found to be one of
# nine divergent versions across the repo, several of them handing out a form
# that exits on the first `status == completed` -- which is not terminal,
# because the watchdog re-runs a transient failure and bumps run_attempt.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'gh[[:space:]]+run[[:space:]]+view[[:space:]]+[0-9]+[^|;&]*--jq[^|;&]*&&[[:space:]]*sleep'; then
    echo '❌ BLOCKED: Reverse polling pattern (gh run view followed by sleep). Polling chews through context. Arm the canonical terminal-state watch from .claude/skills/ci-watch/SKILL.md with run_in_background:true -- it waits for the same run_attempt to be complete TWICE, because a watchdog re-run puts a completed run back in progress. Do NOT use gh run watch -- it has dropped silently on terminal runs (observed 4/4).' >&2
    exit 2
fi
exit 0
