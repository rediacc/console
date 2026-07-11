# 03 — Fork, Attach `--writes`, Snapshots, and Safe Migration

## 1. Everything is CoW

In the target model every layer forks copy-on-write: repos by reflink inside the datastore
BTRFS; datastores by RBD snap+clone; clusters by group snap + clones; ephemeral forks even
WRITE copy-on-write (dm-COW overlay). The only operations that copy bytes are cross-site
transfer and cross-datastore repo moves. Engineering note: BTRFS-inside-RBD stacks two CoW
layers — fine (it is exactly what `datastore fork` already does) but benchmark write
amplification on hot databases during implementation. **Review F10 widens that benchmark**:
with a dm-snapshot overlay, BTRFS's never-overwrite-in-place allocation means overlay
consumption tracks ALLOCATION CHURN, not app bytes written — a "small writes" fork can
invalidate its overlay (total loss of the fork's writes) surprisingly fast, and replicate
multiplies this ×N. The P1 spike measures overlay growth vs app bytes on BTRFS-realistic
patterns (noatime) and evaluates **dm-thin as the overlay engine** (much better
random-write behavior; errors when full instead of a hard invalidate cliff).

## 2. The fork-attach `--writes` contract (user decision)

An RBD clone is itself CoW-writable ON CEPH (writes go to the clone's objects; the protected
parent snapshot is untouched — Ceph refuses to delete it while clones exist). The local
dm-COW overlay is a deliberate EXTRA layer that keeps writes off Ceph entirely. So a forked
datastore has two write dispositions, and the operator must choose explicitly:

- `rdc datastore attach <fork> --to <machine> --writes local`
  Today's overlay behavior: instant, zero Ceph footprint, writes live only in a local
  backing file. EPHEMERAL: machine dies or detaches → writes gone; invisible to Ceph
  snapshots/backups. For tests, benchmarks, debugging against production data.
- `rdc datastore attach <fork> --to <machine> --writes ceph`
  Plain clone attach: durable, replicated, snapshot-able, consumes pool space. The
  "promote fork to real datastore" path.
- **Attaching a fork with NEITHER flag FAILS** with a two-sentence teaching error. Plain
  (non-fork) attach needs no flag — ordinary single-writer mount with fencing.
- N machines may hold independent forks of the same datastore concurrently (own clone +
  own overlay each); the parent keeps its single writer.

Operational hardening carried into implementation:
- Move the COW backing default OUT of `/tmp/cowdata` (tmpfs/reboot loss) to a real local
  path; make `--cow-size` prominent; a FULL dm-snapshot overlay is invalidated, so
  storage-health/maintain must watch overlay fill.
- Fencing (exclusive-lock + osd blocklist) applies to plain attach and `--writes ceph`
  only; `--writes local` forks never touch Ceph for writes and need no fencing.

### Storage lifecycle hygiene (inherited from the 2026-07-10 loop-stranding fix, renet 8478420)

The pool-file stranding bug (unlink-while-loop-held → extents alive but unfindable →
phantom ENOSPC, manual `losetup -d` the only exit) is a BUG CLASS the new design multiplies:
per-volume LUKS images (every PVC), dm-COW overlay backing files, replicate ×N, pool files.
Four rules carry forward as storage-layer contract items:
1. **Detach-before-unlink, everywhere**: no backing file is removed until every holder
   (loop AND dm) is verifiably detached; a failed detach fails the operation. Contract-
   tested (the existing mutation-checked tests are the pattern; reuse `FindLoopDevicesFor`
   + the `loopController` seam rather than reimplementing).
2. **No lazy-success before destructive steps**: `umount -l` returns success while busy —
   the original enabler. Failover/detach/discard sequences verify each step completed
   (plain unmount first; kubelet still holding volume mounts ⇒ detach FAILS loudly).
3. **Inventory-driven sweep**: the fix's sweep is safely gated on "pool file missing ⇒
   claimants stale", which cannot generalize to many volumes. The new design has the
   missing ingredient: the `state` bucket knows expected holders; storage-health/maintain
   diffs expected-vs-actual (`losetup -a` incl. the ` (deleted)` suffix trick, PLUS
   `dmsetup ls` — dm devices escape the losetup trick) and reports orphans as leaks,
   auto-sweeping only the provably stale.
4. **Convergent init as a goal**: "a broken machine fixes itself on the next
   create/attach" — the R2-F15 idempotency table requires re-runs against half-broken
   state to converge, not corner-error.

## 3. Snapshots and the "one instant" property

- Per-repo moment: with repo-as-folder/image, ONE snapshot covers all its volumes —
  the multi-PV atomicity bug (data+WAL pair) disappears by construction.
- Per-machine moment: BTRFS snapshot of a datastore = every repo in it at one instant
  (exists today as `renet backup`).
- **Whole-cluster moment: RBD GROUP SNAPSHOTS.** Put the cluster's datastore images
  (control-plane's included) in one RBD group; `rbd group snap create` captures all of them
  at one atomic, crash-consistent instant WITHOUT draining or stopping anything.
  Cloning images from a group snapshot exists since Ceph Squid (v19, 2024;
  `rbd clone --snap-id`, added as the building block for cloning groups). Tentacle
  (v20.2.x, current) added `rbd group info` / `rbd group snap info`.
  **P0 SPIKE (blocking)**: verify which Ceph release renet's cephadm flow deploys and that
  group-snap + clone works end-to-end on the ops fleet; fallback if pre-Squid: fsfreeze +
  per-image snaps (approximate simultaneity), or pin a newer cephadm image.
- Local-tier datastores cannot join a group snap: repos on the local tier are documented as
  outside the cluster-instant guarantee (placement = consistency choice).

## 4. Safe cross-site migration pipeline (user's four-step design, adopted)

```
1. SNAPSHOT      group snap S1 (hot, source serving)          — instant
2. TRANSFER      ship S1 to remote Ceph (rbd export/import or rbd-mirror bootstrap)
   [iterate]     export-diff --from-snap S(n) while running — converging deltas
3. STOP          per-repo down() hooks → final snap S2 → stop  — downtime opens
4. DIFF          send small S1..S2 (or Sn..S2) delta
5. START         attach on dest → identity rewrite → per-repo up() (secrets inject HERE,
                 from config — secrets never ride the data plane) → HEALTH GATE
                 — downtime closes; rollback = restart intact source
```

- Downtime is proportional to the LAST diff, not the data size.
- Same shape on every tier: `rbd export-diff` / `btrfs send -p` / FIEMAP block delta
  (LUKS repo files — tool exists in `private/renet/experimental/fiemap-delta/`).
- **Free dry run**: boot the transferred S1 on the destination as a `--writes local`
  ephemeral fork, run the health gate, discard — rehearse the cutover before touching the
  source. (Productized as `cluster rehearse`, see 04/05.)
- Running `down()` before the final snap upgrades the cutover from crash-consistent to
  clean-shutdown consistent, mirroring what `repo migrate` already does at repo level
  (down → final rsync → up, measured downtime).
