# 03 — Fork, Attach `--writes`, Snapshots, and Safe Migration

**Status: AS-BUILT.** Every mechanism below is implemented and proven live. Measured
timings are recorded where the design only had estimates.

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
multiplies this ×N.

**RESOLVED (P0 spike f): the overlay engine is dm-thin, not dm-snapshot.** dm-thin has far
better random-write behavior and, critically, **errors when full instead of hitting
dm-snapshot's hard invalidate cliff** (which loses every write in the fork). Overlay-fill
auto-grow is implemented (`growThinPools`, with `NeedsGrow`/`GrowTarget` threshold logic and
a convergent no-op on a half-grown pool) and is wired to a real scheduled caller: the
storage-maintain systemd timer runs `repository maintain --all --json`.

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

**As-built: these four rules held, and rule 2 is what exposed the real bugs.** The
no-lazy-success guard did its job perfectly: it refused every storage release and reported
"target is busy". What it could not do was name the holder, and that turned out to be the
expensive part. Chasing it produced the **holder taxonomy in 02 §3**, which is the durable
result and which P4 must build a shared teardown primitive around. Two further hygiene bugs
fell out of the same work:

- **#27**: `dmsetup remove` was single-shot and raced udev's open on the umount uevent, so
  `detach --discard` could fail hard and **strand the mapping**. Fixed with a bounded retry
  that breaks on non-busy errors and never falls back to a lazy success.
- **#28**: `repository down` on the kube arm ran `kubectl delete namespace` under the generic
  30-second exec timeout, but that call BLOCKS on pod termination, which is gated by the
  30-second default grace period, which a container whose PID 1 installs no SIGTERM handler
  burns entirely (the kernel gives PID 1 no default disposition). A **guaranteed** collision:
  `down` failed on essentially any real kube repo, leaving it half-down with services stopped
  but the namespace and volumes still live. That half-down state is precisely how the device
  stacks in taxonomy class (c) were being left open. Fixed with a deadline that fits.

## 3. Snapshots and the "one instant" property

- Per-repo moment: with repo-as-folder/image, ONE snapshot covers all its volumes —
  the multi-PV atomicity bug (data+WAL pair) disappears by construction.
- Per-machine moment: BTRFS snapshot of a datastore = every repo in it at one instant
  (exists today as `renet backup`).
- **Whole-cluster moment: RBD GROUP SNAPSHOTS.** Put the cluster's datastore images
  (control-plane's included) in one RBD group; `rbd group snap create` captures all of them
  at one atomic, crash-consistent instant WITHOUT draining or stopping anything.
  Cloning images from a group snapshot exists since Ceph Squid (v19, 2024;
  `rbd clone --snap-id`, added as the building block for cloning groups).
  **PROVEN (P0 spike a, then live throughout P3).** renet's cephadm flow deploys **Ceph Squid
  19.2.4**, so no fallback was needed. Group snap plus clone-from-group-snap via
  `rbd clone --snap-id` with clone-format-2 (pinned at provision) works end to end.

  **Measured:** group snapshot **1.2s to 8.7s**; the clone (`datastore fork`) **0.3s to
  10.5s**; `datastore adopt` **37ms**; dm-thin overlay attach **0.4s to 30.1s**. The parent is
  never stopped: across the fork runs the parent's API served **4941 of 4943 liveness samples
  over 82 minutes** (rv1) and 374/374 and 185/185 with zero gaps (FU#1).
- Local-tier datastores cannot join a group snap: repos on the local tier are documented as
  outside the cluster-instant guarantee (placement = consistency choice).
- **Crash-consistency is a real contract, not a formality.** An e2e test seeded a value and
  snapshotted immediately; the unsynced kine write was correctly absent from the point-in-time
  snapshot. That is the contract working, not a bug. The same lesson as rediacc/console#440:
  if you need a write to be IN the snapshot, sync it first.

## 4. Safe cross-site migration pipeline (user's four-step design, adopted)

**Status: NOT LIVE-VALIDATED.** The **in-Ceph** migrate arm (04 §3) is built and proven with a
measured cutover. This **cross-site** pipeline is not: a two-site validation needs two Ceph
clusters running concurrently, which fits locally but never fits the 16GB GitHub-runner ceiling
(tracked as rediacc/console#521, along with the concurrent parent-plus-fork case). It was
deliberately deferred, not forgotten. Treat everything below as designed-but-unproven, and note
that its two load-bearing primitives (fenced attach and identity rewrite) ARE proven by the fork
and in-Ceph migrate arms.

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
