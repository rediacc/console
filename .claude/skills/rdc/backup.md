# rdc backup — Backup, Restore & Machine-to-Machine Transfer

Transfer repository images between machines or to/from external storage.

**Prerequisite**: Both source AND target machines must be registered, set up, and the CLI SSH key must be configured. See "Prerequisites for ops VMs" in [SKILL.md](SKILL.md) and [config.md](config.md).

## Commands

### Push to another machine
```
rdc backup push <repo> -m <source-machine> --to-machine <target-machine> [--checkpoint] [--force]
```
Copies the encrypted repo image directly to the target machine with the **same GUID**. This is a backup/migration, not a fork. After push, deploy on target with:
```
rdc repo up <repo> -m <target-machine> --mount
```

**Important**: `--mount` is required on first deploy after push — the volume needs to be opened (LUKS decryption). The repo's credential must be in the config. If pushing a fork, use `--grand <parent>` on `repo up` to inherit the parent's credential.

### Push to storage
```
rdc backup push <repo> -m <machine> --to <storage-name> [--dest <filename>] [--tag <tag>]
```
Backs up to configured external storage (S3, local file, etc.).

### Pull from another machine
```
rdc backup pull <repo> -m <target-machine> --from-machine <source-machine> [--force]
```

### Pull from storage
```
rdc backup pull <repo> -m <machine> --from <storage-name> [--force]
```

### List backups
```
rdc backup list --from-machine <machine>
rdc backup list --from <storage-name>
```

### Live migration with CRIU checkpoint

CRIU (Checkpoint/Restore In Userspace) captures running process memory state. The process resumes on the target exactly where it left off — in-memory variables, open connections, counters all preserved.

```bash
# On source: checkpoint all containers + push (captures process memory + disk state)
rdc backup push <repo> -m <source> --to-machine <target> --checkpoint

# On target: restore with checkpoint (process resumes from saved state)
rdc repo up <repo> -m <target> --mount --checkpoint
```

**What's preserved**: Process memory, open file descriptors, in-memory variables, timers. The app continues from the exact instruction where it was checkpointed.

**What to expect**: After restore, the app doesn't re-run prep/up lifecycle — containers resume directly from checkpoint. Logs will continue from where they left off (no "Starting..." messages).

### Fork + CRIU (independent copy with live state)

```bash
# Fork locally, then checkpoint + push the fork
rdc repo fork <parent> -m <source> --tag <fork-name>
rdc backup push <fork-name> -m <source> --to-machine <target> --checkpoint
rdc repo up <fork-name> -m <target> --mount --checkpoint --grand <parent>
```

### CRIU troubleshooting

- **Docker experimental is auto-enabled**: Per-repo Docker daemons have `"experimental": true` in their generated daemon.json. System Docker is configured during `rdc config setup-machine`. You don't need to enable this manually.
- **CRIU must be installed on VMs**: `rdc config setup-machine` installs CRIU from system packages and writes `/etc/criu/runc.conf` with `tcp-established`. If checkpoint fails with "CRIU is not installed", re-run setup-machine.
- **Host networking is forced by renet**: `renet compose` overwrites all services to `network_mode: host` regardless of what the compose file says. This is required for CRIU compatibility.
- **CRIU security settings are auto-injected**: `renet compose` adds `cap_add: [CHECKPOINT_RESTORE, SYS_PTRACE, NET_ADMIN]`, `security_opt: [apparmor=unconfined]`, and `userns_mode: host` to every container. Docker's default seccomp profile is preserved (CRIU suspends it via `PTRACE_O_SUSPEND_SECCOMP`). Do not set these manually.
- **TCP connections break after cross-machine restore**: Apps with persistent connections (database pools, websockets) must handle both `ECONNRESET` (stale socket) and `ECONNREFUSED` (service not yet accepting connections). After restore, dependent services like databases may need a few seconds to become ready even though their containers show as "running". See the [heartbeat template](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) for a CRIU-safe reconnection pattern.
- **`restart: always` conflicts with CRIU**: Use `restart: on-failure` or omit it.
- CRIU captures kernel-specific state (cgroup paths, mount IDs, container IDs). Cross-machine restore works best with compatible Docker versions.
- **Do NOT attempt manual workarounds** (raw `docker checkpoint`, `runc`, or `rdc term -c "..."` with Docker commands). Always use `rdc backup push --checkpoint` and `rdc repo up --checkpoint`.
- If checkpoint fails, the push/deploy still succeeds — it falls back to a fresh start (no process memory preservation).

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

### Configure schedule
```
rdc backup schedule set [--interval <cron>] [--storage <name>] [--retention <count>]
```

### Show schedule
```
rdc backup schedule show
```

### Push schedule to machine (systemd timer)
```
rdc backup schedule push <machine>
```

## Fork vs Push — when to use which

| Goal | Command | Result |
|------|---------|--------|
| **Independent copy** on another machine | `repo fork` → `backup push` fork → `repo up --mount` | New GUID, new networkId, new IPs |
| **Migrate/backup** same repo to another machine | `backup push --to-machine` → `repo up --mount` | Same GUID, same identity |
| **Test copy** on same machine | `repo fork --tag <name>` → `repo up --mount` | New GUID, shares encryption cred |

### Cross-machine fork (independent copy)

The fork gets a **different name** (via `--tag`) because it's an independent repo with its own GUID and networkId. Both parent and fork can run simultaneously on different machines.

```bash
# 1. Fork locally (creates new identity — runs on source machine)
rdc repo fork <parent> -m <source-machine> --tag <fork-name>

# 2. Push the fork to target
rdc backup push <fork-name> -m <source-machine> --to-machine <target-machine>

# 3. Deploy on target (--mount + --grand to unlock with parent's credential)
rdc repo up <fork-name> -m <target-machine> --mount --grand <parent>
```

**Note**: `--grand <parent>` tells the CLI to use the parent repo's LUKS credential to unlock the fork. This is required because forks inherit the parent's encryption key.

### Simple migration (same identity)
```bash
# 1. Push directly
rdc backup push <repo> -m <source-machine> --to-machine <target-machine>

# 2. Deploy on target
rdc repo up <repo> -m <target-machine> --mount
```

## Delta transfer for repo push

`backup push --to-machine` uses rsync delta transfer. When a previous backup already exists on the target:
- **First push**: Full transfer (entire LUKS image, e.g., 2.15GB).
- **Subsequent pushes**: Only changed blocks are sent. A 2.15GB repo with small changes transfers ~1.8MB (speedup 985x).
- Renet logs: `"Pre-seeded temp from existing backup (delta transfer enabled)"` confirms delta mode.
- The speedup ratio is shown in rsync output: `total size is 2.15G  speedup is 985.81`.

This makes incremental backups and frequent pushes very fast after the initial full transfer.

## Snapshots (BTRFS)

Local point-in-time snapshots on the same machine:

```
rdc snapshot create <repo> -m <machine>
rdc snapshot list [repo] -m <machine>
rdc snapshot delete <repo> <snapshot-name> -m <machine>
```
