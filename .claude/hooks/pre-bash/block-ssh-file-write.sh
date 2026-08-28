#!/usr/bin/env bash
# Block raw SSH file writes via tee/cat/echo/printf redirection (allow bridge VM 192.168.111.*).
# Stderr/dev-null redirects (2>&1, 2>/dev/null, >/dev/null) are read-only plumbing, not writes.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
# Scan the command, not the prose. Matching raw text meant `echo 'cat a | ssh
# host tee /etc/x'` was refused -- a string, not a write. hook_scan_target drops
# heredoc bodies and quoted spans while still extracting `sh -c` / `eval`
# payloads, so a wrapped ssh-write is caught exactly as before.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
STRIPPED=$(printf '%s' "$SCAN" | sed -E 's/[0-9]?>+[[:space:]]*(&[0-9]|\/dev\/null)//g')
# ANCHORED TO COMMAND POSITION 2026-08-28, found by
# check:ci-guard-mention-anchoring. The first branch already required an actual
# `|` before `ssh`; the SECOND had no anchor at all, so
# "echo the guard blocks ssh ... cat > file redirections" refused as if it were
# the write itself. hook_scan_target's quote-stripping above covers the QUOTED
# case only, same class as block-git-empty-commit.sh's fix the same day.
if echo "$STRIPPED" | grep -qE '(\|\s*\bssh\b[[:space:]][^|;&]*\btee\b|(^|[;&|(]|&&|\|\|)[[:space:]]*\bssh\b[[:space:]][^|;&]*\b(cat|echo|printf)\b[^|;&]*>)' && ! echo "$CMD" | grep -qE '192\.168\.111\.'; then
    echo "❌ BLOCKED: Raw SSH file write detected. Use: ./rdc.sh repo sync upload -m MACHINE -r REPO --local FILE --remote PATH. That transfers via rsync with delta compression and proper permissions." >&2
    exit 2
fi
exit 0
