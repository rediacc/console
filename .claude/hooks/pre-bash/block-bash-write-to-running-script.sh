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
#
# HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB, and excluding them is not a
# loophole -- it is the difference between this guard working and this guard
# making a whole directory uneditable. Every pre-bash guard executes on EVERY
# Bash call, including the one carrying your edit. So while you edit
# block-binary-deploy.sh, that guard is running, as a sibling in the chain
# evaluating that very edit. This fired on exactly that on 2026-08-27, and the
# block is PERMANENT: there is no moment when a pre-bash guard is not running
# during a Bash call, so no amount of waiting clears it. It cost four blocked
# commands before the cause was visible, one of them the fix itself.
#
# The exclusion costs close to nothing. A chain evaluator lives for
# milliseconds and is re-read from scratch on the next call, so the lazy-read
# corruption below needs a window that does not exist here. What this guard is
# actually for -- a suite, a build, a background job running for minutes -- is
# untouched, test-hooks.sh included: that runs from the hooks ROOT, not a chain
# directory, so it still matches and still blocks.
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
#
# `$` IS IN THE CHARACTER CLASS so a variable expansion is RECOGNISED and then
# skipped. Without it, `"$SP/mp-$ver.sh"` yielded the candidate `ver.sh` -- the
# tail of a variable name plus the suffix, a filename that appears nowhere. The
# guard cannot know what `$ver` expands to, so it must not guess.
for cand in $(printf '%s' "$CMD" | grep -oE '[A-Za-z0-9_.$/-]+\.sh' | sort -u); do
    case "$cand" in
        *'$'*) continue ;;
    esac
    base=$(basename "$cand")
    # BRACKET THE FIRST CHARACTER so this pgrep cannot match the shell running
    # this hook, whose command line carries the path it was handed. That is the
    # self-matching trap block-self-matching-pgrep exists for, and this is
    # exactly where it would bite again.
    # ANCHOR TO A PATH BOUNDARY. `pgrep -f` matches anywhere in a command line,
    # so a bare basename matches any process whose command line merely CONTAINS
    # it as a substring: `ver.sh` matched a running `wslServer.sh`, and the
    # guard reported VS Code's server as the job about to be corrupted. The
    # basename must start at the beginning, after a `/`, or after whitespace.
    pat="(^|[/[:space:]])[${base:0:1}]${base:1}"
    running=$(pgrep -af -- "$pat" 2>/dev/null |
        grep -vE '\.claude/hooks/(pre-bash|pre-edit|pre-ask|post-bash)/' |
        head -2)
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
