---
title: "Backup & Restore"
description: "Back up encrypted repositories to external storage, restore from backups, and schedule automated backups."
category: "Guides"
order: 7
language: en
sourceHash: "4cc40d3db5384f5d"
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
| `cold` | Services stopped, snapshot taken, services restarted, snapshot uploaded (app-consistent) | Brief |

Use `hot` for services that tolerate crash-consistent snapshots. Use `cold` when you need guaranteed consistency and can accept a brief restart.

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

Or use the CLI:

```bash
rdc config machine set hostinger --backup-strategies hourly-hot,nightly-cold
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
