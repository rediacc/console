---
name: backup-storage
description: The backup and restore stack: the content-addressed chunk store and its index and manifest format, dedup and compaction, snapshot creation and pruning, retention and quota policy, the rdc backup and rdc datastore CLI verbs, scheduled backups and their systemd units, cold-backup runs, restore and disaster-recovery drills including round-trip verification, and the hosted backup plane (R2 in production, RustFS on Elite) with its upload budgets. Use for work on backup, restore, snapshot, chunk store, retention, prune, or datastore storage accounting, or when a backup verification or restore drill fails.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

This agent owns the backup and restore stack: the Rediacc-native chunk store (the only backup path; the storage-destination commands are retired), and everything hanging off it (quota, retention, prune, scheduling, restore drills).

## Read the record before the plan

`docs/backup-storage/` holds eleven documents. Only one of them describes the tree as it is: `07-execution-record.md`. The other ten were written on 2026-08-09 before any code existed, and the session that met them with the tree found SEVEN load-bearing claims already stale, two of which would have deleted working code. Read 07 first, then the plan document you need:

| file | what it is |
|---|---|
| `07-execution-record.md` | status, operator decisions, the bugs found in the built system, and every correction to the rest |
| `archive/01-verified-context.md` | what existed before the campaign, plus the findings ledger |
| `archive/02-design.md` | architecture and the 14 scored decisions (superseded in places by 07) |
| `archive/03-implementation-map.md` | per-surface seams with file:line, schema plan, traps by name |
| `archive/04-testing-and-local-loop.md` | the three-tier battery and the local VM topology |
| `08-cutover-runbook.md` | wave 5, the credentialed legs the operator still has to run |

Every `file:line` in those documents is a hypothesis. Re-verify before editing.

## The model, in one paragraph

A fixed grid over the repo's LUKS image: cell `i` covers `[i*C, (i+1)*C)`. A snapshot MANIFEST maps every cell to either ZERO (a hole per FIEMAP metadata, never content-scanned) or the SHA-256 of that cell's ciphertext, which is also the object key: `t/<tenant>/l/<lineage>/c/<sha256>`, lineage = grand_guid so forks dedup against each other. First upload writes all non-zero cells;
every later run reflink-snapshots the image under the repo flock, runs `delta.Compare(anchor, snapshot)` with strategy `physical`, hashes only touched cells, uploads only the hashes the store lacks with a create-only PUT (`If-None-Match`), commits the manifest, then advances the anchor by reflink swap. A manifest is full (`cells`) or a delta against a parent (`parent` plus `changedCells`), and the server's retention collapses a doomed run of deltas into its survivors. Restore composes the manifest chain (cell maps only, no data replay), then parallel-GETs each cell once and writes it at its offset into a sparse file. RTO is bandwidth-bound and constant in history depth.

## Where the code is

| surface | path |
|---|---|
| engine | `private/renet/pkg/chunkstore/` (`grid.go`, `manifest.go`, `journal.go`, `grants.go`, `download.go`, `restore.go`, `pipeline_linux.go`) |
| renet verbs | `private/renet/cmd/renet/backup_*.go`, registered in `pkg/functions/commands/backup.go` |
| control plane | `private/account/src/routes/backups.ts`, `src/services/backup-chunk-store.ts`, `src/dto/backup.dto.ts` |
| CLI | `packages/cli/src/commands/backup.ts`, `backup-ops.ts`, `backup-storage.ts`, `backup-storage-browse.ts`, `backup-strategy.ts` |
| schedules | `packages/cli/src/services/backup/backup-schedule{,-execute,-reconcile,-unit-generator}.ts` |
| drill | `.ci/rediacc_ci/drills/backup.py` (`./run.sh drill backup`) |
| wire gate | `scripts/gates/check-backup-protocol-conformance.ts` (`npm run check:ci-backup-protocol-conformance`) |

Anchors live at `<datastore>/.chunk-anchors/<guid>` and the journal at `/var/lib/rediacc/backup-journal/<datastoreID>-<guid>.json`. The `.chunk-` prefix is load-bearing: three live `.backup-*` scanners exist and one of them DELETES matches, so `.backup-anchors` would be reaped on every `machine prune`.

## Status

The chunk-store path is the only backup path. `renet backup snapshot`, `rdc backup snapshot`, restore (`cmd/renet/backup_restore.go`, `rdc backup restore --at`), quota, retention, browse and the drill all exist. `rdc storage`, storage destinations and storage-typed `repo push/pull` arguments are gone; `repo push/pull` move bytes between machines only. Elite boxes bundle the store (`private/elite/BACKUP.md`).

