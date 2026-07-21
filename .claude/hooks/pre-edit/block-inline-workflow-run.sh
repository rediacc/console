#!/usr/bin/env bash
# Block edits that add a fat inline `run:` block to a GitHub workflow.
#
# The rule (enforced in CI by .ci/scripts/quality/check-workflows.sh): a workflow
# `run:` block scalar whose shell logic exceeds 8 non-blank/non-comment lines does
# not belong inline. CI step logic lives in .ci/scripts/<area>/<name>.sh so it is
# locally runnable and shareable across CI systems; the workflow step is env
# wiring + one script call.
#
# This is the fast local nudge for that rule: it fires only for
# .github/workflows/*.yml|yaml edits, only when the new content introduces a
# `run:` block that already crosses the threshold within the edited fragment.
# The CI gate remains the source of truth: it parses whole files, so a fat block
# assembled across several edits still fails there even if no single fragment
# trips this hook.
MAX=8

INPUT=$(cat)

FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$FILE" in
    *.github/workflows/*.yml | *.github/workflows/*.yaml) ;;
    *) exit 0 ;;
esac

CONTENT=$(echo "$INPUT" | jq -r '[.tool_input.content, .tool_input.new_string, .tool_input.new_source, (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")' 2>/dev/null)
[ -z "$CONTENT" ] && exit 0

# Largest run: block logic-line count in the fragment (same block-scalar rules as
# the CI parser: a block owns following blank/deeper-indented lines; a logic line
# is non-blank and does not start with `#`).
WORST=$(printf '%s\n' "$CONTENT" | awk '
function flush() { if (n > max) max = n; inblock = 0 }
{
    line = $0; sub(/\r$/, "", line)
    if (line ~ /^[[:space:]]*$/) next
    match(line, /^ */); cur = RLENGTH
    if (inblock) {
        if (cur > keyindent) { rest = substr(line, cur + 1); if (substr(rest, 1, 1) != "#") n++; next }
        else flush()
    }
    if (line ~ /^[[:space:]]*run:[[:space:]]*[|>]/) { keyindent = cur; inblock = 1; n = 0 }
}
END { flush(); print max + 0 }
')

if [ "${WORST:-0}" -gt "$MAX" ]; then
    echo "❌ BLOCKED: this edit puts a $WORST-line inline 'run:' block in $FILE (limit is $MAX logic lines). Do not add shell logic inline in a workflow. Extract it to .ci/scripts/<area>/<name>.sh (the script header documents required env + how to run it locally), and make the workflow step env wiring + one call to that script. CI enforces this via check-workflows.sh and there is no exemption list: the 52 legacy blocks that used to be grandfathered have all been extracted and the baseline file was deleted, so the rule now holds for every workflow without exception." >&2
    exit 2
fi
exit 0
