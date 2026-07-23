#!/usr/bin/env bash
# Block CI polling: sleep then gh run view/list.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'sleep[[:space:]]+[0-9]+[^|;&]*(&&|;)[[:space:]]*[^|;&]*gh[[:space:]]+run[[:space:]]+(view|list)'; then
    echo '❌ BLOCKED: CI polling pattern detected (sleep then gh run view/list). Polling chews through context and re-fetches the same job tree over and over. Use ONE of: (a) read the existing background watch task output at the path printed when it started, and wait for the completion notification automatically; (b) arm a terminal-state watch in the background (run_in_background:true): R=RUN_ID; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs. Do NOT use gh run watch as the wake-up -- it has dropped silently on terminal runs (observed 4/4); a process exit on terminal state is the reliable notification.' >&2
    exit 2
fi
exit 0
