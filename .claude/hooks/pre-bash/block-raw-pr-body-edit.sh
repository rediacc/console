#!/usr/bin/env bash
# Refuse a hand-written PR body edit; route it through the tool that rebuilds it.
#
# WHY. The console PR description is not free text any more: it carries a
# delimited worklist-epics block generated from agent/pr/<branch>.md, and CI
# gates on that block matching the published snapshot. A raw
# `gh pr edit --body`/`--body-file` writes the WHOLE body, so it silently drops
# the block, and the next thing anyone learns is a red gate several minutes
# later with no hint of what removed it.
#
# THE SAME CLASS ALREADY BIT THIS REPO ONCE, one level down:
# .ci/scripts/autopilot/submodule-prs.sh's header warns that its block must not
# share markers with refresh-pr-body.sh, "because that hook rewrites the WHOLE
# body on every push and anything inside its markers is destroyed on the next
# one." A whole-body writer is the hazard; this guard is that lesson applied to
# the model's own hands.
#
# NOT BLOCKED, deliberately:
#   - the sanctioned tool itself, .ci/scripts/pr/sync-epic-block.sh, which
#     strips and rebuilds only its own markers;
#   - `gh pr edit` for anything that is not the body: --title, --add-label,
#     --add-reviewer, --milestone. The guard keys on the body flags alone,
#     because a guard whose usual outcome is a false positive teaches people to
#     route around it;
#   - the PostToolUse hook refresh-pr-body.sh and the autopilot scripts, which
#     are not model Bash calls and never reach this chain.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

# ANCHORED AT COMMAND POSITION, not matched anywhere on the line.
#
# The first version grepped the raw string and blocked `echo "never use gh pr
# edit --body by hand"`, which is prose ABOUT the rule, not a violation of it.
# block-commit-meta.sh's header names that failure exactly: "a guard whose only
# failure mode is refusing CORRECT input teaches people to reword honest
# messages until it stops complaining." lib/command-scan.sh already solves this,
# and block-second-open-pr.sh uses the same two calls for `gh pr create`.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# The sanctioned tool is allowed to do exactly what it exists to do.
if printf '%s' "$CMD" | grep -qF 'sync-epic-block.sh'; then
    exit 0
fi

hook_gh_pr_at_command_pos "$SCAN" edit || exit 0

if hook_flag_present "$CMD" body || hook_flag_present "$CMD" body-file; then
    cat >&2 <<'MSG'
BLOCKED: do not write a PR body by hand.

The description carries a generated `<!-- worklist-epics:begin -->` block built
from agent/pr/<branch>.md, and a raw `gh pr edit --body` replaces the WHOLE body,
so the block goes with it. CI then fails on a missing block, minutes later,
naming nothing that would point back here.

Use the tool, which strips and rebuilds only its own markers and leaves your
prose alone:

  worklist.py --publish <me> <branch>          # refresh the snapshot
  .ci/scripts/pr/sync-epic-block.sh <pr> <branch>   # sync it into the PR

To change the narrative part of the description, edit it in the GitHub UI or
re-run the sync afterwards. `gh pr edit --title`, `--add-label` and friends are
not affected by this guard.
MSG
    exit 2
fi
exit 0
