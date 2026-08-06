#!/usr/bin/env bash
# Block edits that put Python SOURCE inside a JavaScript/TypeScript file.
#
# THE INCIDENT THIS EXISTS FOR. packages/cli/src/remote/vscode/bootstrap.ts held
# a 130-line Python program inside a template literal, executed on a remote host
# over SSH. No linter, formatter or type checker in this repo could see it, and
# it had grown a code-injection hole: four of the six values interpolated into it
# went in unescaped, so a universalUser of `'; import os; os.system('id'); x='`
# parsed cleanly and executed, under `sudo -u` on the user-switch path. CI now
# catches the class (check:ci-no-inline-python), but CI runs after the edit; this
# refuses it at the keystroke, which is what the operator asked for by name:
# "improve .claude/hooks/ to avoid future incidents".
#
# ONE RULE, TWO ENTRY POINTS, on purpose. The decision lives entirely in
# .ci/scripts/quality/check_inline_python.py, invoked here with --file. A hook
# with its own private regex would drift from the gate, and the direction of
# drift is always the same: the hook grows lenient, the gate stays strict, and
# the difference shows up as a CI failure the author could not reproduce.
#
# THE ESCAPE, and why there is one. Set REDIACC_ALLOW_INLINE_PYTHON=1 in the
# shell that launches the session. A guard with no way past it is a guard
# somebody deletes the first time it is wrong, and deleting it removes the
# protection permanently rather than for one edit. The CI gate is unaffected by
# this variable, so an override buys a local edit, never a merge.

INPUT=$(cat)

FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$FILE" in
    *.ts | *.tsx | *.js | *.jsx | *.cjs | *.mjs) ;;
    *) exit 0 ;;
esac

if [ "${REDIACC_ALLOW_INLINE_PYTHON:-}" = "1" ]; then
    exit 0
fi

CONTENT=$(echo "$INPUT" | jq -r '[.tool_input.content, .tool_input.new_string, .tool_input.new_source, (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")' 2>/dev/null)
[ -z "$CONTENT" ] && exit 0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DETECTOR="$REPO_ROOT/.ci/scripts/quality/check_inline_python.py"

# A missing detector must not read as "clean". It means the hook cannot judge,
# and a guard that cannot judge should say so rather than wave the edit through.
if [ ! -x "$DETECTOR" ]; then
    echo "⚠️  inline-Python guard cannot run: $DETECTOR is missing or not executable. Not blocking, but this edit was NOT checked -- check:ci-no-inline-python still is." >&2
    exit 0
fi

# Judge the FRAGMENT, not the file on disk: the point is to refuse the content
# before it lands. The suffix matters because the detector selects rules by
# file type, so the temp file keeps the real one's extension.
TMP="$(mktemp "${TMPDIR:-/tmp}/inline-python-XXXXXX.${FILE##*.}")"
trap 'rm -f "$TMP"' EXIT
printf '%s\n' "$CONTENT" >"$TMP"

if ! FINDINGS=$("$DETECTOR" --file "$TMP" 2>&1); then
    # Rewrite the temp path back to the real one so the message names a file the
    # author recognises.
    FINDINGS=${FINDINGS//$TMP/$FILE}
    echo "❌ BLOCKED: this edit puts Python source inside $FILE." >&2
    printf '%s\n' "$FINDINGS" >&2
    echo "" >&2
    echo "Python in a JS/TS string is invisible to every tool here: ruff cannot lint or format it, tsc cannot see it, and no reviewer reads a 100-line template literal closely. That is not theoretical -- the last one hid a code-injection hole for as long as the file existed, because values were interpolated into the program's SOURCE." >&2
    echo "" >&2
    echo "Put the program in a real .py file next to the module that runs it, and import it as text (packages/cli/bundle.mjs already carries the esbuild loader; packages/cli/src/types/py-modules.d.ts declares the module). Pass configuration as data -- JSON in argv or on stdin -- never by interpolating into the source, so a value cannot become a statement. packages/cli/src/remote/vscode/setup-script.py is the worked example." >&2
    echo "" >&2
    echo "If this really is the exception, run the session with REDIACC_ALLOW_INLINE_PYTHON=1. The CI gate check:ci-no-inline-python ignores that variable, so the override buys a local edit and never a merge." >&2
    exit 2
fi
exit 0
