---
title: "Pruning"
description: "Remove orphaned backups, stale snapshots, repo images, and local-config leftovers to reclaim disk space and keep state coherent."
category: "Guides"
order: 12
language: en
---

# Pruning

Pruning sweeps state that no longer corresponds to a live resource. Three commands cover three different scopes:

| Command | What it cleans | Where the source of truth lives |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Orphaned backups in cloud storage | Local CLI config (cross-checked against the executor machine for mount safety) |
| `rdc machine prune --name <machine>` | On-machine datastore artifacts (always); orphaned or unknown repo images (opt-in) | Local CLI config + the machine's `.interim/state` mirror |
| `rdc config prune` | Local-config leftovers (cert cache, expired archives, dangling cross-references) | Local CLI config alone |

The three are independent. You can run any one without the others. They share a common safety model described under [Safety](#safety-model) below.

## Mount-safety preflight

`storage prune` and `machine prune --prune-unknown` both run a **mount-safety preflight** before deleting anything: they query the executor machine for currently-mounted or running repositories, intersect with the deletion candidates, and **refuse to delete a candidate that's still live on the machine**. Deleting the off-machine backup of a mounted repo, or deleting a live repo image, is a real data-loss footgun. The preflight makes it impossible to do by accident.

To override (rare; only when you genuinely know the live state is wrong), pass `--force-delete-mounted`. This is a separate flag from `--force` (which controls the archive grace period) so the two escape hatches stay distinct.

## Storage Prune

Scans a storage provider and deletes backups whose GUIDs no longer appear in any local config file.

```bash
# Preview only — show what would be deleted
rdc storage prune --name my-s3 -m server-1 --dry-run

# Actually delete orphaned backups (default behavior)
rdc storage prune --name my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Override the mount-safety check (use with care)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` is required because the rclone calls run on the executor machine, not on your laptop. Clients are not expected to have rclone installed locally. The storage credentials still come from your local config; the machine is just the rclone runner.

### What it checks

1. Lists all backup GUIDs in the named storage (across both `hot/` and `cold/` subdirectories. See [Backup & Restore](/en/docs/backup-restore#scheduled-backups)).
2. Scans every config file on disk (`~/.config/rediacc/*.json`).
3. A backup is **orphaned** if its GUID is not referenced by any config's repositories section.
4. Recently archived repos within the grace period are **protected** even if removed from the active config.
5. Mount-safety preflight: GUIDs currently mounted on `--machine` are skipped and reported, never deleted.

### Performance

Deletes are batched per storage subpath: one rclone call per `hot/` or `cold/` directory regardless of how many GUIDs are being removed. A backlog of 11 orphans collapses from ~50 s of SSH overhead down to a single round-trip per subpath.

## Machine Prune

Cleans up on-machine resources in three phases. Phase 1 always runs; phases 2 and 3 are opt-in and can be combined.

### Phase 1: Datastore cleanup (always runs)

Removes everything left behind when a repo is deleted or a naming convention is retired. Each category is scanned independently. Running prune repeatedly is safe: it's a single idempotent pass, so orphans the last run missed get caught by the next.

| Category | What it removes |
|---------|-----------------|
| Empty mount directories | `mounts/<guid>/` dirs with no backing repository image |
| Orphan immovable directories | `immovable/<guid>/` dirs with no backing repository image |
| Stale lock files | `repositories/.lock-<guid>` for deleted repos |
| Stale backup snapshots | `.snapshot-*` and `.backup-*` left behind by killed backup runs |
| Orphan VS Code sandbox directories | `.interim/sandbox/<name>` for repos no longer active on the machine |
| Orphan iptables chains | `REDIACC_WILDCARD_<N>` and `DOCKER_ISOLATED_NET_<N>` chains for deleted networks |
| Orphan authorized_keys entries | `sandbox-gateway <repo> --guid <uuid>` lines whose `--guid` no longer matches an active mount dir |

The authorized_keys scan looks at `/home/*/.ssh/authorized_keys` and `/root/.ssh/authorized_keys`. An entry is kept only if its `--guid` tag maps to a live mount dir GUID, so repos currently deployed on the machine are always preserved regardless of whether their name happens to appear anywhere on disk. Legacy entries written before renet started adding the `--guid` tag cannot be validated and are always reported as orphans.

```bash
# Dry-run, shows what would be removed (no changes applied)
rdc machine prune --name server-1 --dry-run

# Execute cleanup
rdc machine prune --name server-1
```

> **Cascading cleanup.** Some categories depend on earlier ones. For example, deleting empty mount directories may expose additional sandbox orphans whose backing mount just went away. Running `rdc machine prune` a second time catches the cascade and finishes the cleanup. The final dry-run ends with `No orphaned resources found. Datastore is clean.` when nothing is left to do.

### Phase 2: `--orphaned-repos` (coarse)

With `--orphaned-repos`, the CLI also deletes repository images on the machine that do not appear in **any** local config file.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

This is **coarse**. It deletes everything not in your local config, including legitimate forks managed by other tools or another operator's CLI checkout. If the renet `.interim/state` mirror correctly identifies a repo as a fork but the local config has never seen it, this phase still removes it. Prefer phase 3 (`--prune-unknown`) when you want to be conservative.

### Phase 3: `--prune-unknown` (surgical)

With `--prune-unknown`, the CLI deletes only repos that **both** signals fail to classify: not in any local config **and** no fork-marked entry in the machine's `.interim/state` mirror (see [Repositories. `Type` column](/en/docs/repositories#type-column-and-the-state-mirror)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

In practice `--prune-unknown` is what you want for routine cleanup; `--orphaned-repos` is only correct when you're certain your local config is the complete and authoritative inventory of every repo on the machine. Pre-mirror legacy orphans and repos whose config entry was deleted by mistake both fall into the "unknown" bucket. They're genuinely uncertain, and the surgical flag asks the operator to acknowledge that explicitly.

The mount-safety preflight runs on this phase too: a repo currently mounted on `--machine` is reported and skipped unless `--force-delete-mounted` is passed.

```bash
# Combined: full machine cleanup with the surgical fork-aware path
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

Sweeps stale leftovers **inside the local config file** at `~/.config/rediacc/<config>.json`. Pure-local. No SSH, no renet calls. Three buckets are cleaned:

1. **ACME cert-cache entries** whose anchor (GUID, repository name, or machine name) is no longer in the active config. The cert wildcards can never route anywhere, so they're dead weight.
2. **Expired archived repositories** in `resources.deletedRepositories[]`. Entries whose `deletedAt` is older than `defaults.pruneGraceDays` (default 7 days). In-grace entries are reported (with days remaining) and kept.
3. **Dangling cross-references** between config buckets:
   - `resources.machines.<m>.backupStrategies[]` entries naming a strategy that no longer exists.
   - `resources.backupStrategies.<s>.exclude[]` and `include[]` entries naming a repo that no longer exists.
   - Storage destinations whose target storage is missing. Flagged as a warning, not auto-removed (auto-removal would change strategy semantics).

```bash
# Preview only
rdc config prune --dry-run

# Apply (default behavior)
rdc config prune

# Restrict to one bucket
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Drop ALL archived repositories regardless of grace
rdc config prune --purge-archived

# Override the archive grace window for this invocation
rdc config prune --grace-days 30
```

### What it does NOT touch

- Active resources (machines, storages, repositories, backup strategies, cloud providers).
- Credentials, the account block, the encryption block, defaults.
- Storage `vaultContent` (including expired OneDrive `access_token`. The refresh_token still mints new ones; pruning would force re-auth).
- `knownHosts` entries (auto-refresh path is `rdc config machine scan-keys`).
- The compressed cert blob array (`infra.acmeCertCache.<base>.data[]`) is rebuilt from the cleaned cert list automatically; you don't lose any chain that still covers a kept name.

### Worked example

Output from a real run on a machine with four orphan-GUID wildcards and two stale machine-name wildcards:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Cert names whose anchor is a live machine, repo, or GUID are left alone, as are any single-label `<service>.<base>` or root `*.<base>` wildcards.

## Migration: state-mirror backfill

The `.interim/state/<guid>/.rediacc.json` mirror that powers `--prune-unknown` and the `Type` column in `rdc repo list -m` is written:

- **At fork time** (`rdc repo fork`). Immediately, even before the fork is ever mounted.
- **On every state save** (`rdc repo mount` and any operation that updates repo state). For repos that were created before the mirror code shipped.

Repositories that were created **before the mirror existed and have not been re-mounted since the upgrade** have no mirror file. They show as `unknown` in `rdc repo list -m` even though some are legitimately forks. To fix this for legacy orphans, run the one-shot backfill on the machine:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

The backfill copies live in-volume state to the mirror for currently-mounted repos and writes a synthetic fork-marked mirror for any GUIDs you list under `--mark-as-fork`. After the backfill, scheduled backups stop uploading the listed forks (the upload pipeline checks the mirror for `is_fork: true`).

## Safety Model

All three commands default to safe across multi-config setups.

### Multi-config awareness

`storage prune` and `machine prune --orphaned-repos` scan **all** config files in `~/.config/rediacc/`, not just the active one. A repo referenced by `production.json` will not be deleted even if it is absent from `staging.json`. This prevents accidental deletion when configs are scoped to different environments.

### Grace period

When a repository is removed from a config with `--archive-config`, its credential entry is moved to `resources.deletedRepositories[]` with a `deletedAt` timestamp. The prune commands respect a grace period (default 7 days) during which recently archived repos are protected from deletion. This gives you time to restore a repo (`rdc config repository restore-archived --name <guid>`) if it was removed accidentally. Once the grace expires, `storage prune`, `machine prune`, and `config prune` all auto-purge the entry.

### Mount-safety preflight

Covered above. `storage prune` and `machine prune --prune-unknown` refuse to delete repos that are currently mounted or running on the executor machine. Override only with `--force-delete-mounted`.

### Apply by default; `--dry-run` to preview

All three prune commands default to **applying** changes. Pass `--dry-run` to preview without writing. This matches the verb: "prune" is destructive on its own, and a dry-run flag is the explicit opt-out.

## Configuration

### `pruneGraceDays`

Set a custom default grace period in your config file so you don't need to pass `--grace-days` every time:

```bash
# Set grace period to 14 days in the active config
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

The `--grace-days` CLI flag overrides this value when provided.

### Precedence

1. `--grace-days <N>` flag (highest priority)
2. `pruneGraceDays` in config file
3. Built-in default: 7 days

## Best Practices

- **Run dry-run first on production.** Always preview before executing a destructive prune, especially on production storage.
- **Keep multiple configs current.** Storage and machine prune check all configs in the config directory. If a config file is stale or deleted, its repos lose protection. Keep config files accurate.
- **Prefer `--prune-unknown` over `--orphaned-repos`.** The surgical flag respects the renet mirror; the coarse flag will happily delete forks that other tools created.
- **Use generous grace periods for production.** The default 7-day grace period suits most workflows. For production environments with infrequent maintenance windows, consider 14 or 30 days.
- **Schedule storage prune after backup runs.** Pair `storage prune` with your backup schedule to keep storage costs under control without manual intervention.
- **Combine machine prune with the backup schedule.** After deploying backup schedules (`rdc machine backup schedule`), add a periodic machine prune to clean up stale snapshots and orphaned datastore artifacts.
- **Run `config prune` periodically.** Local-config bloat (especially cert cache) accumulates silently; a quarterly `config prune --dry-run` is enough to catch it.
- **Audit before using `--force` or `--force-delete-mounted`.** Both flags bypass safety checks. Use `--force` only when you're certain no other config references the repos in question; use `--force-delete-mounted` only when you're certain the live state on the machine is wrong.
