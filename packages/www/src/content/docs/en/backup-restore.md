---
title: "Backup & Restore"
description: "Back up encrypted repositories two ways: content-addressed chunk storage that uploads only changed cells, or a full push to any rclone-compatible storage. Restore on any machine and automate with named strategies and systemd timers."
category: "Guides"
order: 7
language: en
sourceHash: "c02ab3e78c40fa92"
---

# Backup & Restore

Rediacc backs up encrypted repositories to external storage and restores them on the same or a different machine. Backups are encrypted; your repository's LUKS credential is required to restore.

## Two backup paths

Rediacc has two independent backup paths, and this guide covers both. They use
different storage and different commands, so a repository backed up on one is not
backed up on the other.

**Chunk storage** (`rdc backup snapshot`) uploads the repository image in
fixed-size cells addressed by content. The first run uploads the full non-zero
inventory; every run after it uploads only the cells that changed, decided from
filesystem allocation metadata rather than by reading the whole image. Identical
cells are stored once across snapshots and across a fork family, and usage is
metered against your storage quota (`rdc backup usage`).

**Storage push is retired.** `rdc repo push --to <storage>` used to copy a whole
backup file to an rclone-compatible provider you registered yourself. The rclone
arm has been removed, and push, pull, list and restore now refuse a storage
destination and point you here. Machine-to-machine transfer is untouched: it
never went through rclone.

Restoring from chunk storage works: `rdc backup restore <repo> --at <snapshot-id>`
materializes a stored snapshot, and `--at` also accepts an RFC 3339 timestamp,
which is resolved against the snapshot inventory. Add `--as <name>` to restore
under a different name and `--up` to bring the repository up afterwards. Chunk
storage also gives you upload (`rdc backup snapshot`), verification
(`rdc backup verify`, and `--deep` to re-hash every cell rather than a sample),
the snapshot inventory (`rdc backup manifests`), and quota accounting
(`rdc backup usage`).

### Chunk-storage commands

