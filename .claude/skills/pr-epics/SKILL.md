---
name: pr-epics
description: How a PR carries the structure of its work here - epics, the generated body block, PR-TASK commit trailers, and the per-epic review. Use when starting a wave, committing into an open PR, or when a pr-epic-block or pr-task-trailers gate fails.
user-invocable: false
self-improving: true
---

# pr-epics: the work must be attributable

A big-bang PR is the norm here, so nothing about it can be flat. The worklist is the real record of a wave; an epic groups its items; the PR body is generated from that; each commit names its epic; and the review runs **once per epic** so no task is starved by being crowded out of one shared turn budget.

| you are doing | read |
|---|---|
| grouping a wave's items, publishing the snapshot | [epics.md](epics.md) |
| committing, or a trailer gate is red | [trailers.md](trailers.md) |
| the body block, or `check:ci-pr-epic-block` is red | [body.md](body.md) |
| reviewing, or changing review cost | [review.md](review.md) |

## The chain, in order

    worklist.py --epic <me> new "<title>"      mint an epic
    worklist.py --epic <me> add <eid> <ids...> attach worklist items
    worklist.py --publish <me> <branch>        render agent/pr/<branch>.md
    git commit -m "...\n\nPR-TASK: <eid>"      every commit names its epic
    .ci/scripts/pr/sync-epic-block.sh <pr> <branch>   body block from snapshot

Break the chain anywhere and the symptom appears somewhere else: an unpublished snapshot fails the block gate, an untagged commit is reviewed by nobody at all.

## Cadence: one verified unit, one commit, one tick

CLAUDE.md rule 1 commits verified work as it lands, so the chain runs once per unit rather than once per wave:

    <acceptance check, exit code read>        the unit is verified
    git commit -F <msg> -- <paths>            one epic, its PR-TASK trailer
    worklist.py --tick <me> <id> "commit:<sha> ..."   the tick names the commit

- **One unit, one epic.** A unit that spans two epics is two commits. Above 20 files it needs a
proof line anyway, which is the signal to split it.
- **The lead commits.** A writer's output is committed by the lead after the spot-check, with the
epic of the item the writer was given.
- **A tick with no commit says why**: `nocommit:<no-tracked-change|research|operator-deferred>`.
- **Pushing is separate**: at an epic milestone, at least every 2 hours of committed work, and
before a stop that leaves unpushed commits, each with its `ci:quick` receipt.
- **A `[hotfix]` on `main` carries no `PR-TASK:`** (there is no `agent/pr/main.md`); its
`Hotfix-Evidence:` trailer takes the place of the epic.

## Three things that are not obvious

**Epics live in a sidecar, never the event log.** `compact()` folds the log to `md`/`add`/`lease`, so a novel event kind is destroyed on the next run. Measured: after a compact the log holds only those kinds. `record_intent` learned this first; `wl_epic.py` follows it.

**The store is unreadable from CI.** It lives in TMPDIR, which is why `agent/pr/<branch>.md` exists and why it is the contract every gate diffs against. A stale snapshot is a red gate, deliberately.

**History is never back-filled.** `trapguard` blocks `git filter-repo --message-callback`, after an incident that lost 96 trailers across 93 commits, and `block_git_amend` refuses an amend. A commit is tagged when it is made.

## Where it can go wrong quietly

- An item whose own text contains the body block's closing delimiter would
truncate the PR body. `wl_epic.neutralize()` defangs it; do not bypass it.
- A **typo'd** `PR-TASK` id is worse than a missing one: it looks tagged, so the
commit routes to an epic that does not exist and no pass reads it. The gate validates ids against the snapshot, not merely their shape.
- A matrix over zero epics **skips the review job entirely**. Discovery emits
`[""]` so a PR with no epics still gets exactly one flat pass.
