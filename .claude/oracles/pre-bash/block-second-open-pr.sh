#!/usr/bin/env bash
# ONE OPEN PR AT A TIME. Refuse `gh pr create` when this author already has an
# open PR in the target repo.
#
# WHY THIS IS A HOOK AND NOT A LINE IN CLAUDE.md. The operator's ruling, and the
# incident behind it: a single session opened FOUR stacked PRs over one night,
# each one individually reasonable (new work arrived, it needed a base, the
# previous PR was not merged yet), and the result was four unmerged PRs waiting
# on one person. Nothing in CLAUDE.md or the pr-babysit command stopped it,
# because instructions only bind a session that reads them, remembers them, and
# applies them at the one second that matters. PreToolUse is the only surface
# that can DENY the command before it runs, which is the difference between a
# preference and a control.
#
# WHAT TO DO INSTEAD, and the message says so, because a block without a next
# step just gets worked around: push the new work onto the EXISTING PR's branch.
# That is almost always what was wanted anyway. A second PR is the right answer
# only when the work is genuinely independent and the operator has said so.
#
# FAILS CLOSED. If the open-PR list cannot be read, this refuses rather than
# waving the create through: `gh` being unreachable is not evidence that no PR
# exists, and creating a duplicate is the expensive direction of the error.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[[ -n "$CMD" ]] || exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
hook_gh_pr_at_command_pos "$SCAN" create || exit 0

SEG=$(hook_gh_pr_segment "$SCAN" create)
REPO=$(hook_target_repo "$SEG" "$SCAN" "$CWD")

LIST=$(gh pr list --repo "$REPO" --author "@me" --state open \
    --json number,title,headRefName,isDraft 2>&1)
RC=$?

if [[ "$RC" -ne 0 ]]; then
    cat >&2 <<EOF
❌ BLOCKED: cannot verify whether an open PR already exists in $REPO, so this
   \`gh pr create\` is refused rather than risking a duplicate.

   gh said: $(printf '%s' "$LIST" | head -2)

   An unreadable list is not evidence that the list is empty. Fix the gh
   problem and retry, or ask the operator to create the PR.
EOF
    exit 2
fi

COUNT=$(printf '%s' "$LIST" | jq 'length' 2>/dev/null || echo 0)
[[ "$COUNT" -gt 0 ]] || exit 0

ROWS=$(printf '%s' "$LIST" | jq -r '.[] | "     #\(.number) \(.title[0:64]) [\(.headRefName)]\(if .isDraft then " (draft)" else "" end)"' 2>/dev/null)

cat >&2 <<EOF
❌ BLOCKED: you already have $COUNT open PR(s) in $REPO. One at a time.

$ROWS

   WHY: four stacked PRs from one night is what bought this rule. Each new PR
   looked reasonable on its own, and the pile landed on the operator, who has to
   review and merge them in order. A second PR does not get work finished
   sooner; it just splits one decision into several.

   DO THIS INSTEAD: push the new work onto the branch of the PR above and
   refresh its body. That is almost certainly what you wanted, and it keeps the
   whole change reviewable as one thing.

   A genuinely independent second PR is the operator's call, not yours. Ask,
   and say why the work cannot ride the open one.
EOF
exit 2
