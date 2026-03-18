# rdc repo — Backup, Restore, Sync & Snapshots

For full command syntax and options, see [reference.md](reference.md).

Backup, restore, transfer, and sync repository images between machines or to/from external storage. All backup and sync operations are subcommands of `rdc repo`.

**Prerequisite**: Both source AND target machines must be registered, set up, and the CLI SSH key must be configured. See "Prerequisites for ops VMs" in [SKILL.md](SKILL.md) and [config.md](config.md).

## Backup commands

### Push to another machine
Copies the encrypted repo image directly to the target machine with the **same GUID**. This is a backup/migration, not a fork. After push, deploy on target with `rdc repo up <repo> -m <target> --mount`.

**Important**: `--mount` is required on first deploy after push — the volume needs to be opened (LUKS decryption). The repo's credential must be in the config. If pushing a fork, use `--grand <parent>` on `repo up` to inherit the parent's credential.

### Push to storage
Backs up to configured external storage (S3, local file, etc.).

### Pull from another machine

### Pull from storage

### List backups

### CRIU checkpoint label

Only containers with the `rediacc.checkpoint=true` label are checkpointed. Containers without it (databases, caches) start fresh and recover via their own mechanisms (WAL, LDF, AOF). CRIU capabilities (`CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN`) are only injected for labeled containers.

```yaml
services:
  db:
    image: postgres:16-alpine
    # No label — starts fresh, recovers via WAL

  app:
    image: node:20-alpine
    labels:
      - "rediacc.checkpoint=true"   # Opt-in to CRIU
    depends_on:
      db:
        condition: service_healthy
```

### Live migration with CRIU checkpoint

CRIU (Checkpoint/Restore In Userspace) captures running process memory state. The process resumes on the target exactly where it left off — in-memory variables, open connections, counters all preserved.

```bash
# On source: checkpoint labeled containers + push (captures process memory + disk state)
rdc repo push <repo> -m <source> --to-machine <target> --checkpoint

# On target: restore (auto-detects checkpoint data, restores process state)
rdc repo up <repo> -m <target> --mount
```

**What's preserved**: Process memory, open file descriptors, in-memory variables, timers. The app continues from the exact instruction where it was checkpointed.

**What to expect**: After restore, the app doesn't re-run up() lifecycle — checkpoint containers resume directly. Non-checkpoint containers (DBs) start fresh and recover from disk. Restore is dependency-aware (uses `depends_on` to start DBs first, wait for healthy, then CRIU restore apps).

### Same-machine fork with CRIU (instant clone with live state)

```bash
# Fork with checkpoint — captures process state, then CoW clones
rdc repo fork <parent> <tag> -m <machine> --checkpoint
rdc repo mount <parent>:<tag> -m <machine>
rdc repo up <parent>:<tag> -m <machine>
# Auto-detects checkpoint → DB starts fresh → app CRIU restores (counter continues)
```

### Cross-machine fork with CRIU

```bash
# Fork with checkpoint, then push to target
rdc repo fork <parent> <tag> -m <source> --checkpoint
rdc repo push <parent>:<tag> -m <source> --to-machine <target>
rdc repo up <parent>:<tag> -m <target> --mount --grand <parent>
```

### Save/restore cycle (stop and resume later)

```bash
rdc repo down <repo> -m <machine> --checkpoint    # Saves process state, then stops
rdc repo up <repo> -m <machine>                    # Auto-detects checkpoint, resumes
```

### CRIU troubleshooting

- **Docker experimental is auto-enabled**: Per-repo Docker daemons have `"experimental": true` in their generated daemon.json. System Docker is configured during `rdc config setup-machine`. You don't need to enable this manually.
- **CRIU must be installed on VMs**: `rdc config setup-machine` installs CRIU from system packages and writes `/etc/criu/runc.conf` with `tcp-established`. If checkpoint fails with "CRIU is not installed", re-run setup-machine.
- **Host networking is forced by renet**: `renet compose` overwrites all services to `network_mode: host` regardless of what the compose file says. This is required for CRIU compatibility.
- **CRIU security settings are auto-injected for labeled containers**: `renet compose` adds `cap_add: [CHECKPOINT_RESTORE, SYS_PTRACE, NET_ADMIN]`, `security_opt: [apparmor=unconfined]`, and `userns_mode: host` to containers with `rediacc.checkpoint=true`. Containers without the label run with a cleaner security posture. Docker's default seccomp profile is preserved (CRIU suspends it via `PTRACE_O_SUSPEND_SECCOMP`).
- **TCP connections break after cross-machine restore**: Apps with persistent connections (database pools, websockets) must handle both `ECONNRESET` (stale socket) and `ECONNREFUSED` (service not yet accepting connections). After restore, dependent services like databases may need a few seconds to become ready even though their containers show as "running". See the [heartbeat template](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) for a CRIU-safe reference implementation.
- **`restart: always` conflicts with CRIU**: Use `restart: on-failure` or omit it.
- CRIU captures kernel-specific state (cgroup paths, mount IDs, container IDs). Cross-machine restore works best with compatible Docker versions.
- **Checkpoint restore is auto-detected**: `repo up` automatically checks for checkpoint data and restores if found. Use `--skip-checkpoint` to force a fresh start instead.
- If checkpoint fails, the deploy still succeeds — it falls back to a fresh start (no process memory preservation).

