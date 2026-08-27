#!/usr/bin/env bash
# Block raw ssh+docker on a rediacc-managed machine (allow bridge VM 192.168.111.*).
#
# ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant
# matching PROSE: `echo '<the banned command>'` was refused, and so was a
# worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and
# quoted spans while still extracting `sh -c` / `eval` payloads, so a command
# hidden in a wrapper is scanned exactly as before -- this narrows what the
# guard refuses, never what it catches.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
if printf '%s' "$SCAN" | grep -qE '\bssh\b[[:space:]][^|;&]*\bdocker\b' && ! printf '%s' "$SCAN" | grep -qE '\bssh\b[[:space:]][^|;&]*192\.168\.111\.'; then
    echo "❌ BLOCKED: Do not run raw ssh+docker on a rediacc-managed machine. Use: ./rdc.sh term connect -m MACHINE -r REPO -c DOCKER_CMD. That runs inside the repo sandbox with DOCKER_HOST preset, no sudo needed. Only bypass by editing .claude/settings.json if rdc genuinely cannot reach the daemon (e.g. host-level docker, not a rediacc repo)." >&2
    exit 2
fi
exit 0
