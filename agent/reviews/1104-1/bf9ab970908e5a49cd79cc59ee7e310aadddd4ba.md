# Review bf9ab970: fix(ci-runner): advance and --changed account for lists, names and refs

Commit: bf9ab970908e5a49cd79cc59ee7e310aadddd4ba
Repo: console
Branch: 1104-1
Parent: 2fff2da3b27e283f313f5256cf6ccec6fee279b2
Patch-Id: 56aca3169775db152bd9f2b43c088f60337a3178
Reviewed-At: 2026-11-17T21:02:54Z
Model: claude-haiku-5-5
Cost: $0.0105 USD, 1 call(s), 53.2s
Diff: 34471 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,ci why=Fixes --changed and advance handling of lists/names/refs carries in the CI runner; no new public capability beyond internal scoping fixes.
Dropped: 0
Body-Sig: 4dcc43a299167f7c

## Findings

### bf9ab970.1 [medium] scripts/ci-runner/select.ts:196
Anchor: in-diff
Claim: byRefs returns true for any spec declaring refs without checking changeSet.files, so with an empty change set (clean tree) a path-scoped gate that declares refs is selected, while the file header says it is selected 'by any non-empty change set'; no selftest case covers an empty change set.
Class: doc-contradicts-code
Resolution: not-a-bug | scripts/ci-runner/select.ts:203 fixed by 65ac06bf6 | d778be9d 2026-11-19T06:54:23Z

### bf9ab970.2 [low] scripts/ci-runner/run.ts:584
Anchor: in-diff
Claim: The original JSDoc 'The change set, WITH its provenance...' now sits directly above the new changeSetListings doc block and so documents the wrong function, while changedFiles (line 618) loses its description.
Class: doc-contradicts-code
Resolution: not-a-bug | scripts/ci-runner/run.ts:600 and :629 doc blocks attach correctly | d778be9d 2026-11-19T06:54:24Z
