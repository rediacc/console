# trailers: every commit names its epic

    git commit -m "feat(x): what changed

    PR-TASK: <epic-id>"

The trailer is how an epic's review finds its work: `git log --grep='^PR-TASK: <id>'`. A commit with no trailer belongs to no epic, so it is reviewed by nobody and **nothing reports the gap**. That is strictly worse than the flat review's coverage map, which at least admits what it skipped.

## Two enforcers, and only one of them is real

`.claude/rediacc_hooks/guards/block_untagged_commit.py` catches the common case at the moment it is cheapest to fix. It reads an `-m` message, an `-F -` heredoc and an `-F <file>` on disk; only a piped stdin or a command-substituted message is **opaque to it**, and it deliberately ALLOWS what it cannot read rather than refusing a commit it cannot judge. That blind spot is stated in its own header, not hidden.

`scripts/gates/check-pr-task-trailers.ts` is the real enforcement. It walks the PR's commits through the API and fails **closed** on an unreadable response, following `.ci/scripts/quality/check_claude_attribution.py` rather than the pr-description gate, which fails open.

## Anchored to line start, on purpose

The sibling guard `block_commit_meta.py` states the rule in its header: a guard whose only failure mode is refusing CORRECT input teaches people to reword honest messages until it stops complaining. So a commit whose prose merely *mentions* `PR-TASK` is not tagged; only a real trailer line is. Both a literal newline and an escaped `\n` count, because `$'...'` delivers the first and
a `-m` string written with `\n` delivers the second.

There is no collision with the two existing message guards: neither `block_commit_meta.py` nor `check_claude_attribution.py` matches `PR-TASK`, and there is no allowlist to update.

## A typo is worse than an omission

An id that does not exist in the published snapshot looks tagged, routes to an epic nobody reviews, and passes any check that only tests the shape. The gate therefore validates ids **against the snapshot**, not against `[0-9a-f]{6,32}`.

## Never back-fill

`trapguard` blocks `git filter-repo --message-callback` without a baseline. The recorded incident is exactly this shape: 93 commits rewritten, 96 trailers lost. A commit is tagged when it is made. `block_git_amend` refuses an amend, so a missed trailer is answered by a follow-up commit that names the epic, never by rewriting history.

## Cadence

CLAUDE.md rule 1 commits each verified unit as it lands, and the chain in [SKILL.md](SKILL.md) runs once per unit:

- **One unit, one epic.** A unit that spans two epics is two commits. Above 20 files it needs a proof line anyway, which is the signal to split it.
- **The lead commits.** A writer's output is committed by the lead after the spot-check, with the epic of the item the writer was given.
- **A tick with no commit says why**: `nocommit:<no-tracked-change|research|operator-deferred>`.
- **Pushing is separate**: at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits, each with its `ci:quick` receipt.
- **A `[hotfix]` on `main` carries no `PR-TASK:`** (there is no `agent/pr/main.md`); its `Hotfix-Evidence:` trailer takes the place of the epic.
