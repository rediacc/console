#!/usr/bin/env bash
# Block Co-Authored-By / Generated with lines in commits.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qiE 'Co-Authored-By|Generated with'; then
  echo "❌ BLOCKED: Do not add Co-Authored-By or Generated with lines in commits." >&2
  exit 2
fi
exit 0
