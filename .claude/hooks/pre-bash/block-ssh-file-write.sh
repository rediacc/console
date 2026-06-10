#!/usr/bin/env bash
# Block raw SSH file writes via tee/cat/echo/printf redirection (allow bridge VM 192.168.111.*).
# Stderr/dev-null redirects (2>&1, 2>/dev/null, >/dev/null) are read-only plumbing, not writes.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
STRIPPED=$(echo "$CMD" | sed -E 's/[0-9]?>+[[:space:]]*(&[0-9]|\/dev\/null)//g')
if echo "$STRIPPED" | grep -qE '(\|\s*\bssh\b[[:space:]][^|;&]*\btee\b|\bssh\b[[:space:]][^|;&]*\b(cat|echo|printf)\b[^|;&]*>)' && ! echo "$CMD" | grep -qE '192\.168\.111\.'; then
  echo "❌ BLOCKED: Raw SSH file write detected. Use: ./rdc.sh repo sync upload -m MACHINE -r REPO --local FILE --remote PATH — transfers via rsync with delta compression and proper permissions." >&2
  exit 2
fi
exit 0
