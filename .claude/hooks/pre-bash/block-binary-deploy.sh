#!/usr/bin/env bash
# Block manual binary deploys via scp / sudo cp of the renet binary.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE '^scp |sudo cp.*/usr/local/bin/renet'; then
  echo "❌ BLOCKED: Do not manually deploy binaries via scp/ssh. Use ./rdc.sh which handles provisioning automatically." >&2
  exit 2
fi
exit 0
