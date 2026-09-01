#!/usr/bin/env bash
# Refuse `gh pr merge` while the branch still has commits that are only local.
#
# WHY, and it is a near-miss from 2026-09-01 rather than a hypothetical. A land pass had
# pushed head `a3701d631` and was one step from `gh pr merge`. A later commit --
# `23e734384`, a gate fix -- was still local. All five repos here set
# `delete_branch_on_merge: true`, so the merge would have deleted `0831-1` out from under
# it. The commit would not have been "lost" (it sits in the local reflog) but it would have
# been orphaned: not on `main`, not on any branch, not in any PR, and invisible to every
# later `git log` a session runs. It was caught by reasoning about branch deletion, which
# is exactly the kind of catch that works until the once it does not.
#
# WHY A HOOK AND NOT A CI GATE. A gate runs in CI, against the tree that was PUSHED. Local
# unpushed commits are invisible to it by construction -- the gate's own view is the
# evidence that they are missing. The only place this is checkable is the machine holding
# the commits, at the moment the merge is typed. That is here.
#
# NOT COVERED BY warn-remote-drift.sh, which is the nearest thing and looks similar: that
# guard fires only on `git push`, and it checks the OPPOSITE direction (remote moved ahead
# of local, so a push would be stale). Local-ahead-of-remote at merge time is a different
# question with a different answer.
#
# FAIL OPEN on every environmental error -- detached HEAD, no such remote branch, no
# network, a merge typed for some other repo's PR. A guard against orphaning work must
# never become an outage that stops work landing.

CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# `gh pr merge` only. `gh pr view`, `gh pr list`, and a merge typed inside a heredoc that
# documents this hook are all none of its business.
printf '%s' "$CMD" | grep -qE '(^|[|;&[:space:]])gh[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)' || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

BRANCH=$(git symbolic-ref --short -q HEAD) || exit 0
[ -n "$BRANCH" ] || exit 0
# On `main` there is no feature branch to strand, and /pr-merge deliberately ends there.
[ "$BRANCH" = "main" ] && exit 0

# `--repo <other>` means the merge targets a DIFFERENT repository, so this checkout's
# unpushed state is irrelevant to it. Only judge a merge that could delete THIS branch.
REPO_ARG=$(printf '%s' "$CMD" | grep -oE -- '--repo[= ]+[^ ]+' | head -1 | sed 's/.*[= ]//')
case "$REPO_ARG" in
    "" | */console) ;;
    *) exit 0 ;;
esac

REMOTE=$(git rev-parse -q --verify "refs/remotes/origin/$BRANCH" 2>/dev/null) || exit 0
[ -n "$REMOTE" ] || exit 0

AHEAD=$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null) || exit 0
[ -n "$AHEAD" ] || exit 0
[ "$AHEAD" = "0" ] && exit 0

cat >&2 <<MSG
BLOCKED: $AHEAD commit(s) on '$BRANCH' are not pushed, and merging deletes the branch.

$(git log --oneline "origin/$BRANCH..HEAD" 2>/dev/null | sed 's/^/    /' | head -10)

\`delete_branch_on_merge\` is true on all five repos here, so the merge removes
'$BRANCH' as soon as it lands. These commits are not on main, not on any other
branch, and not in any PR. They survive only in this machine's reflog, where no
later \`git log\` will find them.

This is not the same thing as an unclean tree, and it is not the drift that
warn-remote-drift.sh checks: that one fires on \`git push\` when the REMOTE has
moved ahead. This is local work the remote has never seen.

Pick one:
  1. Push them, let CI run, then merge:  git push origin $BRANCH
  2. If they genuinely do not belong in this PR, move them to their own branch
     FIRST (\`git branch <name>\`), so the merge cannot take them with it.
MSG
exit 2
