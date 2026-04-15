---
title: "Backup & Restore"
description: "Back up encrypted repositories to external storage, restore from backups, and schedule automated backups."
category: "Guides"
order: 7
language: en
sourceHash: "d5556f7b71c7c3df"
---

# Backup & Restore

Rediacc can back up encrypted repositories to external storage providers and restore them on the same or different machines. Backups are encrypted; the repository's LUKS credential is required to restore.

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

Push always checks that the target repository is mounted before writing. If it is not mounted, the operation is aborted.

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

Rediacc uses named backup strategies. Each strategy defines a schedule, backup mode, optional bandwidth limit, and file filters. Machines reference strategies by name to determine which backups run on them.

### Backup Modes

| Mode | Behavior | Downtime |
|------|----------|----------|
| `hot` | BTRFS snapshot taken while services are running (crash-consistent) | None |
| `cold` | Services stopped, snapshot taken, services restarted, snapshot uploaded (app-consistent) | Per-repo stop+start window, parallelised across repos. See "Estimating Cold Backup Downtime" below. |

Use `hot` for services that tolerate crash-consistent snapshots. Use `cold` when you need guaranteed consistency and can accept a brief restart.

### Cold Backup Semantics

A cold backup runs in three phases per included repo: **stop → snapshot → start**. Understanding where guarantees end helps operators notice partial failures early.

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

**How operators detect failures:**

- `rdc machine query --name <machine> --containers` shows running state. Compare against the expected set.
- `/var/run/rediacc/cold-backup-<guid>.status.json` on the machine. Inspect via `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` with a stale `startedAt` means the last backup didn't complete cleanly.
- Logs from the renet backup run (`journalctl -u renet-*` or the direct `rdc machine deploy-backup` invocation) emit a final summary line of the form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. A non-empty `failed_repos` is the grep target.

### Estimating Cold Backup Downtime

Each repo is down only for its own `down()` + `up()` window. On a warm host these are typically:

| Repo shape | Typical stop+start |
|------------|--------------------|
| Small (1-2 containers, no DB) | 5-15 s |
| Medium (web app + cache) | 20-45 s |
| Heavy (DB + queues + mail) | 60-120 s |

The snapshot step (`btrfs subvolume snapshot -r`) is O(1) regardless of repo size: 0.1-1 s. A repo is not kept down for other repos' snapshots. The uploader then runs against a read-only snapshot while every repo is already back up.

**Total wall-clock for the whole run** is governed by how many repos restart concurrently. Renet derives this from the host:

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

### Define a Strategy

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
  --name nightly-cold \
  --destination my-storage \
  --cron "0 2 * * *" \
  --mode cold \
  --include "*.db" \
  --exclude "tmp/**" \
  --enable
```

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
rdc config backup-strategy show --name nightly-cold
```

### Remove a Strategy

```bash
rdc config backup-strategy remove --name nightly-cold
```

### Bind Strategies to a Machine

In your config, bind one or more strategy names to a machine:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "nightly-cold"]
    }
  }
}
```

## Backup Operations

### Deploy Schedule to Machine

Push the bound strategies to a machine as systemd timers:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

`--dry-run` prints the generated systemd unit files without deploying them. rclone tokens are masked in dry-run output.

### Run a Backup Now

Trigger a backup immediately without waiting for the timer. Works even if no timers have been deployed, using `systemd-run` for ad-hoc execution:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy nightly-cold
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
rdc machine backup cancel -m server-1 --strategy nightly-cold
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
