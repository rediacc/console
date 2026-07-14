# rdc repo — Backup, Restore, Sync & Snapshots

For full command syntax and options, see [reference.md](reference.md).

Backup, restore, transfer, and sync repository images between machines or to/from external storage.

Two nouns are involved:
- `rdc repo push` / `rdc repo pull` / `rdc repo migrate` / `rdc repo sync`: move a repo's bytes.
- `rdc backup`: strategies, scheduling, and restore. `backup strategy {set,remove,list,show}`, `backup schedule`, `backup run`, `backup status`, `backup cancel`, `backup list`, `backup restore`.

**Prerequisite**: Both source AND target machines must be registered, set up, and the CLI SSH key must be configured. See "Prerequisites for ops VMs" in [SKILL.md](SKILL.md) and [config.md](config.md).

## Backup commands

### Push to another machine
`rdc repo push <ref> --to-machine <target>` copies the encrypted repo image directly to the target machine with the **same GUID**. This is a backup/migration, not a fork. The copy lands as a backup ARTIFACT, so it is booted on the target with `backup restore ... --up`; `repo push` itself has no `--up`.

**Important**: mounting is automatic. The retired `repo up --mount` flag is gone, and forks resolve the parent's credential on their own (no `--grand` flag on `repo up` any more).

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
# Checkpoint labeled containers + push (captures process memory + disk state).
# The checkpoint rides along with the artifact; `backup restore --up` boots from it.
rdc repo push <repo> --to-machine <target> --checkpoint
rdc backup restore <repo> --as <repo> -m <target> --up

# Or move the repo outright: two-phase rsync, brief cutover, placement follows.
rdc repo migrate <repo> --to <target> --checkpoint
```

**What's preserved**: Process memory, open file descriptors, in-memory variables, timers. The app continues from the exact instruction where it was checkpointed.

**What to expect**: After restore, the app doesn't re-run up() lifecycle — checkpoint containers resume directly. Non-checkpoint containers (DBs) start fresh and recover from disk. Restore is dependency-aware (uses `depends_on` to start DBs first, wait for healthy, then CRIU restore apps).

### Same-machine fork with CRIU (instant clone with live state)

```bash
# Fork with checkpoint: captures process state, then CoW clones.
# Forks mount automatically on first `repo up`; the old `repo mount` step is gone.
rdc repo fork <parent> --tag <tag> --checkpoint
rdc repo up <parent>:<tag>
# Auto-detects checkpoint → DB starts fresh → app CRIU restores (counter continues)
```

### Cross-machine fork with CRIU

```bash
# Fork with checkpoint, then push the fork to the target and deploy it there
rdc repo fork <parent> --tag <tag> --checkpoint
rdc repo push <parent>:<tag> --to-machine <target>
rdc backup restore <parent>:<tag> --as <parent> -m <target> --up
```

### Save/restore cycle (stop and resume later)

```bash
rdc repo down <repo> --checkpoint    # Saves process state, then stops
rdc repo up <repo>                   # Auto-detects checkpoint, resumes
```

### CRIU troubleshooting

- **Docker experimental is auto-enabled**: Per-repo Docker daemons have `"experimental": true` in their generated daemon.json. System Docker is configured during `rdc machine setup <name>`. You don't need to enable this manually.
- **CRIU must be installed on VMs**: `rdc machine setup <name>` installs CRIU from system packages and writes `/etc/criu/runc.conf` with `tcp-established`. If checkpoint fails with "CRIU is not installed", re-run `rdc machine setup <name>`.
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
The strategy name is a positional argument. Multiple destinations can be configured with
different schedules:
```bash
rdc backup strategy set daily --destination my-s3 --storage my-s3 --cron "0 2 * * *" --enable
rdc backup strategy set offsite --destination azure-backup --storage azure-backup --cron "0 6 * * *" --enable
```
`--storage <name>` is required the first time a destination is created (it names the rclone
credentials from `rdc storage add`).

### Show / list backup strategies
```bash
rdc backup strategy list
rdc backup strategy show daily
```

### Deploy backup schedule to machine (systemd timer)
```bash
rdc backup schedule -m <machine>
```

### Run, watch, and restore
```bash
rdc backup run daily -m <machine> -w      # run a strategy now and watch it
rdc backup status daily -m <machine>
rdc backup list <artifact-ref> -m <machine>
rdc backup restore <artifact-ref> --as <new-name> -m <machine> --up
```

## Bulk sync (push/pull all repos)

### Push all repos to storage

### Pull all repos from storage

## File sync (rsync-based file transfer)

File transfer between local machine and remote repositories. See [sync.md](sync.md) for full details on file sync options and behavior.

## Fork vs Push — when to use which

| Goal | Command | Result |
|------|---------|--------|
| **Independent copy** on another machine | `repo fork <ref> --tag <tag>`, `repo push <ref>:<tag> --to-machine <m>`, then `backup restore ... --up` | New GUID, new networkId, new IPs |
| **Migrate/backup** same repo to another machine | `repo push <ref> --to-machine <m>`, then `backup restore ... --up` | Same GUID, same identity |
| **Move** a repo to another machine | `repo migrate <ref> --to <m>` | Same GUID, placement follows |
| **Test copy** on same machine | `repo fork <ref> --tag <tag>` then `repo up <ref>:<tag>` | New GUID, shares encryption cred |

### Cross-machine fork (independent copy)

The fork uses the name:tag model — `<parent>:<tag>` (e.g., `my-app:staging`). It's an independent repo with its own GUID and networkId. Both parent and fork can run simultaneously on different machines.

```bash
# 1. Fork (creates new identity; runs where the parent lives, the machine is derived)
rdc repo fork <parent> --tag <tag>

