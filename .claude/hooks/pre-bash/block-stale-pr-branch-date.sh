#!/usr/bin/env bash
# A PR must not be opened from a branch carrying an OLD date.
#
# WHAT WENT WRONG, 2026-08-26: PR #575 was opened from branch `0825-2`. The
# branch itself was created correctly at 23:50 the previous night, but the PR
# was filed the NEXT day, so it shipped with yesterday's number. Nothing
# noticed, because every existing pr-create guard asks a different question:
# block-nondraft-pr-create.sh asks "is it a draft", block-second-open-pr.sh
# asks "is one already open". Neither looks at the branch NAME.
#
# The convention is stated in .claude/commands/pr-babysit.md's state block:
#
#     Today (branch base): `date +%m%d`   (feature branches are `MMDD-N`)
#
# It is keyed to the day the WAVE is filed, which is what makes a stale branch
# name misleading rather than merely untidy: `git branch -r | grep "$(date
# +%m%d)-"` is how a session finds today's waves, and a PR filed from an older
# name is invisible to that lookup.
#
# WHY THIS BLOCKS RATHER THAN RENAMING FOR YOU. A hook that mutated git state
# mid-command would rename the local branch while the remote kept the old one,
# leaving the push tracking a branch that no longer exists -- a worse mess than
# the one it fixed, created at the exact moment the session is not looking. So
# it does the whole computation (including picking the next free N against the
# remote) and hands back a ready-to-run command.
#
# ESCAPE HATCH: PR_BRANCH_DATE_OK=1 for a deliberately long-lived branch, e.g.
# resuming a genuinely multi-day wave onto its original PR. It is an env var and
# not a flag so it cannot be pasted in by habit.

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
hook_gh_pr_at_command_pos "$SCAN" create || exit 0

[[ -n "${PR_BRANCH_DATE_OK:-}" ]] && exit 0

# Fall back to $PWD rather than bailing: a hook already runs with the project
# as its cwd, and bailing on a missing .cwd would be a FAIL-OPEN -- the payload
# that omits it is exactly the one a bypass would use.
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
[[ -n "$CWD" && -d "$CWD" ]] || CWD="$PWD"
[[ -d "$CWD" ]] || exit 0

# The branch this PR would come from: an explicit --head wins, else the checkout.
BRANCH=$(printf '%s\n' "$SCAN" |
    grep -oE '(--head|-H)[[:space:]=]+[A-Za-z0-9._/-]+' |
    head -1 | sed -E 's/^(--head|-H)[[:space:]=]+//')
[[ -n "$BRANCH" ]] || BRANCH=$(git -C "$CWD" branch --show-current 2>/dev/null)
[[ -n "$BRANCH" ]] || exit 0

# Only police the MMDD-N convention. A differently-shaped branch name is out of
# scope here: this guard answers "is the date stale", not "is the name legal",
# and conflating the two would make it fire on every non-wave branch.
[[ "$BRANCH" =~ ^([0-9]{4})-([0-9]+)$ ]] || exit 0
BR_DATE="${BASH_REMATCH[1]}"
TODAY=$(date +%m%d)
[[ "$BR_DATE" == "$TODAY" ]] && exit 0

# Pick the next free N for today, against the remote AND local, so the suggested
# command cannot collide with a wave another session already filed.
NEXT=1
while git -C "$CWD" show-ref --verify --quiet "refs/heads/${TODAY}-${NEXT}" ||
    git -C "$CWD" show-ref --verify --quiet "refs/remotes/origin/${TODAY}-${NEXT}"; do
    NEXT=$((NEXT + 1))
    [[ "$NEXT" -gt 99 ]] && break
done
NEW="${TODAY}-${NEXT}"

cat >&2 <<EOF
❌ BLOCKED: branch '$BRANCH' carries an OLD date; today is $TODAY.

Feature branches are MMDD-N keyed to the day the wave is FILED
(.claude/commands/pr-babysit.md). A PR opened from '$BRANCH' is invisible to
the lookup every session uses to find today's waves:

    git branch -r | grep "\$(date +%m%d)-"

Rename to the next free slot, then re-run your 'gh pr create':

    git -C "$CWD" branch -m "$BRANCH" "$NEW"
    git -C "$CWD" push origin --delete "$BRANCH" 2>/dev/null || true
    git -C "$CWD" push -u origin "$NEW"

Not renaming for you on purpose: doing it mid-command would leave the remote
pointing at the old name while the local branch moved.

If this branch is deliberately long-lived (resuming a multi-day wave onto its
existing PR), re-run with PR_BRANCH_DATE_OK=1.
EOF
exit 2
