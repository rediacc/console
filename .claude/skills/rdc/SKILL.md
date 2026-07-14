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
| `backup` | Backup strategies, scheduling, restore | [backup.md](backup.md) |
| `machine` | Machine registration, setup, inspection | [machines.md](machines.md) and [config.md](config.md) |
| `datastore` | Named, movable storage pools; instant fork | [datastore.md](datastore.md) |
| `term` | SSH terminal access | [terminal.md](terminal.md) |
| containers | High-level container commands | [execution.md](execution.md) |
| `config remote` | Config sync to the account server | [config-storage.md](config-storage.md) |

## Key patterns

- **Refs, not flags**: The thing a command acts on is a positional ref. A repo ref
  is `name`, `name:tag` for a fork, and optionally `name@machine` /
  `name:tag@machine` to assert where it lives. A bare `name` is the grand
  (production) repo.
- **The machine is derived**: `rdc repo up shop` finds shop's machine from config.
  Only commands that name a not-yet-placed thing still take `-m <machine>`
  (`repo create`, `datastore create`) or take it as a batch filter
  (`repo up --all -m <machine>`).
- **`--debug`**: Verbose output for troubleshooting.
- **`--dry-run`**: Preview without executing (supported by repo and sync commands).
- **`--output json`**: Machine-readable output (global option).

## Typical workflow

1. **Provision** VMs or register existing machines → see [ops.md](ops.md) and [config.md](config.md)
2. **Create** a repository on a machine → see [repositories.md](repositories.md)
3. **Upload** application files → see [sync.md](sync.md)
4. **Deploy** with `repo up` → see [repositories.md](repositories.md)
5. **Verify** with `machine status --containers` and `repo logs` → see [machines.md](machines.md) and [execution.md](execution.md)

## Quick-start: Deploy an app to an ops VM

If VMs are already running and machine is registered, these 4 commands deploy an app. Substitute names as needed:

```bash
# 1. Create encrypted repo (takes ~25s for LUKS format, leaves volume mounted and ready)
#    `repo create` still takes -m: the repo does not exist yet, so it has no machine to derive.
rdc repo create <app-name> -m <machine> --size 2G

# 2. Upload your app files (Rediaccfile + docker-compose.yaml + any app code)
rdc repo sync upload <app-name> --local <path-to-app-dir>/

# 3. Deploy (runs Rediaccfile up, starts containers)
rdc repo up <app-name>

# 4. Verify (~5s after deploy for first output)
rdc machine status <machine> --containers
rdc repo logs <app-name> -c <container-name> --lines 20
```

For first-time setup (new VMs), see prerequisites in [ops.md](ops.md) and [config.md](config.md).

## Quick-start: Push a repo to another machine

```bash
# Migration (same identity). A pushed copy lands on the target as a backup ARTIFACT,
# so it is booted with `backup restore` — that is where --up lives; `repo push` has no --up.
rdc repo push <repo> --to-machine <target>
rdc backup restore <repo> --as <repo> -m <target> --up

# Independent fork to another machine (the fork inherits the parent's encryption key)
rdc repo fork <repo> --tag <tag>
rdc repo push <repo>:<tag> --to-machine <target>
rdc backup restore <repo>:<tag> --as <repo> -m <target> --up
```

## Quick-start: Live migration with CRIU

```bash
# Checkpoint + push (captures process memory + disk state, source keeps running).
# The checkpoint rides along with the artifact; `backup restore --up` boots from it.
rdc repo push <repo> --to-machine <target> --checkpoint
rdc backup restore <repo> --as <repo> -m <target> --up

# Or move the repo outright (two-phase, minimal downtime, placement follows)
rdc repo migrate <repo> --to <target> --checkpoint
```

## Quick-start: Same-machine fork with CRIU

```bash
# Fork with live state: app continues from checkpoint, DB starts fresh.
# Forks are mounted automatically on first `repo up`; there is no separate `repo mount`.
rdc repo fork <repo> --tag <tag> --checkpoint
rdc repo up <repo>:<tag>
```

## Quick-start: Save/restore (stop and resume later)

