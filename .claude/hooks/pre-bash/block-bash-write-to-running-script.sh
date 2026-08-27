#!/usr/bin/env bash
# The Bash half of block-edit-of-running-script.
#
# WHY A SECOND FILE. The pre-EDIT guard only sees the Edit/Write tools. Within
# an hour of shipping it I walked into the same trap through Bash instead --
# a `python3 - <<PY ... p.write_text(...) PY` rewriting test-hooks.sh while FOUR
# copies of it were executing. The guard did not fire because it never saw the
# call. A guard that covers one of two doors is a guard you will walk around
# without noticing, which is exactly what happened.
#
# THE MECHANISM, since the error never points at it: bash reads a script LAZILY,
# by byte offset. Rewrite it mid-run and the interpreter resumes at its old
# offset inside the new bytes and starts parsing mid-token. It dies naming an
# INNOCENT line while `bash -n` on that same file stays clean. Documented at
# docs/agent-reference/TRAPS.md, and hit three times on 2026-08-26/27.
#
# WRITE INTENT IS REQUIRED, not merely the filename. Every second command in
# this repo mentions a .sh path -- running it, grepping it, checking its
# processes. Blocking on the name alone would be the over-matching that gets a
# guard switched off, so this needs a write operator AND a live process.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# A write indicator: a redirect, an in-place edit, a copy/move onto it, or a
# python/perl write. Reading, running and grepping are none of these.
printf '%s' "$CMD" | grep -qE '>[[:space:]]*[^|&;[:space:]]*\.sh|sed[[:space:]]+-i|tee[[:space:]]|write_text|\bcp[[:space:]]|\bmv[[:space:]]|\bshfmt[[:space:]]+-w|>>[[:space:]]*[^|&;[:space:]]*\.sh' || exit 0

# Which .sh files does this command name at all?
for cand in $(printf '%s' "$CMD" | grep -oE '[A-Za-z0-9_./-]+\.sh' | sort -u); do
    base=$(basename "$cand")
    # BRACKET THE FIRST CHARACTER so this pgrep cannot match the shell running
    # this hook, whose command line carries the path it was handed. That is the
    # self-matching trap block-self-matching-pgrep exists for, and this is
    # exactly where it would bite again.
    pat="[${base:0:1}]${base:1}"
    running=$(pgrep -af -- "$pat" 2>/dev/null | grep -v 'block-bash-write-to-running-script' | head -2)
    [ -z "$running" ] && continue
    cat >&2 <<MSG
BLOCKED: '${base}' is being executed right now, and this command writes to it.

  $(printf '%s\n' "$running" | sed 's/^/    /')

Bash reads a script LAZILY, by byte offset. Editing it now makes the running
interpreter resume at its old offset inside your new bytes, so it parses
mid-token and dies at an INNOCENT line -- while \`bash -n\` on the file stays
clean, which is what makes the failure so expensive to chase.

This is TRAPS.md, "Editing a shell script while a background job is RUNNING it".
Hit three times on 2026-08-26/27, twice on this very file. Its Edit-tool sibling
(block-edit-of-running-script.sh) covers the other door; this one exists because
covering only that door meant walking through this one within the hour.

Pick one:
  1. Let it finish. The run you would corrupt is usually the one you are
     waiting on, so editing now costs you the result twice.
  2. Write a COPY and move it into place once the run exits.
  3. If the process is stale rather than working, stop it first.
MSG
    exit 2
done
exit 0
