#!/usr/bin/env bash
# Block raw ssh+docker on a rediacc-managed machine (allow bridge VM 192.168.111.*).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE '\bssh\b[[:space:]][^|;&]*\bdocker\b' && ! echo "$CMD" | grep -qE '\bssh\b[[:space:]][^|;&]*192\.168\.111\.'; then
  echo "❌ BLOCKED: Do not run raw ssh+docker on a rediacc-managed machine. Use: ./rdc.sh term connect -m MACHINE -r REPO -c DOCKER_CMD — runs inside the repo sandbox with DOCKER_HOST preset, no sudo needed. Only bypass by editing .claude/settings.json if rdc genuinely cannot reach the daemon (e.g. host-level docker, not a rediacc repo)." >&2
  exit 2
fi
exit 0
