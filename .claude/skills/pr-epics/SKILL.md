---
name: pr-epics
description: How a PR carries the structure of its work here - epics, the generated body block, PR-TASK commit trailers, and the per-epic review. Use when starting a wave, committing into an open PR, or when a pr-epic-block or pr-task-trailers gate fails.
user-invocable: false
self-improving: true
---

# pr-epics: the work must be attributable

A big-bang PR is the norm here, so nothing about it can be flat. The worklist is
the real record of a wave; an epic groups its items; the PR body is generated
from that; each commit names its epic; and the review runs **once per epic** so
no task is starved by being crowded out of one shared turn budget.

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

Break the chain anywhere and the symptom appears somewhere else: an unpublished
snapshot fails the block gate, an untagged commit is reviewed by nobody at all.

## Three things that are not obvious

**Epics live in a sidecar, never the event log.** `compact()` folds the log to
`md`/`add`/`lease`, so a novel event kind is destroyed on the next run. Measured:
after a compact the log holds only those kinds. `record_intent` learned this
first; `wl_epic.py` follows it.

**The store is unreadable from CI.** It lives in TMPDIR, which is why
`agent/pr/<branch>.md` exists and why it is the contract every gate diffs
against. A stale snapshot is a red gate, deliberately.

**History is never back-filled.** `trapguard` blocks
`git filter-repo --message-callback`, after an incident that lost 96 trailers
across 93 commits. Tag commits when you make them.

## Where it can go wrong quietly

- An item whose own text contains the body block's closing delimiter would
  truncate the PR body. `wl_epic.neutralize()` defangs it; do not bypass it.
- A **typo'd** `PR-TASK` id is worse than a missing one: it looks tagged, so the
  commit routes to an epic that does not exist and no pass reads it. The gate
  validates ids against the snapshot, not merely their shape.
- A matrix over zero epics **skips the review job entirely**. Discovery emits
  `[""]` so a PR with no epics still gets exactly one flat pass.
