#!/usr/bin/env bash
# Block reverse CI polling: gh run view ... --jq then sleep.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'gh[[:space:]]+run[[:space:]]+view[[:space:]]+[0-9]+[^|;&]*--jq[^|;&]*&&[[:space:]]*sleep'; then
  echo "❌ BLOCKED: Reverse polling pattern (gh run view followed by sleep). Same fix as above — use background gh run watch." >&2
  exit 2
fi
exit 0