```bash
# Upload a snapshot. First run seeds, later runs send only changed cells.
rdc backup snapshot my-app

# Plan without uploading: reports what would move.
rdc backup snapshot my-app --dry-run

# Distrust the local anchor and re-upload the full inventory.
# This re-uploads everything and re-charges quota; use it only when the
# anchor is known bad.
rdc backup snapshot my-app --reseed

# Check the stored inventory and your quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

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

## Configure Storage

Before pushing backups, register a storage provider. Rediacc supports any rclone-compatible storage: S3, B2, Google Drive, and many more.

### Import from rclone

If you already have an rclone remote configured:

```bash
rdc storage import rclone.conf
```

This imports storage configurations from an rclone config file into the current config. Supported types: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob, and Swift.

### View Storages

```bash
rdc storage list
```

## Push a Backup to Another Machine

Copy a repository to a second machine over SSH:

```bash
rdc repo push my-app --to-machine server-1
```

The encrypted image is copied with the SAME GUID, so this is a backup or a
migration rather than a fork. To get an independent copy, `rdc repo fork` first
and push the fork.

For point-in-time backup, use chunk storage instead: `rdc backup snapshot my-app`
uploads only the cells that changed, and `rdc backup restore my-app --at <snapshot>`
brings any of them back.

| Option | Description |
|--------|-------------|
| `--to-machine <machine>` | Target machine for machine-to-machine backup |
| `--dest <filename>` | Custom destination filename |
| `--checkpoint` | Create a CRIU checkpoint before pushing (for containers with `rediacc.checkpoint=true` label). Target auto-restores on `repo up` |
| `--force` | Override an existing backup |
| `--bwlimit <limit>` | Bandwidth limit for rsync transfer (e.g. `10M`, `500K`) |
| `--tag <tag>` | Tag the backup |
| `-w, --watch` | Watch the operation progress |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Pull a Backup from Another Machine

Bring a repository back from the machine that holds it:

```bash
rdc repo pull my-app --from-machine server-1
```

To restore from chunk storage instead, use
`rdc backup restore my-app --at <snapshot-id>`.

Pull refuses to overwrite a repository that is currently **mounted**. Unmount it first, pull, then bring it back up with `rdc repo up`. Directory-based repositories are the exception: they sync in place while mounted.

| Option | Description |
|--------|-------------|
| `--from-machine <machine>` | Source machine for machine-to-machine restore |
| `--force` | Override existing local backup |
| `--bwlimit <limit>` | Bandwidth limit for rsync transfer (e.g. `10M`, `500K`) |
| `-w, --watch` | Watch the operation progress |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## List Backups

List the snapshots in chunk storage:

```bash
rdc backup manifests my-app
```

To see backup artifacts sitting on a machine:

```bash
rdc backup list -m server-1
```

The output lists the snapshots the chunk store holds for that repository:

| Column | Meaning |
|---|---|
| `Mode` | `hot` or `cold`. Which scheduled-backup folder this entry lives in |
| `Name` | Repository name resolved from your local config (falls back to GUID for repos not in config) |
| `GUID` | The on-disk repository GUID |
| `Size` | Human-readable size of the backup file |
| `Modified` | UTC timestamp from the storage backend |

Listing a storage backend is retired along with the rclone arm; the command
refuses and names these two replacements.

### What hot and cold actually mean

`--mode hot` and `--mode cold` describe how the repository is treated while the
backup is taken, not where the data lands.

**Hot** snapshots a running repository. Containers keep serving, and the image is
captured mid-write, so the backup is crash-consistent: exactly what you would get
if the machine lost power at that instant. That is fine for anything that
recovers from its own journal, which is most databases.

**Cold** stops the containers first, flushes, verifies they are down, freezes the
image and only then restarts them. It costs a real outage, but the outage is the
constant-time freeze rather than the transfer, and the result is
application-consistent.

Both write into the same chunk store. Cells are addressed by content, so a repo
backed up by both an hourly hot schedule and a weekly cold one stores the shared
blocks once rather than twice, and a fork family shares them too. Usage is
metered against your quota with `rdc backup usage`.

## Sync One Repository at a Time

Push and pull act on a single repository, addressed by ref (`name`, `name:tag`, or `name@machine`). There is no "all repositories at once" form: run the command once per repository.

### Push to Another Machine

```bash
rdc repo push shop@server-1 --to-machine server-2
```

### Pull from Another Machine

```bash
rdc repo pull shop@server-1 --from-machine server-2
```

| Option | Description |
|--------|-------------|
| `--to-machine <machine>` | Destination machine for machine-to-machine push |
| `--from-machine <machine>` | Source machine for machine-to-machine pull |
| `--force` | Overwrite an existing backup or repository |
| `--checkpoint` | Create a CRIU checkpoint before pushing (push only) |
| `--up` | Mount and deploy the repository after pulling (pull only) |
| `--bwlimit <limit>` | Bandwidth limit for the rsync transfer (e.g. `10M`) |
| `--delta-base <guid>` | Transfer only changed blocks against an immutable base GUID |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Scheduled Backups

Rediacc uses named backup strategies. Each strategy defines a schedule, backup mode, optional bandwidth limit, and file filters. You bind strategy names to machines to control which backups run where.

### Backup Modes

| Mode | Behavior | Downtime |
|------|----------|----------|
| `hot` | BTRFS snapshot taken while services are running (crash-consistent) | None |
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

The snapshot step (`btrfs subvolume snapshot -r`) is O(1) regardless of repo size: 0.1-1 s. A repo is not kept down for other repos' snapshots. The uploader then runs against a read-only snapshot while every repo is already back up.

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

If you run a latency-sensitive repo (public web app, mail), its downtime is bounded by its own stop+start (typically 30-90 s), not by the whole run length. Repos are scheduled into concurrency slots in the order they were discovered; there is no priority queue. Split heavy repos into their own `--exclude`-scoped strategies if you need finer-grained scheduling.

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

This default is deliberate. Running two cold backups in parallel against the same datastore would contend on the BTRFS snapshot path, the rclone remote, and the per-repo sidecars at `/var/run/rediacc/cold-backup-<guid>.status.json`. Waiting behind a running instance beats thrashing the same data from two directions.

**Monitoring implication.** A hung backup (for instance, rclone wedged on a network blackhole) silently drops every subsequent timer fire. The scheduler emits no alarm. Watch `systemctl show <unit> -p ActiveEnterTimestamp`: if the service has been `activating` for longer than your expected run length (for example, more than 48 h on a nightly timer), investigate.

**If you need every scheduled fire to run**, switch the timer from `OnCalendar=<cron>` to `OnUnitInactiveSec=<interval>`. That fires N hours after the previous run's completion rather than on a fixed wall-clock schedule, so long runs do not cause drops. They just push the next run later. The trade-off is schedule drift: your 03:00 nightly becomes "24 h after the last one ended."

### Snapshots, Interruptions, and Pool Space

Every push works from a momentary datastore snapshot, so the uploaded data is consistent even while repositories keep writing. While the backup runs, that snapshot keeps referencing every block it shares with live repositories: deletions and [trims](/en/docs/repositories#reclaim-space-trim) free less pool space until the cycle finishes and the snapshot is deleted. The [storage health report](/en/docs/monitoring#storage-health) shows how much space backup snapshots are currently pinning.

Interruptions are safe. Stopping the service (or rebooting the machine) makes the backup abort its transfer and delete its snapshot before exiting; the next scheduled run picks up where it left off, since unchanged files are skipped by checksum. If the process is killed too hard to clean up (power loss), the orphaned snapshot is detected and removed automatically by the storage maintainer within minutes.

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
  --exclude very-large-repo \
  --enable
```

