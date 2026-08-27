#!/usr/bin/env bash
# Refuse to edit a shell script that a process is CURRENTLY RUNNING.
#
# WHY A HOOK. This is written down in full at docs/agent-reference/TRAPS.md
# ("Editing a shell script while a background job is RUNNING it"), with the
# mechanism, the 2026-08-09 incident, and the tell. It was hit again on
# 2026-08-26, on the SAME file, with the SAME signature: a backgrounded
# test-hooks.sh died at `line 1179: syntax error near unexpected token 'else'`
# while `bash -n` on that exact file was clean. Cost a full suite pass. A trap
# documented in that much detail and walked into anyway is one that needs a gate
# rather than another paragraph.
#
# THE MECHANISM, because the error never points at it. Bash reads a script
# LAZILY, by byte offset, not into memory. Rewrite the file mid-run and the
# interpreter resumes at its old offset inside the NEW bytes, so it starts
# parsing mid-token. The line it names is innocent and may not even exist at
# that number any more. `bash -n` being clean is the tell: a syntax error the
# syntax checker cannot reproduce is not in the file, it is in the READER.
#
# SCOPE: shell scripts only, and only while something is actually running one.
# A .ts or .py file is read once into memory by its interpreter, so editing it
# mid-run is merely confusing rather than corrupting. Narrow on purpose -- a
# guard that refused every edit to any file with a live process would be the
# over-matching this repo has switched guards off for.
CMD=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0
case "$CMD" in
    *.sh) ;;
    *) exit 0 ;;
esac

BASE=$(basename "$CMD")
# BRACKET CLASS ON THE FIRST CHARACTER, and it is not decoration: without it
# this pgrep matches the shell running this very hook, whose command line
# contains the path it was handed. That is the self-matching trap that block-
# self-matching-pgrep.sh exists for, and writing this guard is exactly where it
# would have bitten again.
PAT="[${BASE:0:1}]${BASE:1}"
RUNNING=$(pgrep -af -- "$PAT" 2>/dev/null | grep -v 'pre-edit/block-edit-of-running-script' | head -3)
[ -z "$RUNNING" ] && exit 0

cat >&2 <<MSG
BLOCKED: '${BASE}' is being executed by a live process right now.

  $(printf '%s\n' "$RUNNING" | sed 's/^/    /')

Bash reads a script LAZILY, by byte offset, not into memory. Editing it now
makes the running interpreter resume at its old offset inside your new bytes,
so it starts parsing mid-token and dies with a syntax error naming an INNOCENT
line -- often one that no longer exists at that number. \`bash -n\` on the file
stays clean throughout, which is what makes the failure so expensive to chase.

This is docs/agent-reference/TRAPS.md, "Editing a shell script while a
background job is RUNNING it". It cost a suite pass on 2026-08-09 and again on
2026-08-26, both times on test-hooks.sh.

Pick one:

  1. Let it finish. The run you would corrupt is usually the one you are
     waiting on anyway, so editing now costs you the result twice.
  2. Edit a COPY and move it into place once the run exits.
  3. If the process is stale rather than working, stop it first -- then the
     edit is safe and this guard goes quiet on its own.
MSG
exit 2
