---
name: rdc
description: Rediacc CLI for managing machines, repositories, and deployments over SSH. Use when provisioning VMs, deploying apps, managing containers, syncing files, or operating remote infrastructure.
user-invocable: false
---

# rdc — Rediacc CLI

`rdc` manages machines, encrypted repositories, and deployments over SSH.

## How to run

In development: `./rdc.sh <command>` (builds deps, runs via tsx, ~5s startup overhead).
In production: `rdc <command>` directly.

Each `./rdc.sh` invocation has bootstrap overhead. Chain independent commands with `&&` or `;` to minimize total invocations.

## Command reference

For complete command syntax and options, see [reference.md](reference.md) (auto-generated from CLI — do not edit manually).

Every command also supports `--help`:
```
./rdc.sh <command> --help
```

## Command groups

| Group | Purpose | Details |
|-------|---------|---------|
| `ops` | Local VM provisioning | [ops.md](ops.md) |
| `config` | Machine registration, SSH, setup | [config.md](config.md) |
| `repo` | Repository lifecycle, backup, sync, snapshots | [repositories.md](repositories.md) |
| `repo push/pull` | Backup, restore, machine-to-machine transfer | [backup.md](backup.md) |
| `repo sync` | File transfer to/from repos | [sync.md](sync.md) |
| `repo tunnel` | SSH port-forward tunnel to container ports | — |
| `repo snapshot` | BTRFS point-in-time snapshots | [backup.md](backup.md) |
| `machine` | Remote machine inspection | [machines.md](machines.md) |
| `datastore` | Ceph RBD datastore, instant fork/unfork | [datastore.md](datastore.md) |
| `term` | SSH terminal access + container actions | [terminal.md](terminal.md) |
| containers | High-level container commands | [execution.md](execution.md) |
| `store` | Config sync to external backends | [config-storage.md](config-storage.md) |

## Key patterns

- **`-m <machine>`**: Most commands need a target machine name.
- **`-r <repository>`**: Sync commands need a repository name.
- **`--debug`**: Verbose output for troubleshooting.
- **`--dry-run`**: Preview without executing (supported by repo and sync commands).
- **`--output json`**: Machine-readable output (global option).
- All repo commands use the `-m` flag, not positional machine arguments.

## Typical workflow

1. **Provision** VMs or register existing machines → see [ops.md](ops.md) and [config.md](config.md)
2. **Create** a repository on a machine → see [repositories.md](repositories.md)
3. **Upload** application files → see [sync.md](sync.md)
4. **Deploy** with `repo up` → see [repositories.md](repositories.md)
5. **Verify** with `machine containers` and `term --container-action logs` → see [machines.md](machines.md) and [execution.md](execution.md)

## Quick-start: Deploy an app to an ops VM

If VMs are already running and machine is registered, these 4 commands deploy an app. Substitute names as needed:

```bash
# 1. Create encrypted repo (takes ~25s for LUKS format, leaves volume mounted and ready)
rdc repo create --name <app-name> -m <machine> --size 2G

# 2. Upload your app files (Rediaccfile + docker-compose.yaml + any app code)
rdc repo sync upload -m <machine> -r <app-name> --local <path-to-app-dir>/

# 3. Deploy (runs Rediaccfile up, starts containers)
rdc repo up --name <app-name> -m <machine>

# 4. Verify (~5s after deploy for first output)
rdc machine containers <machine>
rdc term connect -m <machine> -r <app-name> --container <container-name> --container-action logs --log-lines 20
```

For first-time setup (new VMs), see prerequisites in [ops.md](ops.md) and [config.md](config.md).

## Quick-start: Push a repo to another machine

```bash
# Migration (same identity)
rdc repo push --name <repo> -m <source> --to-machine <target>
rdc repo up --name <repo> -m <target>

# Independent fork to another machine (--grand passes parent's encryption key)
rdc repo fork --parent <repo> --tag <tag> -m <source>
rdc repo push --name <repo>:<tag> -m <source> --to-machine <target>
rdc repo up --name <repo>:<tag> -m <target>
```

## Quick-start: Live migration with CRIU

```bash
# Checkpoint + push (captures process memory + disk state, source keeps running)
rdc repo push --name <repo> -m <source> --to-machine <target> --checkpoint

# Restore on target (auto-detects checkpoint, resumes process state)
rdc repo up --name <repo> -m <target>
```

## Quick-start: Same-machine fork with CRIU

```bash
# Fork with live state — app continues from checkpoint, DB starts fresh
rdc repo fork --parent <repo> --tag <tag> -m <machine> --checkpoint
rdc repo mount --name <repo>:<tag> -m <machine>
rdc repo up --name <repo>:<tag> -m <machine>
```

## Quick-start: Save/restore (stop and resume later)

