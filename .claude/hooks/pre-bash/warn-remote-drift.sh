#!/usr/bin/env bash
# On `git push`, check whether the remote branch has moved past local HEAD
# and STOP the push before it burns a CI round.
#
# WHY (operator, 2026-07-31): a babysat branch gets rebased on the REMOTE by
# GitHub's update-branch (strict_required_status_checks_policy keeps PR
# branches current with main), so a session's local branch silently falls
# behind its own remote. The session then watches a superseded run, or worse
# pushes its stale head, minting a non-fast-forward failure or an extra full
# CI round. One `git fetch` here is cheaper than either.
#
# Scope: plain `git push` in this superproject only. Submodule pushes name
# their own remotes and refs too many ways to second-guess; force-pushes are
# already blocked by block-git-force-push.sh; `--dry-run` is harmless.
# Fail-open on every environmental error (no network, no upstream, detached
# HEAD): a drift CHECK must never become a push outage.

CMD=$(jq -r '.tool_input.command' 2>/dev/null)

echo "$CMD" | grep -qE '(^|[|;&[:space:]])git push([[:space:]]|$)' || exit 0
echo "$CMD" | grep -qE 'git push[^|;&]*--dry-run' && exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

BRANCH=$(git symbolic-ref --short -q HEAD) || exit 0
[ -n "$BRANCH" ] || exit 0

# Bounded fetch of just this branch; fail open on timeout or any error.
timeout 15 git fetch --quiet origin "$BRANCH" 2>/dev/null || exit 0

REMOTE=$(git rev-parse -q --verify "origin/$BRANCH" 2>/dev/null) || exit 0
LOCAL=$(git rev-parse -q --verify HEAD 2>/dev/null) || exit 0
[ "$REMOTE" = "$LOCAL" ] && exit 0

# Remote strictly behind local = a normal push of new commits; let it through.
if git merge-base --is-ancestor "$REMOTE" "$LOCAL" 2>/dev/null; then
    exit 0
fi

AHEAD=$(git rev-list --count "$LOCAL..$REMOTE" 2>/dev/null || echo "?")
cat >&2 <<EOF
❌ BLOCKED: origin/$BRANCH has moved past your local HEAD ($AHEAD commit(s) you do not have; likely GitHub's update-branch rebasing onto main, or another session pushing). Pushing now would fail or waste a full CI round on a stale base. Align FIRST, then push:
  1. Compare: git log --oneline HEAD..origin/$BRANCH  and  git diff HEAD origin/$BRANCH --stat
  2. If your local commits are content-identical to remote ones (a remote rebase), move the pointer losslessly: git reset --keep origin/$BRANCH  (then git submodule update -- <path> for any pointer-only submodule diff)
  3. Otherwise rebase your unpushed commits: git rebase origin/$BRANCH  (never force-push the result)
EOF
exit 2
