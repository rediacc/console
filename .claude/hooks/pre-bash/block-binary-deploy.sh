#!/usr/bin/env bash
# Block manual binary deploys via scp / sudo cp of the renet binary.
#
# DEPLOYING IS UPLOADING. The original pattern was `^scp `, which refuses every
# scp of every file in either direction -- including the one that is not a
# deploy at all:
#
#   scp host:/var/log/renet.log ./logs/     <- pulling a log back to diagnose
#
# That is the opposite of deploying a binary, and refusing it pushes the work
# onto a clumsier path with no benefit. A guard is judged by what it lets
# through as much as by what it stops, and until 2026-08-27 nothing here
# asserted this one let anything through.
#
# The direction is decidable: scp's LAST argument is its destination, and a
# destination naming a remote host (`host:path`, `user@host:path`) is an
# upload. Anything else is a download.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# The renet binary specifically, however it gets there.
if printf '%s' "$CMD" | grep -qE 'sudo cp[^;&|]*/usr/local/bin/renet'; then
    echo "❌ BLOCKED: Do not manually deploy binaries via scp/ssh. Use ./rdc.sh which handles provisioning automatically." >&2
    exit 2
fi

# Each scp clause, judged by where it is sending things.
#
# A HERE-STRING, not a pipe, and the first draft got this wrong twice in one
# line. Piping put the loop in a subshell where `exit 2` could not leave the
# script; worse, `printf '%s'` gave the clauses no trailing newline, so `read`
# returned non-zero on the only line and the body never ran at all. The guard
# reported every upload as ALLOWED and its block case would have gone green on
# a no-op. A here-string supplies the newline and keeps the loop in this shell.
while IFS= read -r clause; do
    printf '%s' "$clause" | grep -qE '(^|[[:space:]])scp[[:space:]]' || continue
    dest=$(printf '%s' "$clause" | awk '{print $NF}')
    # A host spec: a hostname (optionally user@) followed by a colon. A local
    # path containing a colon has a slash before it, so it cannot match here.
    printf '%s' "$dest" | grep -qE '^[A-Za-z0-9_.-]+(@[A-Za-z0-9_.-]+)?:' || continue
    echo "❌ BLOCKED: Do not manually deploy binaries via scp/ssh. Use ./rdc.sh which handles provisioning automatically." >&2
    exit 2
done <<<"$(printf '%s' "$CMD" | tr ';&|' '\n\n\n')"
exit 0