### CRIU performance (tested)

| Metric | Value |
|--------|-------|
| Checkpoint | ~2s for 2 containers (hot backup, source keeps running) |
| Transfer (delta, no checkpoint) | ~1.8MB of 2.15GB (speedup 985x with small changes) |
| Transfer (delta, with checkpoint) | ~130MB of 2.15GB (speedup ~16x — CRIU image data is new each time) |
| Restore | ~7s including LUKS mount + Docker daemon start |
| Total migration | ~22s end-to-end |

**Note**: Checkpoint pushes always transfer more than non-checkpoint pushes because CRIU process memory dumps are new content each time. Non-checkpoint delta pushes only transfer changed disk blocks.

## Backup scheduling

### Configure backup strategy
Multiple destinations can be configured with different schedules:
```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

### Show backup strategy

### Deploy backup schedule to machine (systemd timer)

## Bulk sync (push/pull all repos)

### Push all repos to storage

### Pull all repos from storage

## File sync (rsync-based file transfer)

File transfer between local machine and remote repositories. See [sync.md](sync.md) for full details on file sync options and behavior.

## Fork vs Push — when to use which

| Goal | Command | Result |
|------|---------|--------|
| **Independent copy** on another machine | `repo fork` then `repo push` fork then `repo up --mount` | New GUID, new networkId, new IPs |
| **Migrate/backup** same repo to another machine | `repo push --to-machine` then `repo up --mount` | Same GUID, same identity |
| **Test copy** on same machine | `repo fork <parent> <tag>` then `repo up --mount` | New GUID, shares encryption cred |

### Cross-machine fork (independent copy)

The fork uses the name:tag model — `<parent>:<tag>` (e.g., `my-app:staging`). It's an independent repo with its own GUID and networkId. Both parent and fork can run simultaneously on different machines.

```bash
# 1. Fork locally (creates new identity — runs on source machine)
rdc repo fork <parent> <tag> -m <source-machine>

# 2. Push the fork to target
rdc repo push <parent>:<tag> -m <source-machine> --to-machine <target-machine>

# 3. Deploy on target (--mount + --grand to unlock with parent's credential)
rdc repo up <parent>:<tag> -m <target-machine> --mount --grand <parent>
```

**Note**: `--grand <parent>` tells the CLI to use the parent repo's LUKS credential to unlock the fork. This is required because forks inherit the parent's encryption key.

### Simple migration (same identity)
```bash
# 1. Push directly
rdc repo push <repo> -m <source-machine> --to-machine <target-machine>

# 2. Deploy on target
rdc repo up <repo> -m <target-machine> --mount
```

## Delta transfer for repo push

`repo push --to-machine` uses rsync delta transfer. When a previous backup already exists on the target:
- **First push**: Full transfer (entire LUKS image, e.g., 2.15GB).
- **Subsequent pushes**: Only changed blocks are sent. A 2.15GB repo with small changes transfers ~1.8MB (speedup 985x).
- Renet logs: `"Pre-seeded temp from existing backup (delta transfer enabled)"` confirms delta mode.
- The speedup ratio is shown in rsync output: `total size is 2.15G  speedup is 985.81`.

This makes incremental backups and frequent pushes very fast after the initial full transfer.

## Snapshots (BTRFS)

Local point-in-time snapshots on the same machine.

## Prune — cleanup orphaned resources

Two prune commands remove resources no longer referenced by any config file.

### Storage prune (orphaned backups in cloud/external storage)
Multi-config safe: scans all config files in `~/.config/rediacc/` before deciding a backup is orphaned. Recently archived repos within the grace period are protected.

### Machine prune (datastore + orphaned repo images)
Phase 1: clean stale mounts, locks, snapshots. Phase 2 (with `--orphaned-repos`): also delete repo images not in any config.

### Grace period configuration

Set a default grace period in config so `--grace-days` is not required each time:

```bash
rdc config set pruneGraceDays 14
```

Precedence: `--grace-days` flag > `pruneGraceDays` in config > 7-day default.
