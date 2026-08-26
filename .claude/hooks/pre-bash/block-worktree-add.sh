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

# THE WRAPPER SAILED STRAIGHT PAST THE CHECK ABOVE. `./run.sh worktree create`
# reaches scripts/dev/worktree.sh, which runs `git worktree add -b ...` -- the
# exact command this hook exists to stop -- but the text the hook sees never
# contains "git worktree add", so it matched nothing. The block was literal, and
# the wrapper is not literal.
#
# This got more urgent, not less: `worktree create` now also brings a devbox up,
# so the bypass costs a multi-GB image pull and a held port block on top of the
# unwanted checkout.
#
# NO "am I an agent?" SNIFF, deliberately. The operator's `!`-prefixed command
# runs in the SAME session with the SAME environment, so any such test would
# block the sanctioned path too. The `!` prefix bypasses PreToolUse hooks
# entirely, which is the whole mechanism -- there is nothing here to detect.
# The `(bash|sh)[[:space:]]+` prefix is not decoration: `bash
# scripts/dev/worktree.sh create` puts the INTERPRETER in command position, not
# the script, so a command-position-anchored match misses it entirely. Caught by
# driving both forms through this hook rather than reading the regex.
if printf '%s' "$SCAN" | grep -qE "(^|[;&|(]|\\\$\\(|\`)[[:space:]]*((bash|sh)[[:space:]]+)?(\\./)?(run\\.sh|[A-Za-z0-9_./-]*worktree\\.sh)[[:space:]]+(worktree[[:space:]]+)?create([[:space:]]|\$)"; then
    echo '❌ BLOCKED: `run.sh worktree create` creates a git worktree (and now a devbox container with it), so it is the same decision as `git worktree add` and carries the same rule: the operator approves it explicitly THIS session and runs it themselves via the `!` prefix, which bypasses this hook. Do not ask through chat and then run it yourself, and never in an autonomous/cron-fired continuation with no live operator to ask. Prefer the current checkout or an existing worktree. `worktree list`, `switch`, `remove` and `prune` are unaffected.' >&2
    exit 2
fi
exit 0
