#!/usr/bin/env bash
# Block git restore/checkout/rm of protected hook files.
#
# THE VERB AND THE PATH MUST BE IN THE SAME CLAUSE. The original pattern joined
# them with `.*`, which spans `&&`, `;` and `|`, so a command that checked out a
# branch and then merely READ a protected file was refused:
#
#   git checkout main && cat .claude/settings.json
#
# Nothing there restores anything. `[^;&|]*` keeps the match inside one clause,
# which is the smallest change that tells "restore this file" apart from
# "restore something, then look at this file".
#
# Verified on 2026-08-27, when this guard blocked the very command that was
# measuring it -- the probe's line contained the fixture text and never ran. A
# guard that cannot be measured without tripping over itself is one nobody
# measures, which is how it sat with a block case and no allow case.
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
PROTECTED='(\.claude/settings\.json|scripts/pre-commit-check\.sh)'
if printf '%s' "$SCAN" | grep -qE "(git restore|git checkout|(^|[[:space:];|&])rm[[:space:]])[^;&|]*$PROTECTED"; then
    echo "❌ BLOCKED: Cannot delete or restore protected hook files" >&2
    exit 2
fi
exit 0
