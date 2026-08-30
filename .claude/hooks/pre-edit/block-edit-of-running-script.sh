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
# HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB. Every guard in a chain executes on
# every tool call in that chain, including the call carrying your edit -- so
# editing a pre-edit guard finds that guard "running", permanently, with no
# moment of quiet to wait for. Its Bash-side sibling hit this on 2026-08-27 and
# blocked four commands including its own repair. A chain evaluator lives for
# milliseconds and is re-read from scratch next call, so the lazy-read window
# below does not exist for it; a suite or background job running for minutes,
# which is what this guard is for, still matches and still blocks.
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
#
# ANCHOR TO A PATH BOUNDARY. A bare basename matches any process whose command
# line merely CONTAINS it as a substring (`ver.sh` inside a running
# `wslServer.sh`). The basename must start at the beginning, after a `/`, or
# after whitespace. Fixed here 2026-08-30 to match the Bash-side sibling
# (block-bash-write-to-running-script.sh), which got this anchor on 2026-08-27
# and this guard never did -- a sibling drift, not a design choice.
PAT="(^|[/[:space:]])[${BASE:0:1}]${BASE:1}"
# `pgrep -af` matches any process whose ARGUMENTS mention the name, which is
# the very trap this guard exists to prevent, wearing a different hat. Fixed
# here 2026-08-30, mirroring the Bash-side sibling's 2026-08-27 fix
# (review-found on PR #579, on a different guard, same class): a running
# `claude -p '<huge prompt text>'` invocation -- the stop-hook judge itself --
# has this exact filename embedded in its prompt (an example inside
# docs/agent-reference/TRAPS.md, quoted in this very file's own comments) and
# was scored as "executing" it. No interpreter was running the script at all.
#
# A process is RUNNING the script only if an interpreter is executing it. So
# require the matching process to BE a shell, and the name to sit in the first
# few argv slots where a script argument lives, rather than buried in a prose
# payload.
RUNNING=""
for RPID in $(pgrep -f -- "$PAT" 2>/dev/null); do
    case "$(ps -o comm= -p "$RPID" 2>/dev/null)" in
        bash | sh | dash | zsh | ksh) ;;
        *) continue ;;
    esac
    RARGS=$(tr '\0' ' ' <"/proc/$RPID/cmdline" 2>/dev/null)
    printf '%s' "$RARGS" | cut -d' ' -f1-4 | grep -qE -- "$PAT" || continue
    printf '%s' "$RARGS" | grep -qE '\.claude/hooks/(pre-bash|pre-edit|pre-ask|post-bash)/' && continue
    RUNNING="$RUNNING$RPID $(printf '%s' "$RARGS" | cut -c1-80)
"
done
RUNNING=$(printf '%s' "$RUNNING" | head -3)
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
