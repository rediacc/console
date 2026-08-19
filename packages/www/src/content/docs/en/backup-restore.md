---
title: "Backup & Restore"
description: "Snapshot encrypted repositories to content-addressed chunk storage, where only changed cells are uploaded and every snapshot restores directly. Or keep a copy on another machine. Restore anywhere, and automate it with named strategies and systemd timers."
category: "Guides"
tags:
  - backup
  - storage
order: 7
language: en
---

# Backup & Restore

Rediacc backs up encrypted repositories and restores them on the same machine or
a different one. Backups are encrypted because the repository is: what leaves the
machine is the ciphertext, and your repository's LUKS credential is required to
restore.

There are two ways to back up, and they answer different questions.

- **Snapshots to chunk storage** (`rdc backup snapshot`) keep a history you can
  go back through. This is the main path.
- **A copy on another machine** (`rdc repo push`, `rdc repo pull`) keeps the
  repository as it is now on hardware you control. No cloud account is involved.

They are independent. A repository backed up one way is not backed up the other
way.

## How snapshots work

The repository image is cut into fixed-size cells on a fixed grid. Each cell is
either a hole, meaning nothing was ever written there, or it is stored under a
key that **is** the SHA-256 of that cell's ciphertext.

That one decision is where the properties come from.

**Only real changes cost anything.** The first snapshot uploads every written
cell. Every run after it asks the filesystem which extents were touched, reads
and hashes only those, and uploads only the cells the store does not already
hold. A repository whose data barely moved uploads almost nothing, and the run
takes minutes rather than as long as the image is big.

**Identical data is stored once.** Because the key is the content hash, two
snapshots that share a cell share the object, and so do a repository and its
[forks](/en/docs/tutorial-forking): a fork family backs up against one lineage
rather than duplicating its parent.

**Restoring an old snapshot is not slower than restoring a recent one.** There is
no chain of increments to replay through. Restoring resolves the snapshot into a
complete list of cells and fetches those cells directly, so restore time tracks
the size of the image and your bandwidth, not how long you have been taking
backups. Holes stay holes, so a sparse image restores sparse, and a cell that
appears in several places in the image is downloaded once.

**Every snapshot stands on its own.** There is no "full backup" you must not lose
and no window where a broken increment invalidates the ones after it. Any
snapshot in the list is directly restorable.

**Verification is re-hashing, not trust.** Since the key is the hash of the
contents, checking a backup means fetching cells and hashing them.
`rdc backup verify` samples; `rdc backup verify --deep` re-hashes every recorded
cell.

**An interrupted run is not wasted.** Upload resumes without re-sending cells
that already landed, and a restart of a partial restore re-hashes what is already
on disk and reuses it rather than downloading it again.

### What it costs you

Quota is counted in **physical unique stored bytes**: what is actually held after
deduplication, not the sum of what your snapshots logically represent. Thirty
snapshots of a repository that changes slowly cost close to one.
`rdc backup usage` shows stored bytes against your quota, which is a
per-subscription number starting at 10 GB on a Community plan.

### What snapshots need

Snapshot upload goes through the account server, which authorizes each run
against the repository's installed licence and hands the machine a short-lived
grant to write with. So this path needs an account server the machine can reach
and a licensed repository. Without them the snapshot is refused rather than
quietly skipped, and `rdc backup manifests`, `rdc backup usage` and
`rdc backup retention` have nothing to read.

That includes `--dry-run`. The licence is read before the run decides whether it
is planning or uploading, so a dry run is a preview of the work, not a way to try
the command without credentials.

Machine-to-machine push and pull need neither. They are a direct transfer between
two machines already in your config.

### What a snapshot does not promise

- **A snapshot covers one repository, not your whole machine at once.** Each
  repository is captured at its own instant. If two repositories depend on each
  other, their snapshots are not a coordinated pair.
- **It is not continuous replication.** A snapshot is a point you took, and you
  can lose everything written since the last one. How much that is depends on how
  often you run.
- **Stored objects are write-once, not certified WORM.** Cells are written with a
  create-only conditional, the grant a machine gets cannot delete anything, and
  deletions happen server-side under retention policy. That is a real barrier to a
  compromised machine destroying its own backups. It is not a compliance
  certification, and it is not audited as one.

