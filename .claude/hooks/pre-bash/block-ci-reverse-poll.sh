#!/usr/bin/env bash
# Block reverse CI polling: gh run view ... --jq then sleep.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'gh[[:space:]]+run[[:space:]]+view[[:space:]]+[0-9]+[^|;&]*--jq[^|;&]*&&[[:space:]]*sleep'; then
  echo '❌ BLOCKED: Reverse polling pattern (gh run view followed by sleep). Polling chews through context. Arm a terminal-state watch in the background (run_in_background:true): R=RUN_ID; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs. Do NOT use gh run watch -- it has dropped silently on terminal runs (observed 4/4).' >&2
  exit 2
fi
exit 0
