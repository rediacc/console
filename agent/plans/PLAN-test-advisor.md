# PLAN: a test advisor, not a longer reggate
Status: compacted
First-Seen: 2026-09-20
Owner: b7baf3ee
Full-Text-Blob: 2a9b231bbfe9745800132f1859ddda383771ae94
Record-Sig: 378f05aa

## Why
CI regression testing was fragmented across six surfaces (static gates, E2E on real VMs, ops/KVM provisioning, install methods, unit tests, hooks), but the reggate decision mechanism only recognized one via hardcoded globs. This left gaps where code changes had no acceptable regression gate, and the operator correctly refused the proposal to enumerate all six surfaces in the judge
(the list would rot as new surfaces appeared).

## Outcome
Implemented a routing-via-agent design with a testing skill at `.claude/skills/testing/SKILL.md` plus surface-specific files (gates.md, e2e.md, ops.md, install.md, unit.md, hooks.md), a test-advisor agent at `.claude/agents/test-advisor.md` that loads the skill, and modified reggate logic that calls the advisor for verdict instead of glob patterns. Self-improvement runs through the
existing `skill-test-iterate` mechanism with a 60-line-per-file cap enforced by `check:ci-skill-size`. Landed in commits a1ec17d9, 43b527ca, 3771a92f, ccb19e99, 62d69e1d.

## Lessons
- The 60-line cap per skill file is a forcing function, not decoration—it prevents regression to the long-text accretion the operator identified. Someone relaxing it would undo the core mechanic.
- Self-improvement feedback must come from a separate reader (skill-test-iterate), not append-per-verdict by the author—external critique catches what the author normalized.
- Queued reggate verdicts should be reported via outq_add, never auto-created as worklist items—auto-creation would settle the entire queue without asking and turn the mechanism into a no-op.
- Keep routing inline in the judge prompt for now (not a separate agent call)—one model call per stop beats two for identical information; drift from the skill files is the signal to extract it.
- The six regression surfaces are stable enough to document in skill files, but the routing mechanism must stay agent-based so it can adapt to surfaces that don't yet exist without code changes.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:45:26Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: package.json
Gates: check:ci-parity, check:ci-skill-size
Why-Source: model
Read-History: `git show 2a9b231bbfe9745800132f1859ddda383771ae94` recovers the text; `git log --find-object=2a9b231bbfe9745800132f1859ddda383771ae94 --all` names the commit

## History
- 2026-09-20T16:45:26Z compacted by d778be9d from `done` (record-sig 378f05aa)
