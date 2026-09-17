# PLAN: Make deletion reachable — segmented chains, chain-aware prune, enforced retention
Status: compacted
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-backup-quota-delta-gc.md
Full-Text-Blob: d7d85100f0fb4a3a11edddfa56da1c3574dc3fe4
Record-Sig: 8567e958

## Why
The chunk store could grow but could not shrink. renet's `buildPlan` produced a strictly linear delta chain, every manifest after the first naming its predecessor as parent, so the account server's `pruneManifest` dependents check refused every candidate a retention policy would ever pick. It was correct, unreachable, had a passing test and zero production callers, and the server
exposed no delete verb at all. `RetentionPolicySchema` was write-only in the same way: declared in the config schema, consumed by nobody, with a doc comment claiming a server-side enforcement that did not exist. The customer-visible consequence was permanent: `backupUsage.storedBytes` only ever went up, so once quota was reached the next backup was refused forever with a 403
advising a prune verb that did not exist.

## Outcome
SHIPPED, all three legs, measured 2026-09-06. THE HEADER SAYS `Status: draft` AND THE TREE DISAGREES.

- Leg 1, segmented chains, is in renet: `SegmentRecord{RootSnapshotID, Depth}` at
`private/renet/pkg/chunkstore/journal.go:86`, `AdvanceSegment` at :111, `DefaultSegmentMaxDepth` at :106, `Pipeline.SegmentMaxDepth` at `private/renet/pkg/chunkstore/pipeline_linux.go:45`, and the `--segment-depth` override in `cmd/renet/backup_snapshot.go`. The no-migration guarantee is pinned by `private/renet/pkg/chunkstore/segment_test.go:25`, "nil segment forces a full
manifest".
- Leg 2, chain-aware collapse, is in the account server:
`private/account/src/services/backup-gc.service.ts:56` defines `BACKUP_COLLAPSE_MAX_CELLS = 262_144`, the plan's exact constant and value, with the deferral at :454, the over-bound refusal at :569 and `validateManifestShape` at :977 called on six distinct write paths.
- Leg 3, enforced retention, is wired end to end: `retentionPolicySweep` at
`private/account/src/services/backup-gc.service.ts:640`, migration `private/account/drizzle/0051_backup_retention.sql`, three `/retention` routes in `private/account/src/routes/backups.ts`, and the CLI verbs at `packages/cli/src/commands/backup-storage.ts:461`. Account commit d97fa05, console commit 120cd9e73.
- The load-bearing ordering constraint is honoured AND documented at the call site:
`private/account/src/services/backup-gc.service.ts:133-142` runs the retention sweeps before the chunk GC so the chunks their deletions orphan are reclaimed in the same pass.
- The control the plan demanded exists:
`private/account/tests/integration/backup-retention.test.ts:260`, "the control: a retention sweep makes storedBytes go strictly DOWN".

TWO THINGS DID NOT LAND. The drill leg was never added: `scripts/drills/backup.sh:95` reads `LEGS="a,b,c,d,e,f,g,h,j,k"` with no `leg_l`, and nothing drives retention through the `/backup/maintenance` test seam that DOES exist at `private/account/src/routes/test.ts:1066`. And the automatic push of a retention policy from `backup strategy` or `backup run` was dropped, so an operator
must issue `backup retention` by hand, which is precisely the drift risk the plan's section 3.2 said automation would remove. The migration also landed under `drizzle/`, not the `migrations/` directory the plan named; no such directory exists.

## Lessons
- A correct function with zero callers and a passing test is indistinguishable from a
working feature until somebody asks who calls it. `pruneManifest` was in that state for the whole life of the chunk store.
- A schema key nobody reads is worse than a missing one, because its doc comment
makes a promise. `RetentionPolicySchema` claimed server-side enforcement that did not exist.
- Deletion in a delta chain is a shape problem, not a policy problem. No retention
policy can delete anything from a strictly linear chain, so the fix had to change what the engine emits before any policy could take effect.
- Sweep order is load-bearing and invisible: retention must run before chunk GC or
the chunks it orphans wait a whole maintenance cycle. The shipped code says so in a comment at the call site, which is the only place a reader would look.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:10Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: private/renet/pkg/chunkstore/pipeline_linux.go, private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-gc.test.ts, packages/shared/src/config-schema/schemas.ts, private/account/src/db/schema.ts, packages/cli/src/commands/backup-storage.ts, docs/backup-storage/02-design.md, private/account/package.json, packages/shared/src/subscription/types.ts, private/account/src/types/api-token.ts, private/account/src/services/device-code.service.ts, private/renet/.ci/scripts/test/run-tests.sh, private/account/vitest.config.ts, .ci/scripts/private/run-account.sh, .github/workflows/ci-quality.yml, packages/shared/vitest.config.ts, package.json, scripts/ci-runner/manifest.ts, .ci/scripts/ci/scope-map.cjs
Gates: check:test-shared
Why-Source: auto
Read-History: `git show d7d85100f0fb4a3a11edddfa56da1c3574dc3fe4` recovers the text; `git log --find-object=d7d85100f0fb4a3a11edddfa56da1c3574dc3fe4 --all` names the commit

## History
- 2026-09-06T17:06:10Z compacted by 8f55d4f0 from `draft` (record-sig 8567e958)
