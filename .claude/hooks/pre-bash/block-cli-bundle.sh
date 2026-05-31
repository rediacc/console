#!/usr/bin/env bash
# Block running the CLI bundle directly via node.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'node .*(cli-bundle|packages/cli/)'; then
  echo "❌ BLOCKED: Do not run the CLI bundle directly via node. Use ./rdc.sh instead." >&2
  exit 2
fi
exit 0
