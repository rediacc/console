#!/usr/bin/env bash
# Block CI polling: sleep then gh run view/list.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'sleep[[:space:]]+[0-9]+[^|;&]*(&&|;)[[:space:]]*[^|;&]*gh[[:space:]]+run[[:space:]]+(view|list)'; then
  echo "❌ BLOCKED: CI polling pattern detected (sleep then gh run view/list). Polling chews through context and re-fetches the same job tree over and over. Use ONE of: (a) read the existing background watch task output at the path printed when it started, and wait for the completion notification automatically; (b) start a fresh background watch: gh run watch RUN_ID --repo rediacc/console --exit-status --interval 100 with run_in_background:true. Do not sleep+view in a loop." >&2
  exit 2
fi
exit 0
