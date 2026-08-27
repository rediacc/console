#!/usr/bin/env bash
# Block running the CLI bundle directly via node.
#
# THE ENTRY ARGUMENT IS THE TEST, not the presence of a path anywhere in the
# line. The original pattern was `node .*(cli-bundle|packages/cli/)`, and `.*`
# spans the whole command, so it refused three things it had no business
# refusing:
#
#   node packages/cli/bundle.mjs        <- this repo's OWN build entry, the
#                                          `build:bundle` script and line 144
#                                          of build-cli-executables.sh
#   node scripts/x.mjs --outdir packages/cli/dist
#                                       <- the path is an OUTPUT flag, not the
#                                          program being run
#   any command merely QUOTING one of those strings
#
# The third is not hypothetical: while measuring this guard on 2026-08-27 it
# blocked the measurement twice, because the probe's own command line contained
# the fixture text. That is the mention-as-execution class, and this session hit
# it nine times across these guards and the ones written to catch it.
#
# So: match `node`, skip its flags, and require the FIRST non-flag argument --
# the program -- to be the bundle. `bundle.mjs` is not `cli-bundle`, so the
# build entry passes by construction rather than by an allowlist.
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
[ -z "$CMD" ] && exit 0

if printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|[[:space:]])node[[:space:]]+(-[^[:space:];|&]+[[:space:]]+)*[^[:space:];|&]*(cli-bundle[^[:space:];|&]*\.[cm]?js|packages/cli/dist/[^[:space:];|&]*)'; then
    echo "❌ BLOCKED: Do not run the CLI bundle directly via node. Use ./rdc.sh instead." >&2
    exit 2
fi
exit 0
