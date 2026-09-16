# PLAN: the cold backup path for the chunk store
Status: compacted
Full-Text: f7a5351a9 agent/PLAN-cold-path.md
Full-Text-Blob: 94817d485e814eefcb2a0fc24d339c9a8a974c48
Record-Sig: 497574c0

## Why
Cold backup for the chunk store, under the operator's constraint that the downtime be the
SNAPSHOT window and never the transfer window. The design is a datastore-wide barrier
around a constant-time reflink: stop containers, syncfs, stage, restart, and only then
plan and upload, because holding containers down across `buildPlan` would make the outage
O(image). It named three blockers in existing code, one of them live: the cold restart
was passed the SIGTERM-cancelled context, so on the dangerous path the restart was a
no-op and the containers stayed down.

## Outcome
SHIPPED, with one half of the evidence still missing. Header `done` is TRUE about the
code. Measured 2026-09-06.

- The engine split exists: `StageSnapshot` and `PlanFromStaging` in
  `private/renet/pkg/chunkstore/pipeline_linux.go`, with `PlanOptions.OwnsColdBackup` at
  `:59` and `TransientReasonForOwner` at `:109` delegating from the unchanged exported
  `TransientReason` at `:99`. That is BLOCKER 1 closed exactly as designed.
- The barrier is `private/renet/cmd/renet/backup_snapshot_cold.go`, and the 2026-08-15
  correction shipped with it: `containersStillUp` at `:351`, reached through the
  `containersStillUpFn` seam at `:58` and used at `:261`, so the quiesce predicate is
  CONTAINERS and not the daemon.
- The verb: `backupSnapshotCmd.Flags().Bool("cold", ...)` at
  `private/renet/cmd/renet/backup_snapshot.go:160`, the `--cold --dry-run` refusal at
  `:208`, and `ColdWindowMs` on the record at `:62`.
- Step 6 landed console-side:
  `packages/cli/src/services/backup/backup-schedule-unit-generator.ts:168` emits `--cold`
  where it used to throw, and `:312` raises `TimeoutStopSec` to 960 for cold (blob
  98855f51342e20f4b63c2891515079a0df108b15), in commit 120cd9e73, "feat(backup):
  chunk-store cold path, rclone decommission, stop-hook cadence".
- T1, T4 and T5 are Go tests in `backup_snapshot_cold_test.go`: the ordering barrier, the
  SIGTERM-inside-the-window restart, the second run refused having stopped nothing, the
  quiesce failure refused rather than degraded, and the per-phase outage report.
- T3 IS NOT IN THE TREE. The differential round trip (a container appending a monotonic
  counter, restored file with no gap against a live file with one) has no artifact
  anywhere: nothing under `packages/e2e-tests`, `.ci/scripts` or `scripts/drills` names
  `--cold` or `coldWindowMs`. The plan's own header called T3 the remaining half, and it
  still is.

## Lessons
- SAID LOUDLY BECAUSE COMPACTION WOULD OTHERWISE HIDE IT: this plan is not wholly
  finished and it carries NO checkbox boxes, so `--park` is a silent no-op on it
  (`wl_planrec.compact` sets `parked` only when `park and n_open`). It is therefore
  recorded `compacted`, which is EXEMPT from the housekeeping clock, and T3 now has no
  mechanical reminder at all. Anyone reviving this plan should re-add T3 as a real box
  before doing anything else.
- A seam can hide a predicate. The first quiesce verification refused every repository it
  had just selected, three live runs in a row, and no unit test could see it because the
  fixture stubbed the very function whose meaning was wrong.
- Fail closed on an unverifiable quiesce: an unreachable socket counts as still running,
  because a quiesce you cannot verify is exactly what must not be labelled cold.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:30:34Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: none
Gates: none
Why-Source: author
Read-History: `git show 94817d485e814eefcb2a0fc24d339c9a8a974c48` recovers the text; `git log --find-object=94817d485e814eefcb2a0fc24d339c9a8a974c48 --all` names the commit

## History
- 2026-09-06T17:30:34Z compacted by 8f55d4f0 from `done` (record-sig 497574c0)
