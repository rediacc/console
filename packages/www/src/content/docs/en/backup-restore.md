---
title: "Backup & Restore"
description: "Back up encrypted repositories to any rclone-compatible storage, restore on any machine, and automate with named backup strategies and systemd timers."
category: "Guides"
order: 7
language: en
sourceHash: "f5222efa9505ab5e"
---

# Backup & Restore

Rediacc backs up encrypted repositories to external storage and restores them on the same or a different machine. Backups are encrypted; your repository's LUKS credential is required to restore.

## Configure Storage

Before pushing backups, register a storage provider. Rediacc supports any rclone-compatible storage: S3, B2, Google Drive, and many more.

### Import from rclone

If you already have an rclone remote configured:

```bash
rdc config storage import --file rclone.conf
```

This imports storage configurations from an rclone config file into the current config. Supported types: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob, and Swift.

### View Storages

```bash
rdc config storage list
```

## Push a Backup

Push a repository backup to external storage:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

The backup lands in the storage's `hot/` folder when the repository is mounted at push time, and in `cold/` when it is unmounted. This is the same layout the scheduled backups use, so `rdc repo backup list` shows every backup in one table.

| Option | Description |
|--------|-------------|
| `--to <storage>` | Target storage location |
| `--to-machine <machine>` | Target machine for machine-to-machine backup |
| `--dest <filename>` | Custom destination filename |
| `--checkpoint` | Create a CRIU checkpoint before pushing (for containers with `rediacc.checkpoint=true` label). Target auto-restores on `repo up` |
| `--force` | Override an existing backup |
| `--bwlimit <limit>` | Bandwidth limit for rsync transfer (e.g. `10M`, `500K`) |
| `--tag <tag>` | Tag the backup |
| `-w, --watch` | Watch the operation progress |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Pull / Restore a Backup

Pull a repository backup from external storage:

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull always checks that the target repository is mounted before writing. If it is not mounted, the operation is aborted.

| Option | Description |
|--------|-------------|
| `--from <storage>` | Source storage location |
| `--from-machine <machine>` | Source machine for machine-to-machine restore |
| `--force` | Override existing local backup |
| `--bwlimit <limit>` | Bandwidth limit for rsync transfer (e.g. `10M`, `500K`) |
| `-w, --watch` | Watch the operation progress |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## List Backups

View available backups in a storage location:

```bash
rdc repo backup list --from my-storage -m server-1
```

