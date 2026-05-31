#!/usr/bin/env bash
# Block force-push (--force / -f / --force-with-lease).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'git push[^|;&]*(--force-with-lease|--force([[:space:]]|=|$)|[[:space:]]-f([[:space:]]|$))'; then
  echo "❌ BLOCKED: Do not force-push (--force / -f / --force-with-lease). Force-push overwrites remote history and erases the trace of individual PR changes, which is exactly what broke traceability before. Use a plain 'git push' so each CI fix lands as its own reviewable commit. Rewriting already-pushed history is the user's decision, not an agent's." >&2
  exit 2
fi
exit 0
