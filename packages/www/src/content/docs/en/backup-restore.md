---
title: "Backup & Restore"
description: "Back up encrypted repositories to external storage, restore from backups, and schedule automated backups."
category: "Guides"
order: 7
language: en
---

# Backup & Restore

Rediacc can back up encrypted repositories to external storage providers and restore them on the same or different machines. Backups are encrypted — the repository's LUKS credential is required to restore.

## Configure Storage

Before pushing backups, register a storage provider. Rediacc supports any rclone-compatible storage: S3, B2, Google Drive, and many more.

### Import from rclone

If you already have an rclone remote configured:

```bash
rdc config import-storage rclone.conf
```

This imports storage configurations from an rclone config file into the current config. Supported types: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob, and Swift.

### View Storages

```bash
rdc config storages
```

## Push a Backup

Push a repository backup to external storage:

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| Option | Description |
|--------|-------------|
| `--to <storage>` | Target storage location |
| `--to-machine <machine>` | Target machine for machine-to-machine backup |
| `--dest <filename>` | Custom destination filename |
| `--checkpoint` | Create a checkpoint before pushing |
| `--force` | Override an existing backup |
| `--tag <tag>` | Tag the backup |
| `-w, --watch` | Watch the operation progress |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Pull / Restore a Backup

Pull a repository backup from external storage:

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| Option | Description |
|--------|-------------|
| `--from <storage>` | Source storage location |
| `--from-machine <machine>` | Source machine for machine-to-machine restore |
| `--force` | Override existing local backup |
| `-w, --watch` | Watch the operation progress |
| `--debug` | Enable verbose output |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## List Backups

View available backups in a storage location:

```bash
rdc backup list --from my-storage -m server-1
```

## Bulk Sync

Push or pull all repositories at once:

### Push All to Storage

```bash
rdc backup sync --to my-storage -m server-1
```

### Pull All from Storage

```bash
rdc backup sync --from my-storage -m server-1
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

Automate backups with a cron schedule that runs as a systemd timer on the remote machine.

### Set Schedule

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| Option | Description |
|--------|-------------|
| `--destination <storage>` | Default backup destination |
| `--cron <expression>` | Cron expression (e.g., `"0 2 * * *"` for daily at 2 AM) |
| `--enable` | Enable the schedule |
| `--disable` | Disable the schedule |

### Push Schedule to Machine

Deploy the schedule configuration to a machine as a systemd timer:

```bash
rdc backup schedule push server-1
```

### View Schedule

```bash
rdc backup schedule show
```

## Browse Storage

Browse the contents of a storage location:

```bash
rdc storage browse my-storage -m server-1
```

## Best Practices

- **Schedule daily backups** to at least one storage provider
- **Test restores** periodically to verify backup integrity
- **Use multiple storage providers** for critical data (e.g., S3 + B2)
- **Keep credentials secure** — backups are encrypted but the LUKS credential is required to restore
