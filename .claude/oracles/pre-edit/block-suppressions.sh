#!/usr/bin/env bash
# Block lint/type suppression directives in Edit/Write/MultiEdit/NotebookEdit content.
#
# NOTE: the banned tokens are written with a trailing char class (e.g.
# eslint-disabl[e]) so this very file never contains the literal token
# contiguously, otherwise this guard would block edits to its own source. The
# [x] class still matches the real token. That convention is not decoration:
# drafting the comment below WITHOUT it got the repair refused by the very guard
# being repaired.
#
# TWO NARROWINGS, both paid for. The original test was "does this content
# contain the token, anywhere, in any file", which is the mention-as-execution
# shape this repo hit twelve times in one session. Measured 2026-08-27, it
# refused:
#
#   docs/style.md   "Never write @ts-ignor[e]; fix the type instead."
#
# That is not a suppression, it is the RULE being written down -- so the guard
# refused the documentation of itself. Its own header had named this exact
# over-block class as a known risk without ever testing for it, which is what an
# allow case of `const x = 1;` buys you: proof the regex is not matching
# literally everything, and nothing else.
#
#   1. CODE FILES ONLY. A directive in Markdown is an example, and an example is
#      how the rule gets taught. A fenced snippet showing the wrong way must
#      stay writable.
#   2. DIRECTIVE POSITION. A real suppression sits immediately after a comment
#      opener: `// @ts-ignor[e]`, `/* eslint-disabl[e] */`, `{/* ... */}`. Prose
#      puts words in between, and those words are what tell the two apart. This
#      is a property of the syntax rather than a keyword list, so it does not
#      need maintaining as people find new ways to phrase a sentence.
INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$FILE" in
    *.ts | *.tsx | *.js | *.jsx | *.cjs | *.mjs | *.vue | *.svelte | *.astro) ;;
    # No file_path at all still gets checked: a payload that names no file could
    # be anything, and defaulting to "not code" would be a hole.
    "") ;;
    *) exit 0 ;;
esac

CONTENT=$(printf '%s' "$INPUT" | jq -r '[.tool_input.content, .tool_input.new_string, .tool_input.new_source, (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")' 2>/dev/null)
[ -z "$CONTENT" ] && exit 0

TOKENS='eslint-disabl[e]|@ts-ignor[e]|@ts-nochec[k]|@ts-expect-erro[r]|biome-ignor[e]'
OPENER='(//+|/\*+|\{[[:space:]]*/\*+|^[[:space:]]*\*+|#)'

if printf '%s' "$CONTENT" | grep -qE "${OPENER}[[:space:]]*(${TOKENS})"; then
    echo "❌ BLOCKED: Do not use eslint-disabl""e, @ts-ignor""e, @ts-nochec""k, @ts-expect-erro""r, or biome-ignor""e. Fix the issue properly." >&2
    exit 2
fi
exit 0
