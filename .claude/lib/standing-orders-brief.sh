#!/usr/bin/env bash
# The live-state brief printed by /standing-orders.
#
# This is a SCRIPT and not a pile of `!` one-liners inside the command file for
# two reasons, and the second is the one that matters:
#
#   1. The command file declares `allowed-tools` prefix patterns. A compound
#      one-liner carrying pipes, command substitution and a while-loop is scored
#      by the permission matcher in a way nobody has verified, and the failure
#      mode is a permission prompt on the operator's first invocation of a
#      command whose entire purpose is to be frictionless.
#   2. A script can be RUN. Every block below was driven directly during
#      development; a `!` block inside a markdown file can only be tested by
#      invoking the command, which is a slower loop and leaves the failure modes
#      undiscovered until an operator hits them.
#
# Read-only by construction: it prints, it never writes to the store.
set -uo pipefail

WL=".claude/hooks/stop/worklist.py"
ME="${CLAUDE_CODE_SESSION_ID:0:8}"

# CLAUDE_CODE_SESSION_ID, never CLAUDE_SESSION_ID. The latter DOES NOT EXIST
# (wl_core.py:212 says so in as many words), and a brief keyed off an empty
# prefix silently reports the WHOLE repo's items as "mine" -- the exact
# ownership confusion this command exists to clear up.
if [ -z "$ME" ]; then
    echo "  (no CLAUDE_CODE_SESSION_ID in this environment: cannot tell my items from a peer's."
    echo "   Every count below would be a guess, so none are printed.)"
    exit 0
fi

echo "I am ${ME} on branch $(git branch --show-current 2>/dev/null || echo '?') at $(date -u +%Y-%m-%dT%H:%MZ)"
echo

echo "MY OPEN SLICE (the verb printed per item is the next command; base your report on this, not on memory):"
python3 "$WL" --list --open "$ME" 2>&1 | head -60
echo

all_open=$(python3 "$WL" --list --open 2>/dev/null | grep -c '^  - \[' || true)
mine_open=$(python3 "$WL" --list --open "$ME" 2>/dev/null | grep -c '^  - \[' || true)
deferrals=$(python3 "$WL" --list --open "$ME" 2>/dev/null | grep -c '^  - \[?\]' || true)
echo "OWNERSHIP: ${all_open} open in this repo, ${mine_open} mine, $((all_open - mine_open)) a peer session's."
echo "  The hook blocks only on mine. A peer's items are REPORTED to the operator and never worked, never ticked."
echo "OPEN DEFERRALS OF MINE: ${deferrals}. A queue of these is over-asking, not a backlog:"
echo "  anything settleable from the code, the request, or a sensible default was mine to decide."
echo

# THE LEASE PROBE. This is the block with the most earned confidence in the
# file, because it measures rather than advises.
#
# It probes the OUTPUT STREAM ON DISK, deliberately NOT the harness's roster of
# running tasks. The roster is the thing that lies: it keeps an entry after that
# task's process has died. This session read the roster literally, concluded a
# worker was alive, and came one command away from pointing a second writer at a
# dead worker's files.
#
# Silent about what it cannot measure. A task with no output stream (an agent
# that reports only at completion) is reported as unmeasurable, never accused of
# being dead -- the same discipline the liveness ladder uses.
echo "ARE MY [>] LEASES BELIEVABLE:"
tasks_dir=""
root="${TMPDIR:-/tmp}/claude-$(id -u)/$(pwd | tr -c 'A-Za-z0-9\n' '-')"
if [ -d "$root" ]; then
    for d in "$root"/"$ME"*; do
        [ -d "$d/tasks" ] && tasks_dir="$d/tasks" && break
    done
fi

workers=$(python3 "$WL" --list --open "$ME" 2>/dev/null | grep -o 'worker:[A-Za-z0-9._-]*' | sort -u || true)
if [ -z "$workers" ]; then
    echo "  (none: no in-flight background work claimed by me)"
elif [ -z "$tasks_dir" ]; then
    echo "  Cannot resolve this session's task directory, so no lease can be checked."
    echo "  Treat every [>] below as UNVERIFIED and probe before believing it."
    echo "$workers" | sed 's/^/    /'
else
    echo "$workers" | while read -r w; do
        id="${w#worker:}"
        f="${tasks_dir}/${id}.output"
        if [ -e "$f" ]; then
            size=$(stat -Lc %s "$f" 2>/dev/null || echo 0)
            mins=$((($(date +%s) - $(stat -Lc %Y "$f" 2>/dev/null || date +%s)) / 60))
            echo "    ${id}: ${size} bytes, last grew ${mins}m ago"
            if [ "$size" -eq 0 ] && [ "$mins" -ge 15 ]; then
                echo "      ^ empty and cold. Probe the process before trusting this lease;"
                echo "        an entry can outlive the worker that made it."
            fi
        else
            echo "    ${id}: no output stream this session can see."
            echo "      An Agent's NAME is not a background task id, and a task started after the"
            echo "      last sidecar snapshot is legitimately absent. Probe, do not assume death."
        fi
    done
fi
echo

echo "WAITING FOR ME FROM PEER SESSIONS (silence means nothing is waiting):"
python3 "$WL" --poll "$ME" 2>&1 | head -30
echo

branch=$(git branch --show-current 2>/dev/null || echo '')
if [ -n "$branch" ]; then
    plans=$(ls -1 "agent/${branch}"/PLAN-*.md 2>/dev/null | wc -l | tr -d ' ')
    state_age=$(stat -c %y "agent/${branch}/${ME}/STATE.md" 2>/dev/null | cut -d. -f1 || echo 'MISSING')
    peers=$(find "agent/${branch}" -mindepth 1 -maxdepth 1 -type d ! -name "${ME}" 2>/dev/null | wc -l | tr -d ' ')
    echo "DURABLE CONTEXT: my STATE.md ${state_age}; ${plans} plan file(s) under agent/${branch}/"
    echo "  ${peers} peer session folder(s) beside mine under agent/${branch}/. Theirs to write, mine to read."
    echo "  These survive a reboot. The worklist store lives under \$TMPDIR and does not."
fi
