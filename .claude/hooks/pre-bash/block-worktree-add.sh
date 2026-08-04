#!/usr/bin/env bash
# Block `git worktree add` from the assistant's own Bash tool, unconditionally.
#
# WHY UNCONDITIONAL. A hook has no reliable, verified way to tell "a live
# operator just approved this" from "an autonomous/cron-fired continuation
# with nobody watching" -- there is no session field this codebase's other
# hooks rely on for that distinction, and inventing one on an unverified
# guess is worse than not trying. So the policy is enforced by WHO can get
# the command to run at all, not by the hook reading intent:
#   - An operator who wants a worktree created can run the command
#     themselves via the `!` prefix (CLAUDE.md's documented escape hatch),
#     which never reaches this hook -- that IS "asked the operator, they
#     said yes", made structural rather than inferred.
#   - An autonomous/cron-fired session has no live operator to relay that
#     to, so the practical effect is worktree creation never happens there,
#     which is exactly the "non-interactive: not allowed" requirement.
#
# Found live 2026-08-01: a session created a throwaway worktree+branch for a
# small doc edit mid-/pr-merge, then a second one for a NUL-byte gate fix,
# after the operator had already twice said to keep changes local instead.
# The operator then found six PRE-EXISTING worktrees holding real, unrelated
# work from other sessions sitting untouched in the same repo. Worktrees are
# cheap to create and easy to forget, and each one is a place uncommitted
# work can silently strand outside the one tree everyone actually watches.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[[ -z "$CMD" ]] && exit 0

SCAN=$(hook_scan_target "$CMD")
# Command position: line start (or wrapper-payload line start), or after
# ; & | ( $( or a backtick. `git -C <path> worktree add ...` still matches
# since -C is a flag between `git` and `worktree`, not a new command.
if printf '%s' "$SCAN" | grep -qE "(^|[;&|(]|\\\$\\(|\`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+worktree[[:space:]]+add([[:space:]]|\$)"; then
    echo '❌ BLOCKED: git worktree add is not run from here. Worktree creation needs the operator to approve it explicitly THIS session, then run the command themselves via the `!` prefix (bypasses this hook) -- do not ask the operator through chat and then run it yourself, and never create one in an autonomous/cron-fired continuation with no live operator to ask. Prefer working directly in the current checkout, a plain `git clone`, or an existing worktree instead. If you believe you already have explicit sign-off, hand the exact command back to the operator to run with `!`.' >&2
    exit 2
fi
exit 0