The output is a unified table that merges both [scheduled-backup folders](#scheduled-backups) (`hot/` and `cold/`) so you see every backup in one view:

| Column | Meaning |
|---|---|
| `Mode` | `hot` or `cold`. Which scheduled-backup folder this entry lives in |
| `Name` | Repository name resolved from your local config (falls back to GUID for repos not in config) |
| `GUID` | The on-disk repository GUID |
| `Size` | Human-readable size of the backup file |
| `Modified` | UTC timestamp from the storage backend |

To drill into a single mode, pass `--path`:

```bash
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
```

### Storage layout

Scheduled backups land under per-mode subfolders inside the storage's configured folder, so the same storage cleanly hosts both the hourly and the weekly streams without mixing them:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

A repo can appear in both `hot/` and `cold/` (the hourly schedule snapshots it; the weekly schedule snapshots it again). The merged listing shows both rows so you can see which streams cover which repos.

## Bulk Sync

Push or pull all repositories at once:

### Push All to Storage

```bash
rdc repo push --to my-storage -m server-1
```

### Pull All from Storage

```bash
rdc repo pull --from my-storage -m server-1
```

| Option | Description |
|--------|-------------|
| `--to <storage>` | Target storage (push direction) |
| `--from <storage>` | Source storage (pull direction) |
| `--repo <name>` | Sync specific repositories (repeatable) |
| `--override` | Override existing backups |
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

- `rdc machine query --name <machine> --containers` shows running state. Compare against the expected set.
- `/var/run/rediacc/cold-backup-<guid>.status.json` on the machine. Inspect via `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` with a stale `startedAt` means the last backup didn't complete cleanly.
- Logs from the renet backup run (`journalctl -u renet-*` or the direct `rdc machine backup schedule` invocation) emit a final summary line of the form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. A non-empty `failed_repos` is the grep target.

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

The default setup is a two-strategy split: a fast hourly hot stream that captures every repo, and a slower weekly cold stream for app-consistent snapshots. Both strategies write to separate storage subfolders (`hot/` and `cold/`), so the streams never mix.

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

The `--exclude` filter on the cold strategy is the recommended escape hatch for very-large repos that don't fit in your weekly maintenance window. The hourly hot strategy still covers them; cold simply skips. Repository names in `--exclude` match the local-config repo name (no `:tag`).

| Option | Description |
|--------|-------------|
| `--name <name>` | Strategy name (used for machine binding) |
| `--destination <storage>` | Storage provider to upload to |
| `--cron <expression>` | Cron expression (e.g. `"0 2 * * *"` for daily at 2 AM) |
| `--mode <hot\|cold>` | Backup mode |
| `--bwlimit <limit>` | Bandwidth limit for uploads (e.g. `10M`) |
| `--include <pattern>` | Include filter (repeatable) |
| `--exclude <pattern>` | Exclude filter (repeatable) |
| `--enable` / `--disable` | Enable or disable the strategy |

### View Strategies

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### Remove a Strategy

```bash
rdc config backup-strategy remove --name weekly-cold
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

> **Binding is local-config only.** Defining a strategy and binding it to a machine does not touch the machine. Run `rdc machine backup schedule -m <machine>` (see [Deploy Schedule to Machine](#deploy-schedule-to-machine)) to deploy the systemd timers, and re-run it after any strategy or binding change.

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
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Cold strategy: back up everything weekly, excluding the large derived dataset
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
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

Repos that are not excluded from either strategy appear in both the `hot/` and `cold/` storage subfolders. The merged `rdc repo backup list` output shows both rows so you can verify which streams cover which repos.

## Backup Operations

### Deploy Schedule to Machine

Push the bound strategies to a machine as systemd timers:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

The deploy is a state reconciler. It reads the current unit files and systemd state on the machine, compares against what the config would produce (SHA-256 per file), and only touches units whose content actually changed. Re-running with no config changes is a no-op: no writes, no `daemon-reload`, no timer churn.

`--dry-run` prints the plan for each strategy (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) without touching the machine. Combine with `--debug` to also print the generated unit bodies; rclone tokens are redacted.

If a backup is currently running for a strategy you are about to update or remove, the deploy fails fast with a hint to cancel it or pass `--force`. With `--force`, the running invocation keeps its in-memory unit and the new configuration applies on the next timer tick, so the running backup is never killed.

`--reset-failed` is opt-in. When passed, it clears systemd's failed state on touched services after a successful deploy. Off by default so prior failure signals stay visible to alerting.

### Run a Backup Now

Trigger a backup immediately without waiting for the timer. Works even if no timers have been deployed, using `systemd-run` for ad-hoc execution:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### View Backup Status

Show the current status of backup timers and recent job results:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Cancel a Running Backup

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## Repository Migration

Move a repository from one machine to another:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `--name <repo>` | Repository to migrate |
| `--from <machine>` | Source machine |
| `--to <machine>` | Destination machine |
| `--provision` | Provision the repository on the destination before transferring |
| `--checkpoint` | Create a CRIU checkpoint before migrating |
| `--skip-dns` | Skip updating DNS records after migration |
| `--bwlimit <limit>` | Bandwidth limit for the transfer (e.g. `50M`) |

Migration transfers the encrypted repository data via rsync. The source repository remains intact until you explicitly remove it.

## Browse Storage

Browse the contents of a storage location:

```bash
rdc storage browse --name my-storage
```

## Best Practices

- Schedule daily cold backups for app-consistent snapshots of critical data
- Use hot backups for high-frequency snapshots where zero downtime is required
- Test restores periodically to verify backup integrity
- Use multiple storage providers for critical data (e.g. S3 + B2)
- Keep credentials secure; backups are encrypted but the LUKS credential is required to restore