The `--exclude` filter on the cold strategy is the recommended escape hatch for very-large repos that don't fit in your weekly maintenance window. The hourly hot strategy still covers them; cold simply skips. Repository names in `--exclude` match the local-config repo name (no `:tag`).

| Option | Description |
|--------|-------------|
| `<strategy>` (positional) | Strategy name (used for machine binding) |
| `--destination <storage>` | Storage provider to upload to |
| `--cron <expression>` | Cron expression (e.g. `"0 2 * * *"` for daily at 2 AM) |
| `--mode <hot\|cold>` | Backup mode |
| `--bwlimit <limit>` | Bandwidth limit for uploads (e.g. `10M`) |
| `--include <pattern>` | Include filter (repeatable) |
| `--exclude <pattern>` | Exclude filter (repeatable) |
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

In your config, bind one or more strategy names to a machine:

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
| **Consistency** | Crash-consistent (BTRFS snapshot while running) | Application-consistent (stop → snapshot → start) |
| **Downtime** | None | Per-repo stop+start window (typically 5-120 s) |
| **Suitable frequency** | High (e.g. hourly) | Low (e.g. daily or weekly) |
| **Typical use** | Frequent safety net | Scheduled guaranteed-consistency backup |

**Hot** is the right default for high-frequency runs. Services keep running while the snapshot is taken, so there's no downtime for your apps. The snapshot is crash-consistent: equivalent to what you'd get after an unclean shutdown. For most modern databases and message queues, that's fine.

**Cold** is appropriate when you need a guaranteed application-consistent snapshot and can accept a brief per-repo restart. Services are stopped before the snapshot and restarted before the upload begins, so a slow or failed upload never prolongs the downtime window. See [Cold Backup Semantics](#cold-backup-semantics) for the full guarantee model.

### Filtering repos per strategy

Each strategy can carry `--include` and `--exclude` filters. Repository names that match an `--exclude` pattern are skipped for that strategy; `--include` restricts the run to only those names. Filters match the local-config repository name (no `:tag`).

```bash
# Hot strategy: back up everything hourly
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Cold strategy: back up everything weekly, excluding the large derived dataset
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### When to exclude a repo from the frequent hot strategy

Exclude a repository from the high-frequency run when:

- The repo is large and **fully regenerable** from source data already on the volume, so every hourly backup wastes significant bandwidth without adding meaningful recovery value.
- The backup run would overrun its own schedule interval at your available upload speed.

**Example.** A `analytics-demo` repository contains roughly 114 GB of derived Postgres tables that can be fully rebuilt from raw CSV dump files already stored inside the same volume. At a 6 MB/s upload limit, a single hot backup of that repo takes over 5 hours. Running that hourly means each run is still in progress when the next one fires, which causes every subsequent run to be silently dropped (see [Long-Running Backups and Overlapping Schedules](#long-running-backups-and-overlapping-schedules)). Excluding it from `hourly-hot` and keeping it in `weekly-cold` means it is backed up once per week instead of never.

> **If the data is purely regenerable**, consider whether you need to back it up at all. An alternative is to back up only the raw source inputs (the CSV dumps, in this example) and skip the derived copy entirely. A weekly cold backup of the source inputs is much smaller and fully sufficient for recovery.

A repo that neither strategy excludes is captured by both, so it has hourly crash-consistent snapshots and a weekly application-consistent one. `rdc backup manifests <repo>` shows them together, and the blocks they share are stored once.

## Backup Operations

### Deploy Schedule to Machine

Push the bound strategies to a machine as systemd timers:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

The deploy is a state reconciler. It reads the current unit files and systemd state on the machine, compares against what the config would produce (SHA-256 per file), and only touches units whose content actually changed. Re-running with no config changes is a no-op: no writes, no `daemon-reload`, no timer churn.

`--dry-run` prints the plan for each strategy (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) without touching the machine. Combine with `--debug` to also print the generated unit bodies; rclone tokens are redacted.

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
| `--provision` | Provision the repository on the destination before transferring |
| `--checkpoint` | Create a CRIU checkpoint before migrating |
| `--skip-dns` | Skip updating DNS records after migration |
| `--bwlimit <limit>` | Bandwidth limit for the transfer (e.g. `50M`) |

Migration transfers the encrypted repository data via rsync. The source repository remains intact until you explicitly remove it.

## Browse Storage

`rdc storage browse` and `rdc storage import` are the exception to the retirement:
they spawn your own rclone from PATH rather than an embedded copy, and they remain
the way to read an archive written before the change.

```bash
rdc storage browse my-storage
```

Browsing is read-only. Pushing to, pulling from and listing a storage backend are
retired; each refuses and names the chunk-store command that replaces it.

## Best Practices

- Schedule daily cold backups for app-consistent snapshots of critical data
- Use hot backups for high-frequency snapshots where zero downtime is required
- Test restores periodically to verify backup integrity
- Use multiple storage providers for critical data (e.g. S3 + B2)
- Keep credentials secure; backups are encrypted but the LUKS credential is required to restore
