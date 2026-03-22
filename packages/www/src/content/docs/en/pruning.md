---
title: "Pruning"
description: "Remove orphaned backups, stale snapshots, and unused repo images to reclaim disk space."
category: "Guides"
order: 12
language: en
---

# Pruning

Pruning removes resources that are no longer referenced by any configuration file. There are two prune commands targeting different resource types:

- **`rdc storage prune`** -- deletes orphaned backup files from cloud/external storage
- **`rdc machine prune`** -- cleans up datastore artifacts and (optionally) orphaned repo images on a machine

## Storage Prune

Scans a storage provider and deletes backups whose GUIDs no longer appear in any config file.

```bash
# Dry-run (default) — shows what would be deleted
rdc storage prune my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune my-s3 -m server-1 --grace-days 14
```

### What it checks

1. Lists all backup GUIDs in the named storage.
2. Scans every config file on disk (`~/.config/rediacc/*.json`).
3. A backup is **orphaned** if its GUID is not referenced by any config's repositories section.
4. Recently archived repos within the grace period are **protected** even if removed from the active config.

## Machine Prune

Cleans up on-machine resources in two phases.

### Phase 1: Datastore cleanup (always runs)

Removes empty mount directories, stale lock files, and stale BTRFS snapshots.

```bash
# Dry-run
rdc machine prune server-1 --dry-run

# Execute cleanup
rdc machine prune server-1
```

### Phase 2: Orphaned repository images (opt-in)

With `--orphaned-repos`, the CLI also identifies LUKS repo images on the machine that do not appear in any config file and deletes them.

```bash
# Dry-run (default behavior when is set)
rdc machine prune server-1

# Actually delete orphaned repos
rdc machine prune server-1

# Custom grace period
rdc machine prune server-1 --grace-days 30
```

## Safety Model

Pruning is designed to be safe by default across multi-config setups.

### Multi-config awareness

Both prune commands scan **all** config files in `~/.config/rediacc/`, not just the active one. A repo referenced by `production.json` will not be deleted even if it is absent from `staging.json`. This prevents accidental deletion when configs are scoped to different environments.

### Grace period

When a repository is removed from a config, it may be archived with a timestamp. The prune commands respect a grace period (default 7 days) during which recently archived repos are protected from deletion. This gives you time to restore a repo if it was removed accidentally.

### Dry-run by default

`storage prune` and `machine prune` default to dry-run mode. They display what would be removed without making changes. Pass `--no-dry-run` or `--force` to execute the actual deletion.

## Configuration

### `pruneGraceDays`

Set a custom default grace period in your config file so you don't need to pass `--grace-days` every time:

```bash
# Set grace period to 14 days in the active config
rdc config set pruneGraceDays 14
```

The `--grace-days` CLI flag overrides this value when provided.

### Precedence

1. `--grace-days <N>` flag (highest priority)
2. `pruneGraceDays` in config file
3. Built-in default: 7 days

## Best Practices

- **Run dry-run first.** Always preview before executing a destructive prune, especially on production storage.
- **Keep multiple configs current.** Prune checks all configs in the config directory. If a config file is stale or deleted, its repos lose protection. Keep config files accurate.
- **Use generous grace periods for production.** The default 7-day grace period suits most workflows. For production environments with infrequent maintenance windows, consider 14 or 30 days.
- **Schedule storage prune after backup runs.** Pair `storage prune` with your backup schedule to keep storage costs under control without manual intervention.
- **Combine machine prune with deploy-backup.** After deploying backup schedules (`rdc machine deploy-backup`), add a periodic machine prune to clean up stale snapshots and orphaned datastore artifacts.
- **Audit before using `--force`.** The `--force` flag bypasses the grace period. Only use it when you are certain no other config references the repos in question.
