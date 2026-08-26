# trailers: every commit names its epic

    git commit -m "feat(x): what changed

    PR-TASK: <epic-id>"

The trailer is how an epic's review finds its work:
`git log --grep='^PR-TASK: <id>'`. A commit with no trailer belongs to no epic,
so it is reviewed by nobody and **nothing reports the gap**. That is strictly
worse than the flat review's coverage map, which at least admits what it skipped.

## Two enforcers, and only one of them is real

`.claude/hooks/pre-bash/block-untagged-commit.sh` catches the common case at the
moment it is cheapest to fix. It sees only the raw Bash string, so
`git commit -F file` and a command-substituted message are **opaque to it**, and
it deliberately ALLOWS what it cannot read rather than refusing a commit it
cannot judge. That blind spot is stated in its own header, not hidden.

`scripts/check-pr-task-trailers.ts` is the real enforcement. It walks the PR's
commits through the API and fails **closed** on an unreadable response, following
`check-claude-attribution.sh` rather than `check-pr-description.sh`, which fails
open.

## Anchored to line start, on purpose

The sibling guard `block-commit-meta.sh` states the rule in its header: a guard
whose only failure mode is refusing CORRECT input teaches people to reword honest
messages until it stops complaining. So a commit whose prose merely *mentions*
`PR-TASK` is not tagged; only a real trailer line is. Both a literal newline and
an escaped `\n` count, because `$'...'` delivers the first and a `-m` string
written with `\n` delivers the second.

There is no collision with the two existing message guards: neither
`block-commit-meta.sh` nor `check-claude-attribution.sh` matches `PR-TASK`, and
there is no allowlist to update.

## A typo is worse than an omission

An id that does not exist in the published snapshot looks tagged, routes to an
epic nobody reviews, and passes any check that only tests the shape. The gate
therefore validates ids **against the snapshot**, not against `[0-9a-f]{6,32}`.

## Never back-fill

`trapguard` blocks `git filter-repo --message-callback` without a baseline. The
recorded incident is exactly this shape: 93 commits rewritten, 96 trailers lost.
Tag commits when you make them; a missed one is fixed by an amend on a commit you
have not pushed, or by a follow-up commit, never by rewriting history.