### The rclone storage path is gone

`rdc repo push --to <storage>` and its relatives used to copy a whole backup file
to a cloud provider you registered yourself. Those now refuse a storage
destination and name their replacement. Machine-to-machine transfer never went
through rclone and is unaffected. If you still need to read an archive written
that way, see [Reading an Archive Written Before the
Retirement](#reading-an-archive-written-before-the-retirement).

### Chunk-storage commands

```bash
# Upload a snapshot. First run seeds, later runs send only changed cells.
rdc backup snapshot my-app

# Plan without uploading: reports what would move.
rdc backup snapshot my-app --dry-run

# Stop the containers, freeze, restart, then upload.
rdc backup snapshot my-app --cold

# Distrust the local anchor and re-upload the full inventory.
# This re-uploads everything and re-charges quota; use it only when the
# anchor is known bad.
rdc backup snapshot my-app --reseed

# Check the stored inventory and your quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Option | Description |
|--------|-------------|
| `<repo-ref>` (positional) | Repository to snapshot |
| `--dry-run` | Plan only: no upload. Reports what would move |
| `--cold` | Stop the containers, freeze, restart, then upload. Cannot be combined with `--dry-run` |
| `--reseed` | Distrust the local anchor and upload a full inventory. Re-uploads everything and re-charges quota |
| `--debug` | Enable verbose output |

## Cold Snapshots (`--cold`)

A cold snapshot stops a repository before it is frozen, so the stored image is application-consistent instead of crash-consistent. It runs on the machine itself:

```bash
# Every repository on the default datastore.
sudo renet backup snapshot --cold

# Only the repositories you name. --repo takes a repository GUID and repeats.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` cannot be combined with `--dry-run`. A dry run that stops containers is not dry, and one that does not is not cold, so renet refuses the pair rather than pick a meaning for you.

### What a cold run does

For each selected repository, in this order:

1. Stop its containers.
2. Flush the repository mount and the datastore to disk.
3. Confirm the containers really stopped.
4. Take a copy-on-write reflink of the repository image.
5. Start the containers again.

Only then does the upload begin, with every repository already back up.

The outage is the freeze, not the transfer. A reflink is metadata only, so it takes the same time whether the repository holds 1 GB or 100 GB. An upload does not work that way: it grows with the bytes that changed, and a first snapshot uploads the whole non-zero inventory. Holding containers down until the upload finished would tie the outage to the size of the data, which on a first seed means hours instead of milliseconds.

Every selected repository is stopped inside one window rather than one at a time. That costs a slightly longer outage per repository, and it buys a single consistency point across the whole set.

A repository with no containers running is already quiet. It is snapshotted with no outage at all, and that is a normal result rather than a failure.

### What the outage costs

Measured on a real machine, the whole outage was **222 ms**:

| Phase | Measured | What happens |
|-------|----------|--------------|
| `cold_down` | 64 ms | Containers stop |
| `cold_sync` | 26 ms | Repository mounts and datastore flushed to disk |
| `cold_verify` | 31 ms | Containers confirmed stopped |
| `cold_stage` | 0 ms | Reflink of the repository image |
| `cold_up` | 99 ms | Containers start again |

Restarting the containers dominates, and staging is effectively free: the reflink does not register at millisecond resolution. Read that zero next to the per-repository records rather than on its own, though. A run that refused every repository also reports `cold_stage=0ms`, and only the records say which of the two you are looking at.

The breakdown is the evidence, not decoration. None of these five phases reads or sends repository data, so none of them grows as the backup grows. The one part that does grow, the upload, runs after the outage has already ended.

renet prints the same figures when the run finishes, so you can measure your own machines instead of trusting ours:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Each repository's JSON record carries the same outage and phases, so a later reader can tell a cold snapshot from a hot one without guessing from timing.

### When to choose cold

Hot is the default and the right choice for most repositories. A hot snapshot is crash-consistent, which is the state a repository would be in after a power cut, and it costs no downtime at all. Most databases and queues recover from that state on their own.

Choose cold for data that cannot be safely captured while it is being written. A database holding its own write-ahead log and in-memory state is the obvious case. You are trading a short, measured outage for a snapshot the application can open without recovering first.

### What a cold run refuses

Refusing is the feature. A backup labeled cold that never quiesced anything is a lie you would only find out about at restore time, so renet never quietly downgrades a cold run to a hot one:

- **Containers that did not stop.** After the stop, renet asks the repository's own Docker socket whether anything is still running. If something is, that repository is refused instead of snapshotted. The check fails closed: if the socket cannot be reached or the container list cannot be read, the quiesce counts as unverified, and unverified is refused.
- **A license that cannot be read.** Licenses are checked before the outage rather than after it, because a repository whose license cannot be read could never have uploaded anything. Such a repository is skipped without being stopped. If none of the selected repositories has a readable license, the whole run is refused before a single container goes down.
- **A second cold run on the same datastore.** The lock covers the datastore, and a busy lock is refused outright, having stopped nothing. Two overlapping runs would each stop containers the other believes it owns, and the second would restart repositories the first was still freezing. Skipping the run and waiting for the next one is better than that.

If a run is interrupted while the containers are down, by a `systemctl stop` or a reboot, renet starts them again before it exits. Recovery on the machine is the backstop: it spots a cold backup whose owner is gone and brings those repositories back up.

## Push a Backup to Another Machine

Copy a repository to a second machine over SSH:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` resolves the destination from your config, and `--to-machine
<machine>` says the same thing explicitly. A storage name is refused: that path
is retired.

The encrypted image is copied with the SAME GUID, so this is a backup or a
migration rather than a fork. To get an independent copy, `rdc repo fork` first
and push the fork.

The first push carries the whole image. Every push after it sends only the
changed blocks against an immutable base image kept on both machines, with no
flags to set. `--delta-base <guid>` names that base yourself if you need to.

The pushed copy lands on the target as a backup artifact rather than a running
repository. Turn it into one with `rdc backup restore`:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

For point-in-time backup, use chunk storage instead: `rdc backup snapshot my-app`
uploads only the cells that changed, and `rdc backup restore my-app --at <snapshot>`
brings any of them back.

| Option | Description |
|--------|-------------|
| `<ref>` (positional) | Repository ref to push |
| `--to <remote>` | Destination machine or cluster |
| `--to-machine <machine>` | Destination machine, stated explicitly |
| `--provision <provider>` | Provision the target machine through this cloud provider if it does not exist |
| `--checkpoint` | Create a CRIU checkpoint before pushing (for containers with `rediacc.checkpoint=true` label). Target auto-restores on `repo up` |
| `--force` | Override an existing backup |
| `--bwlimit <limit>` | Bandwidth limit for rsync transfer (e.g. `10M`, `500K`) |
| `--delta-base <guid>` | Transfer only changed blocks against this immutable base GUID. Omit for hands-free auto-base |
| `--strategy <strategy>` | Block-delta strategy when using a delta base: `auto`, `physical`, or `shared` |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Pull a Backup from Another Machine

Bring a repository back from the machine that holds it:

```bash
rdc repo pull my-app --from server-1
```

Add `--up` to mount and deploy it in the same command. To restore from chunk
storage instead, use `rdc backup restore my-app --at <snapshot-id>`.

Pull refuses to overwrite a repository that is currently **mounted**. Unmount it first, pull, then bring it back up with `rdc repo up`. Directory-based repositories are the exception: they sync in place while mounted.

| Option | Description |
|--------|-------------|
| `<ref>` (positional) | Repository ref to pull |
| `--from <remote>` | Source machine or cluster |
| `--from-machine <machine>` | Source machine, stated explicitly |
| `--force` | Override existing local backup |
| `--up` | Mount and deploy the repository after pulling |
| `--bwlimit <limit>` | Bandwidth limit for rsync transfer (e.g. `10M`, `500K`) |
| `--delta-base <guid>` | Receive only changed blocks against this immutable base GUID |
| `--strategy <strategy>` | Block-delta strategy when using a delta base: `auto`, `physical`, or `shared` |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## List Backups

List the snapshots in chunk storage:

```bash
rdc backup manifests my-app
```

Each row is one stored point in time:

| Column | Meaning |
|---|---|
| `Repo` | Repository name resolved from your local config (falls back to GUID for repos not in config) |
| `Snapshot` | The snapshot id. This is what `rdc backup restore --at` takes |
| `Created` | UTC time the snapshot was taken |
| `Total` | Size of the repository image this snapshot represents |
| `Added` | Bytes this snapshot actually uploaded on top of the ones before it |
| `Chunks` | How many cells it added |

To see what a `rdc repo push --to <machine>` left on the destination, ask that
machine what it is holding:

```bash
rdc repo list --machine server-1
```

The pushed copy appears under its own name. A second row carrying a raw GUID
beside it is the retained delta base, which is what makes the next push to that
machine incremental rather than a full transfer.

`rdc backup list --machine <machine>` reads the `hot/` and `cold/` folders that
scheduled runs write into, so it is the wrong tool for a copy that a push placed
there and will show you nothing.

| Column | Meaning |
|---|---|
| `Mode` | `hot` or `cold`. Which scheduled-backup folder this entry lives in |
| `Name` | Repository name resolved from your local config (falls back to GUID for repos not in config) |
| `GUID` | The on-disk repository GUID |
| `Size` | Human-readable size of the backup file |
| `Modified` | UTC timestamp of the file on the machine |

Listing a storage backend is retired along with the rclone arm; the command
refuses and names these two replacements.

## Retention

The server enforces a per-repository retention policy over the chunk store, so
old snapshots are pruned without you deleting anything by hand. With no policy
declared, every snapshot is kept.

```bash
# What is being enforced right now.
rdc backup retention my-app

# Keep a rolling window: 7 daily, 4 weekly, 6 monthly.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Go back to keeping everything.
rdc backup retention clear my-app
```

| Option | Description |
|--------|-------------|
| `--keep-last <n>` | Keep this many of the most recent snapshots |
| `--keep-hourly <n>` | Keep the newest snapshot from each of this many hours |
| `--keep-daily <n>` | Keep the newest snapshot from each of this many days |
| `--keep-weekly <n>` | Keep the newest snapshot from each of this many weeks |
| `--keep-monthly <n>` | Keep the newest snapshot from each of this many months |
| `--keep-yearly <n>` | Keep the newest snapshot from each of this many years |

Give at least one rule. `set` with no rules is refused rather than treated as
"keep nothing", because clearing a policy is what `clear` is for.

## Restore

`rdc backup restore` turns a backup into a live repository, and it is the same
verb for both paths. What differs is what you point it at.

```bash
# A point in time from chunk storage.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# An artifact a push left on a machine.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` takes a snapshot id from `rdc backup manifests`, or an RFC 3339 time such
as `2026-08-14T12:00:00Z`, which resolves to the newest snapshot taken at or
before that moment. A time with no snapshot at or before it is refused rather
than rounded forward.

Restoring under a new name with `--as` overwrites nothing, so a restore drill is
safe to run against a live machine. Restoring onto a name that already exists is
refused.

| Option | Description |
|--------|-------------|
| `<artifact-ref>` (positional) | What to restore. `repo` for a chunk-store snapshot, `repo@place` for an artifact on a machine |
| `--as <name>` | Name for the restored repository (defaults to the artifact name) |
| `-m, --machine <machine>` | Machine to restore onto |
| `--datastore <name>` | Restore into this named datastore, whose attached machine hosts it |
| `--at <time>` | Restore a point in time: a snapshot id or an RFC 3339 time |
| `--up` | Deploy the restored repository after the transfer |
| `--health-window <seconds>` | How long to watch the deployed repository for health |
| `--health-timeout <seconds>` | How long to wait for it to become healthy |
| `-y, --yes` | Skip the confirmation |
| `--debug` | Enable verbose output |

Restoring a repository needs its LUKS credential, which lives in your config. If
you have config storage enabled, that credential comes back with your config on a
fresh machine. If you do not, keep a copy of the config somewhere the machine
failing does not take with it.

### Prove the restore on each machine

A machine that has never round-tripped is not backed up, however green its
uploads look. Uploads and restores fail for different reasons, and the second
kind only shows up when you try.

Do it once per machine, before you rely on the backups:

1. Take a snapshot: `rdc backup snapshot my-app`.
2. Confirm it is recorded: `rdc backup manifests my-app`.
3. Restore it under a throwaway name: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Compare the restored repository against the source, then delete the drill copy with `rdc repo delete my-app-drill --yes`.

Nothing in that sequence touches the live repository, so it is safe on a machine
that is serving traffic. If you are moving off an older backup arrangement, keep
it running until this has passed on that machine at least once. Two backup paths
cost storage; one unproven path costs the data.

## Sync One Repository at a Time

Push and pull act on a single repository, addressed by ref (`name`, `name:tag`, or `name@machine`). There is no "all repositories at once" form: run the command once per repository.

A ref naming a fork and a machine works the same as a bare name:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

The full option lists are under [Push a Backup to Another
Machine](#push-a-backup-to-another-machine) and [Pull a Backup from Another
Machine](#pull-a-backup-from-another-machine).

## Scheduled Backups

Rediacc uses named backup strategies. Each strategy defines a schedule, backup mode, optional bandwidth limit, and file filters. You bind strategy names to machines to control which backups run where.

### Backup Modes

| Mode | Behavior | Downtime |
|------|----------|----------|
| `hot` | Repository image frozen while services keep running (crash-consistent) | None |
| `cold` | Services stopped, snapshot taken, services restarted, snapshot uploaded (app-consistent) | Per-repo stop+start window, parallelised across repos. See "Estimating Cold Backup Downtime" below. |

Use `hot` for services that tolerate crash-consistent snapshots. Use `cold` when you need guaranteed consistency and can accept a brief restart.

### Cold Backup Semantics

A cold backup runs in three phases per included repo: **stop → snapshot → start**. Know where the guarantees end and you'll catch partial failures early.

**What cold backup guarantees:**

- Before the snapshot, every running container in each included repo is gracefully stopped via its Rediaccfile `down()` hook and the per-repo Docker daemon is quiesced. The snapshot is therefore application-consistent, not merely crash-consistent.
- The set of container IDs that were running pre-snapshot is persisted to a sidecar at `/var/run/rediacc/cold-backup-<guid>.running.json`. This is the source of truth for "what should be back up when we're done."
- After the snapshot, the repo's Rediaccfile `up()` hook is invoked to restore the full compose stack.
- A per-run status sidecar at `/var/run/rediacc/cold-backup-<guid>.status.json` records each attempt's phase, result, and any error.

**What cold backup does NOT guarantee:**

- `up()` is best-effort. It can fail for reasons outside cold backup's control (a `depends_on: service_healthy` condition still waiting, a compose-file syntax error, a transient network failure pulling an image). When it fails, cold backup logs the error at error level, writes the status sidecar, and moves on to the next repo.
- When `up()` fails, a **fallback direct restart** kicks in: the running-sidecar is read and each recorded container ID is restarted via direct Docker API (no compose). This gets services back up even if the compose flow has a snag, though without re-running any Rediaccfile hooks.
- If even the fallback fails for some container IDs (for instance, the Docker daemon itself is down), the sidecar is **left in place** so the router watchdog can keep retrying on each tick.

**Watchdog recovery:** on every tick, the watchdog checks for a running-sidecar. Any container ID listed there that is currently stopped gets restarted, *regardless of the container's saved `restart_policy`*. This means services with `restart: on-failure` (which Docker would NOT restart after a clean stop) still come back after a cold backup. Once every listed container is running, the sidecar is deleted.

**How you detect failures:**

- `rdc machine status <machine> --containers` shows running state. Compare against the expected set.
- `/var/run/rediacc/cold-backup-<guid>.status.json` on the machine. Inspect via `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` with a stale `startedAt` means the last backup didn't complete cleanly.
- Logs from the renet backup run (`journalctl -u renet-*` or the direct `rdc backup schedule` invocation) emit a final summary line of the form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. A non-empty `failed_repos` is the grep target.

### Estimating Cold Backup Downtime

Each repo is down only for its own `down()` + `up()` window. On a warm host these are typically:

| Repo shape | Typical stop+start |
|------------|--------------------|
| Small (1-2 containers, no DB) | 5-15 s |
| Medium (web app + cache) | 20-45 s |
| Heavy (DB + queues + mail) | 60-120 s |

The freeze step is a copy-on-write reflink of the repository image. It is metadata only, so it takes the same time whether the repository holds 1 GB or 100 GB, and on a measured run it did not register at millisecond resolution. A repo is not kept down for other repos' freezes. The upload then runs against the frozen copy while every repo is already back up.

**Total wall-clock for the whole run** is governed by how many repos restart concurrently. renet derives this from the host:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Examples:

| Host | Repos | Concurrency | Wall-clock restart |
|------|-------|-------------|--------------------|
| 4 CPU VM | 5 repos, avg 30 s each | 2 | ~75 s |
| 16 CPU server | 10 repos, avg 40 s each | 8 | ~80 s |
| 64 CPU fleet node | 50 repos, avg 40 s each | 8 | ~4 min |

**Override via env:** set `REDIACC_COLD_BACKUP_CONCURRENCY=N` in the backup service's environment (a systemd drop-in is the usual route) to pin a specific value. `=1` forces strictly-serial restarts, useful when debugging a crashloop in one repo's `up()` hook.

If you run a latency-sensitive repo (public web app, mail), its downtime is bounded by its own stop+start (typically 30-90 s), not by the whole run length. Repos are scheduled into concurrency slots in the order they were discovered; there is no priority queue. Give heavy repos their own `--include`-scoped strategy if you need finer-grained scheduling.

### Long-Running Backups and Overlapping Schedules

A cold backup that takes longer than its own schedule interval (for example, a first-seed of a 500 GB repo on a modest link can legitimately need more than 24 h, during which the nightly timer fires again) does not queue or launch a second run. The systemd `Type=oneshot` unit is a single instance: when the timer fires and the service is already `activating`, systemd coalesces the start into the existing job. No new process starts, no run is queued for later.

Concretely, a run that starts Monday 03:00 UTC and finishes Thursday at noon:

| Day | 03:00 UTC fire | Result |
|------|---------------|--------|
| Monday | First fire | Run begins |
| Tuesday | Second fire | Dropped silently (previous run is still active) |
| Wednesday | Third fire | Dropped silently (previous run is still active) |
| Thursday | Run ends at midday | No catch-up; next run is Friday 03:00 UTC |

The timer's `Persistent=true` directive does **not** rescue these fires. `Persistent=true` replays fires that were missed because the timer itself was inactive (system off, timer disabled). Fires dropped because the service was busy are gone.

This default is deliberate. Running two cold backups in parallel against the same datastore would contend on the freeze path, the upload, and the per-repo sidecars at `/var/run/rediacc/cold-backup-<guid>.status.json`. Waiting behind a running instance beats thrashing the same data from two directions. The datastore lock enforces it: a second cold run finds the lock busy and is refused outright, having stopped nothing.

**Monitoring implication.** A hung backup (for instance, an upload wedged on a network blackhole) silently drops every subsequent timer fire. The scheduler emits no alarm. Watch `systemctl show <unit> -p ActiveEnterTimestamp`: if the service has been `activating` for longer than your expected run length (for example, more than 48 h on a nightly timer), investigate.

**If you need every scheduled fire to run**, switch the timer from `OnCalendar=<cron>` to `OnUnitInactiveSec=<interval>`. That fires N hours after the previous run's completion rather than on a fixed wall-clock schedule, so long runs do not cause drops. They just push the next run later. The trade-off is schedule drift: your 03:00 nightly becomes "24 h after the last one ended."

### Snapshots, Interruptions, and Pool Space

Every push works from a momentary datastore snapshot, so the uploaded data is consistent even while repositories keep writing. While the backup runs, that snapshot keeps referencing every block it shares with live repositories: deletions and [trims](/en/docs/repositories#reclaim-space-trim) free less pool space until the cycle finishes and the snapshot is deleted. The [storage health report](/en/docs/monitoring#storage-health) shows how much space backup snapshots are currently pinning.

Interruptions are safe. Stopping the service (or rebooting the machine) makes the backup abort its transfer and delete its snapshot before exiting; the next scheduled run picks up where it left off, because cells already stored are not uploaded again. If the process is killed too hard to clean up (power loss), the orphaned snapshot is detected and removed automatically by the storage maintainer within minutes.

### Define a Strategy

The default setup is a two-strategy split: a fast hourly hot stream that captures every repo, and a slower weekly cold stream that quiesces containers for app-consistent snapshots. Both write into the same chunk store, and shared blocks are stored once rather than per stream.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

`--destination <name>` names the destination inside the strategy; it is a label
you choose, and it describes the chunk store. `--include` lists the repositories
to back up, and repeating it adds more. Omit it and the strategy covers every
repository on the datastore. Names match the local-config repository name
(no `:tag`).

`--exclude` is refused for a chunk-store destination rather than quietly
dropped, because the underlying `backup snapshot` selects repositories by naming
them and has no exclude of its own. Honouring it would mean backing up
repositories you asked to leave out. Scope a strategy with `--include` instead,
so what a scheduled run covers is written down rather than inferred.

| Option | Description |
|--------|-------------|
| `<strategy>` (positional) | Strategy name (used for machine binding) |
| `--destination <name>` | Destination name inside the strategy. Defaults to the chunk store |
| `--storage <name>` | Opt in to the retired rclone destination kind. A schedule using it cannot be deployed |
| `--cron <expression>` | Cron expression (e.g. `"0 2 * * *"` for daily at 2 AM) |
| `--mode <hot\|cold>` | Backup mode |
| `--bwlimit <limit>` | Bandwidth limit for uploads (e.g. `10M`) |
| `--include <repos>` | Repositories this strategy covers (repeatable) |
| `--exclude <repos>` | Repositories to skip (repeatable). Refused on a chunk-store destination |
| `--folder <path>` | Subfolder inside an rclone bucket. Refused on a chunk-store destination |
| `--enable` / `--disable` | Enable or disable the strategy |

### View Strategies

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Remove a Strategy

```bash
rdc backup strategy remove weekly-cold
```

### Bind Strategies to a Machine

A strategy bound to no machine is never deployed. Bind one or more to a machine:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

Binding is recorded in your config as a list on the machine, which is what
`rdc backup schedule` reads to decide which units to deploy:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Binding is local-config only.** Defining a strategy and binding it to a machine does not touch the machine. Run `rdc backup schedule -m <machine>` (see [Deploy Schedule to Machine](#deploy-schedule-to-machine)) to deploy the systemd timers, and re-run it after any strategy or binding change.

## Choosing Hot vs Cold and Per-Repo Filtering

### Hot vs cold at a glance

| | Hot | Cold |
|---|-----|------|
| **Consistency** | Crash-consistent (image frozen while running) | Application-consistent (stop → freeze → start) |
| **Downtime** | None | Per-repo stop+start window (typically 5-120 s) |
| **Suitable frequency** | High (e.g. hourly) | Low (e.g. daily or weekly) |
| **Typical use** | Frequent safety net | Scheduled guaranteed-consistency backup |

**Hot** is the right default for high-frequency runs. Services keep running while the snapshot is taken, so there's no downtime for your apps. The snapshot is crash-consistent: equivalent to what you'd get after an unclean shutdown. For most modern databases and message queues, that's fine.

**Cold** is appropriate when you need a guaranteed application-consistent snapshot and can accept a brief per-repo restart. Services are stopped before the snapshot and restarted before the upload begins, so a slow or failed upload never prolongs the downtime window. See [Cold Backup Semantics](#cold-backup-semantics) for the full guarantee model.

Both modes write into the same chunk store, and the mode is about how the
repository is treated while the image is frozen, not about where the data lands.
A repository covered by both an hourly hot schedule and a weekly cold one stores
the cells they share once rather than twice.

### Scoping repos per strategy

A strategy with no `--include` covers every repository on the datastore.
Repeating `--include` narrows it to the repositories you name, matched on the
local-config repository name (no `:tag`).

```bash
# Hot strategy: back up everything hourly
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Cold strategy: weekly, and only the repositories that need quiescing
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### When to keep a repo out of the frequent hot strategy

Name the repositories you want in the high-frequency run, rather than letting it
take everything, when:

- A repo is large and **fully regenerable** from source data already on the volume, so every hourly backup spends bandwidth without adding recovery value.
- The backup run would overrun its own schedule interval at your available upload speed.

**Example.** An `analytics-demo` repository holds roughly 114 GB of derived Postgres tables that can be rebuilt from raw CSV dumps stored inside the same volume. At a 6 MB/s upload limit, a first snapshot of that repo takes over 5 hours. Running that hourly means each run is still in progress when the next one fires, so every subsequent fire is silently dropped (see [Long-Running Backups and Overlapping Schedules](#long-running-backups-and-overlapping-schedules)). Listing the other repositories in `hourly-hot` and leaving `analytics-demo` to `weekly-cold` means it is backed up once per week instead of never.

> **If the data is purely regenerable**, consider whether you need to back it up at all. An alternative is to back up only the raw source inputs (the CSV dumps, in this example) and skip the derived copy entirely. A weekly cold backup of the source inputs is much smaller and fully sufficient for recovery.

A repo that both strategies cover gets hourly crash-consistent snapshots and a weekly application-consistent one. `rdc backup manifests <repo>` shows them together, and the cells they share are stored once.

## Backup Operations

### Deploy Schedule to Machine

Push the bound strategies to a machine as systemd timers:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

The deploy is a state reconciler. It reads the current unit files and systemd state on the machine, compares against what the config would produce (SHA-256 per file), and only touches units whose content actually changed. Re-running with no config changes is a no-op: no writes, no `daemon-reload`, no timer churn.

`--dry-run` prints the plan for each strategy (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) without touching the machine. Combine with `--debug` to also print the generated unit bodies, with credentials redacted. A chunk-store unit carries none in the first place: the machine authenticates with its own signed repository licence and the server hands back a short-lived grant, so nothing sensitive is written to the unit file.

If a backup is currently running for a strategy you are about to update or remove, the deploy fails fast with a hint to cancel it or pass `--force`. With `--force`, the running invocation keeps its in-memory unit and the new configuration applies on the next timer tick, so the running backup is never killed.

`--reset-failed` is opt-in. When passed, it clears systemd's failed state on touched services after a successful deploy. Off by default so prior failure signals stay visible to alerting.

### Run a Backup Now

Trigger a backup immediately without waiting for the timer. Works even if no timers have been deployed, using `systemd-run` for ad-hoc execution:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### View Backup Status

Show the current status of backup timers and recent job results:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Cancel a Running Backup

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Repository Migration

Move a repository from one machine to another:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `<ref>` (positional) | Repository ref to migrate; its `@machine` names the source |
| `--to <place>` | Destination machine or cluster |
| `--provision <provider>` | Auto-provision the target machine through this cloud provider (e.g. `hetzner`, `linode`) |
| `--checkpoint` | Create a CRIU checkpoint before migrating, so process memory moves too |
| `--delta-base <guid>` | Immutable base GUID for the cutover delta. Defaults to the first-phase base |
| `--strategy <strategy>` | Block-delta strategy for the cutover: `auto`, `physical`, or `shared` |
| `--skip-dns` | Skip updating DNS records after migration |
| `--keep-source` | Keep the source images after a successful move |
| `--bwlimit <limit>` | Bandwidth limit for the transfer (e.g. `50M`) |

Migration transfers the encrypted repository data via rsync in two phases: a bulk
transfer while the repository keeps running, then a brief stop for the delta.
Migration **moves** the repository, so the source images are deleted once the move
succeeds. Pass `--keep-source` to retain them. This is the difference between
`repo migrate` and `repo push`: push leaves the source running and untouched.

## Reading an Archive Written Before the Retirement

`rdc storage` is what is left of the rclone arm, and it is read-only. It cannot
be a backup destination any more, but it can still get at an archive that was
written to one.

```bash
# Register a remote you already have configured for rclone.
rdc storage import rclone.conf
rdc storage list

# Look at what is in it. This runs the rclone on your PATH.
rdc storage browse my-storage
```

`import` reads an rclone config file and records the remotes in your config;
supported types are S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob
and Swift.

**`browse` requires `rclone` on your PATH.** It runs the rclone installed on the
machine you are typing on; there is no bundled copy any more. Without one it
tells you so and does nothing else.

Pushing to, pulling from, listing and restoring a storage backend are retired;
each refuses and names the command that replaces it.

## Best Practices

- Schedule daily cold snapshots for app-consistent copies of critical data
- Use hot snapshots for high-frequency runs where zero downtime is required
- Test restores periodically. `rdc backup restore --as <new-name>` overwrites nothing, so a drill is safe on a live machine
- Set a retention policy rather than pruning by hand, so the window you keep is written down
- Keep a machine-to-machine copy as well as snapshots if you want a copy on hardware you control
- Keep credentials secure; backups are encrypted but the LUKS credential is required to restore
