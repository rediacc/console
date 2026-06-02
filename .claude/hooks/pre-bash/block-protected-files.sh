#!/usr/bin/env bash
# Block git restore/checkout/rm of protected hook files.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
PROTECTED='(\.claude/settings\.json|scripts/pre-commit-check\.sh)'
if echo "$CMD" | grep -qE "(git restore|git checkout|(^|[[:space:];|&])rm[[:space:]]).*$PROTECTED"; then
  echo "❌ BLOCKED: Cannot delete or restore protected hook files" >&2
  exit 2
fi
exit 0