# 2. Push the fork to target and deploy it there
rdc repo push <parent>:<tag> --to-machine <target-machine>
rdc backup restore <parent>:<tag> --as <parent> -m <target-machine> --up
```

**Note**: The CLI automatically resolves the parent repo's LUKS credential for forks. This is handled internally because forks inherit the parent's encryption key.

### Simple migration (same identity)
```bash
# Push and deploy on the target in one command
rdc repo push <repo> --to-machine <target-machine>
rdc backup restore <repo> --as <repo> -m <target-machine> --up
```

## Delta transfer for repo push

`repo push --to-machine` uses rsync delta transfer. When a previous backup already exists on the target:
- **First push**: Full transfer (entire LUKS image, e.g., 2.15GB).
- **Subsequent pushes**: Only changed blocks are sent. A 2.15GB repo with small changes transfers ~1.8MB (speedup 985x).
- Renet logs: `"Pre-seeded temp from existing backup (delta transfer enabled)"` confirms delta mode.
- The speedup ratio is shown in rsync output: `total size is 2.15G  speedup is 985.81`.

This makes incremental backups and frequent pushes very fast after the initial full transfer.

## Snapshots

There is no `repo snapshot` command. Point-in-time copies come from two places:

- **Datastore snapshots** (whole pool): `rdc datastore snapshot create <datastore> --snapshot <label>` and `rdc datastore snapshot list <datastore>`. A snapshot costs nothing at rest and is what a datastore fork clones from.
- **Per-repo point-in-time copies**: `rdc repo fork <ref> --tag <tag>` (CoW, near-instant), or the branching verbs `rdc repo commit` / `branch` / `checkout` / `log` / `merge` for an immutable commit history.

## Prune — cleanup orphaned resources

Two prune commands remove resources no longer referenced by any config file.

### Storage prune (orphaned backups in cloud/external storage)
Multi-config safe: scans all config files in `~/.config/rediacc/` before deciding a backup is orphaned. Recently archived repos within the grace period are protected.

### Machine prune (datastore + orphaned repo images)
Phase 1: clean stale mounts, locks, snapshots. Phase 2 (with `--orphaned-repos`): also delete repo images not in any config.

### Grace period configuration

Set a default grace period in config so `--grace-days` is not required each time. `config set`
takes the key and value positionally:

```bash
rdc config set pruneGraceDays 14
```

Precedence: `--grace-days` flag > `pruneGraceDays` in config > 7-day default.
