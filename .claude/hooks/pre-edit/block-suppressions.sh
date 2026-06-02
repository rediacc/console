#!/usr/bin/env bash
# Block lint/type suppression directives in Edit/Write/MultiEdit/NotebookEdit content.
# NOTE: the banned tokens are written with a trailing char class (e.g. eslint-disabl[e]) so
# this very file never contains the literal token contiguously — otherwise the suppressions
# guard would block edits to its own source. The [x] class still matches the real token.
CONTENT=$(jq -r '[.tool_input.content, .tool_input.new_string, .tool_input.new_source, (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")' 2>/dev/null)
if echo "$CONTENT" | grep -qE 'eslint-disabl[e]|@ts-ignor[e]|@ts-nochec[k]|@ts-expect-erro[r]|biome-ignor[e]'; then
  echo "❌ BLOCKED: Do not use eslint-disable, @ts-ignore, @ts-nocheck, @ts-expect-error, or biome-ignore. Fix the issue properly." >&2
  exit 2
fi
exit 0