```bash
rdc repo down --name <repo> -m <machine> --checkpoint    # Saves state, stops
rdc repo up --name <repo> -m <machine>                    # Auto-restores
```

Requires `rediacc.checkpoint=true` label on containers to checkpoint. See [backup.md](backup.md) for full CRIU details, label setup, and troubleshooting.

## Quick-start: Instant fork with Ceph (zero data transfer)

```bash
# 1. Configure Ceph for the source machine (one-time; ops pool is rediacc_rbd_pool)
rdc config machine set-ceph -m <machine> --pool rediacc_rbd_pool --image ds-prod

# 2. Initialize Ceph-backed datastore (one-time; reads image/pool from config)
rdc datastore init -m <machine> --backend ceph --size 100G --force

# 3. Fork to another machine (Ceph operation < 2s; ~4s total with CLI bootstrap)
rdc datastore fork -m <machine> --to <target>
# Output includes: Snapshot: fork-<timestamp>, Clone: <image>-fork-<target>

# 4. Clean up when done (all three IDs required — get from fork output above)
# --force ensures all cleanup steps run even if one fails (recommended)
rdc datastore unfork -m <machine> --source <image> --snapshot fork-<timestamp> --dest <image>-fork-<target> --force
```

Requires a Ceph cluster (provisioned by `rdc ops up`). See [datastore.md](datastore.md) for full details.

## Quick-start: SSH tunnel to a container port

```bash
# Tunnel a container's port to localhost (e.g. database access from local tools)
rdc repo tunnel -m <machine> -r <repo> -c <container> --port 5432

# Auto-detect container and port (when repo has a single running container)
rdc repo tunnel -m <machine> -r <repo>

# Map to a different local port
rdc repo tunnel -m <machine> -r <repo> -c <container> --port 5432 --local 15432
```

Keeps the tunnel open until Ctrl+C. Requires the container to have a `rediacc.service_ip` label (assigned automatically by renet).

## Prerequisites for ops VMs (READ FIRST)

Before ANY operation on ops-provisioned VMs, the CLI must have the correct SSH key:

```bash
rdc config ssh set --key ~/.renet/staging/.ssh/id_rsa
```

This is required because ops VMs trust a staging key, not your default SSH key. Without this, all remote operations (setup-machine, repo create, repo push, sync, etc.) will fail with "All configured authentication methods failed".

Each target machine must also be registered and set up:
```bash
rdc config machine add --name <name> --ip <ip> --user <username>
rdc config machine setup --name <name>
```

See [config.md](config.md) for full details.

## Security — Agent guards

- **Fork-only mode** (default): AI agents can only modify fork repositories. Grand (original) repos are protected. To override, set `REDIACC_ALLOW_GRAND_REPO=<repo-name>`, a comma-separated list (`repo1,repo2`), or `REDIACC_ALLOW_GRAND_REPO=*` for all repos.
- **MCP fork-only mode**: The MCP server (`rdc mcp serve`) runs in fork-only mode by default. Use `--allow-grand` flag to enable grand repo access.
- **Per-repo SSH keys + server-side sandbox**: Each repo has its own SSH key with `command="renet sandbox-gateway <name>"` in `authorized_keys`. Every SSH session (term, VS Code, sync) is sandboxed server-side with Landlock filesystem restrictions, OverlayFS home overlay, and per-repo TMPDIR. Cross-repo access blocked by the kernel. `.envrc` auto-loaded for Docker access.
- **Machine-level SSH**: Direct machine access (`rdc term connect -m <machine>` without a repo) is blocked for agents unless `REDIACC_ALLOW_GRAND_REPO=*` is set. A comma-separated repo list does not unlock machine-level access, only `*` does (including `*` appearing inside a list such as `repo1,*,repo2`).

## Operational details

- **Router watchdog**: The renet router includes a watchdog that auto-recovers stopped containers based on restart policies saved in `.rediacc.json`.
- **Operation timing**: Remote operations show step-by-step timing (`Completed in X.Xs (total: Y.Ys)`).

## Important conventions

- **Never use raw SSH, SCP, or `rdc term connect -c` as a workaround** — `rdc` has dedicated commands for all remote operations. If a command fails, report it as a bug rather than working around it with `term connect -c` or raw docker/runc commands.
- **Never use `rdc term connect -c` to run docker commands** — use `rdc machine containers`, `rdc run container_logs`, `rdc run container_exec`, etc. See [terminal.md](terminal.md) for the complete list of what NOT to use `term` for.
- Repositories use `renet compose` (not `docker compose`). Renet injects network isolation, host networking, and per-service loopback IPs.
- Each repository gets an isolated Docker daemon, encrypted LUKS volume, and dedicated IP range.
- The "Proxy is not running" warning during `repo up` is informational and does not affect functionality.
- If a `rdc` command fails or doesn't do what you expect, **report the exact error** — do not attempt manual fixes via SSH.