```bash
rdc repo down <repo> --checkpoint    # Saves state, stops
rdc repo up <repo>                   # Auto-restores
```

Requires `rediacc.checkpoint=true` label on containers to checkpoint. See [backup.md](backup.md) for full CRIU details, label setup, and troubleshooting.

## Quick-start: Instant fork with Ceph (zero data transfer)

```bash
# 1. Create an rbd-backed datastore (one-time; ops pool is rediacc_rbd_pool)
rdc datastore create ds-prod -m <machine> --backend rbd --size 100G --pool rediacc_rbd_pool

# 2. Attach it to the machine that will hold it
rdc datastore attach ds-prod --to <machine>

# 3. Fork it and hand the fork to another machine (Ceph clone is instant, size-independent).
#    A fork must say where its writes go: local (ephemeral overlay) or ceph (durable clone).
rdc datastore fork ds-prod --tag <tag> --attach-to <target> --writes local

# 4. Clean up when done. A --writes local fork has nowhere to write back to,
#    so detaching it throws the overlay away and needs --discard.
rdc datastore detach ds-prod:<tag> --discard
```

Requires a Ceph cluster (provisioned by `rdc ops up`). See [datastore.md](datastore.md) for full details.

## Quick-start: SSH tunnel to a container port

```bash
# Tunnel a container's port to localhost (e.g. database access from local tools)
rdc repo tunnel <repo> -c <container> --port 5432

# Auto-detect container and port (when repo has a single running container)
rdc repo tunnel <repo>

# Map to a different local port
rdc repo tunnel <repo> -c <container> --port 5432 --local 15432
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
rdc machine add <name> --ip <ip> --user <username>
rdc machine setup <name>
```

See [config.md](config.md) for full details.

## Security — Agent guards

- **Fork-only mode** (default): AI agents can only modify fork repositories. Grand (original) repos are protected. To override, set `REDIACC_ALLOW_GRAND_REPO=<repo-name>`, a comma-separated list (`repo1,repo2`), or `REDIACC_ALLOW_GRAND_REPO=*` for all repos.
- **MCP fork-only mode**: The MCP server (`rdc mcp serve`) runs in fork-only mode by default. Use `--allow-grand` flag to enable grand repo access.
- **Per-repo SSH keys + server-side sandbox**: Each repo has its own SSH key with `command="renet sandbox-gateway <name>"` in `authorized_keys`. Every SSH session (term, VS Code, sync) is sandboxed server-side with Landlock filesystem restrictions, OverlayFS home overlay, and per-repo TMPDIR. Cross-repo access blocked by the kernel. `.envrc` auto-loaded for Docker access.
- **Machine-level SSH**: Direct machine access (`rdc term connect <machine>`, where the target is a machine name rather than a repo ref) is blocked for agents unless `REDIACC_ALLOW_GRAND_REPO=*` is set. A comma-separated repo list does not unlock machine-level access, only `*` does (including `*` appearing inside a list such as `repo1,*,repo2`).

## Operational details

- **Router watchdog**: The renet router includes a watchdog that auto-recovers stopped containers based on restart policies saved in `.rediacc.json`.
- **Operation timing**: Remote operations show step-by-step timing (`Completed in X.Xs (total: Y.Ys)`).

## Important conventions

- **Never use raw SSH, SCP, or `rdc term connect -c` as a workaround** — `rdc` has dedicated commands for all remote operations. If a command fails, report it as a bug rather than working around it with `term connect -c` or raw docker/runc commands.
- **Never use `rdc term connect -c` to run docker commands**. Use `rdc machine status <machine> --containers`, `rdc repo logs`, `rdc repo exec`, etc. See [terminal.md](terminal.md) for the complete list of what NOT to use `term` for.
- Repositories use `renet compose` (not `docker compose`). Renet injects network isolation, host networking, and per-service loopback IPs.
- Each repository gets an isolated Docker daemon, encrypted LUKS volume, and dedicated IP range.
- The "Proxy is not running" warning during `repo up` is informational and does not affect functionality.
- If a `rdc` command fails or doesn't do what you expect, **report the exact error** — do not attempt manual fixes via SSH.