Open work lives in `agent/plans/PLAN-backup-program.md` (one box per item, each with its acceptance line). **"Restore exists" and "restore is exercised" are different claims**: suite 26's restore tier automates the byte-identity proof and needs the fleet plus a real store, so check the plan's K boxes for what has actually been driven.

## The trap that produced every bug in this stack

Four defects on the commit path were all found AFTER the code was green, and all four had the same shape: **each side was tested against its own fake, so both suites passed while the two sides agreed on nothing.** The verb never sent `machineId`; `addedBytes`/`addedChunkCount` were never populated, so the quota ledger could never increment; `PutManifest` required a field only one
minter produced; and chunks were written one level ABOVE where the server looked, which kills dedup and makes a snapshot unrestorable while still metering it.

The cure is structural and already in place: `check:ci-backup-protocol-conformance` pins six legs of the wire, and renaming a single JSON tag on the Go side alone makes it exit
1. **Do not add a field to one side without adding its conformance leg.** A unit test
that verifies our own signature with our own key proves nothing about the other side; that is exactly how the R2 JWT minter shipped minting credentials live R2 refuses.

Two more of the same class worth carrying:

- A BACKUP-intent session could mint a READ grant, because `mintGrant` checked intent
and `mintReadGrant` did not. Enforcement was one-directional. Found by RUNNING the drill, not by reading code.
- A `hosted-service` backup destination was SILENTLY SKIPPED by the schedule generator:
it looked every destination up in a map of the old storage remotes and dropped what it could not find, and a chunk-store destination has no such entry BY CONSTRUCTION. The operator got a timer that backed up nothing, with no error.

## Decisions that are already made

Do not relitigate these; they are the operator's, recorded in 07 §2.

- **Production R2 uses the PRESIGN minter**, not the locally-signed JWT. The store stays
the native R2 binding; grants are presigned URLs signed with the WORKER keys `ACCOUNT_BACKUP_S3_*`. The production deploy sets those, NOT `ACCOUNT_BACKUP_R2_GRANT_PARENT_*`. The choice is GATED, not commented: `tests/integration/backup-plane-selection.test.ts` fails if the JWT minter is re-selected. Naming, because this family moved twice on 2026-09-02 (durable plan decision 10): the
WORKER/`.env` keys are `ACCOUNT_BACKUP_S3_*` (they were `BACKUP_S3_*`, then briefly `CLOUDFLARE_R2_BACKUP_*`), while the GITHUB org-secret names are still `BACKUP_S3_*` and deliberately have not moved. zod v4 strips an unknown key silently, so a stale spelling here disables the backup plane with no error. Check `private/account/src/types/env.ts` before trusting any of these names.
- **The SERVER names the keys.** `chunkPrefix` and `manifestKey` ride in the grant. The
client never composes an object key; that coupling is what caused the wrong-level chunk write.
- **Quota is the only product lever.** No licensing or tier gating anywhere in this
feature; every user gets the same functionality. Restore is registered `TierNone` deliberately, because gating disaster recovery behind a licence tier would let an expired subscription lock a customer out of their own data.
- **Quota counts PHYSICAL unique stored bytes** per subscription, so the dedup benefit
passes to the user. Enforced at grant-mint time, before any I/O is spent.
- **A test bucket is named distinctly (for example `example-backups-test`), NEVER `rediacc-backups`**, so no
misconfiguration can cross test and production backups.
- **Clean break on scheduling.** One operator, no external consumers, no compatibility
shims.

## Running things

```bash
./run.sh drill backup --selftest          # the drill; --selftest plants ONE shared
                                           # probe (rediacc_ci.drills.lib) before any
                                           # leg runs, not one per leg
npm run check:ci-backup-protocol-conformance
cd private/renet && go test -race ./pkg/chunkstore/... ./cmd/...
```

Cold-backup runs restart repos concurrently; `REDIACC_COLD_BACKUP_CONCURRENCY` overrides the heuristic. A quota refusal from `backup snapshot` is exit 16 and means prune or upgrade, never debug.

## Out of scope, deliberately

Whole-cluster atomic backup (rbd group snap plus export-diff): v1 restores are per-repo crash-consistent, not cross-repo coordinated, and the docs must keep saying so. Customer-supplied S3 as a backup target, Infrequent Access storage class, and purchasable quota upgrades are all mapped and
none are built. Do not claim continuous data protection or sub-minute replication; this system is neither.
