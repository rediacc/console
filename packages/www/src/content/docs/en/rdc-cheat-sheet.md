---
title: RDC CLI Cheat Sheet
description: "Quick reference for rdc: configs, repos, machines, file sync, and containers. Full option set: add --help to any command."
category: Guides
order: 3
cardGrid: true
language: en
---

# RDC CLI Cheat Sheet

Not every `rdc` command is listed here, just the ones that come up on every deployment. For the full option set, run any rdc command with `--help`. Edge cases and rarely-used options are in the full reference.

## Repository Lifecycle

| Command | Description |
|---------|-------------|
| `rdc repo create <repo> -m <machine>` | Create a new repository on a machine |
| `rdc repo up <repo>@<machine>` | Deploy or update a repository |
| `rdc repo down <repo>@<machine>` | Stop a repository |
| `rdc repo delete <repo>@<machine>` | Delete a repository |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Fork a repository (near-instant, BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | Promote a validated fork to production under its parent's name |
| `rdc repo list` | List all repositories with name and GUID |

## Per-repo Secrets

Write-only deploy-time credentials. `get` returns the digest only. The value is never returned. See [Repositories § Secrets](/en/docs/repositories#secrets) for the full guide.

| Command | Description |
|---------|-------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Create a new secret (`--current ""` for first-write) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Overwrite an existing secret (passwd-style precondition) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Overwrite without verifying prior value (audited as rotation) |
| `rdc repo secret list <repo>` | List secret names + delivery modes (never values, never digests) |
| `rdc repo secret get <repo> --key <KEY>` | Show secret digest + mode (no plaintext value, ever) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Delete a secret |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Delete without verifying prior value |

> Forks inherit no secrets. Set them on the fork explicitly with `rdc repo secret set <repo>:<tag>`.

## Backup and Restore

| Command | Description |
|---------|-------------|
| `rdc repo push ... --bwlimit <limit>` | Limit rsync bandwidth during push (e.g. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limit rsync bandwidth during pull |
| `rdc repo push ... --checkpoint` | Checkpoint containers before pushing |
| `rdc backup manifests <repo-ref>` | List the snapshots the chunk store holds |
| `rdc backup browse <repo-ref>` | List the files a repository contains (local, read-only) |
| `rdc backup snapshot <repo>` | Upload a chunk-store snapshot: full inventory first, changed cells after |
| `rdc backup snapshot <repo> --dry-run` | Plan the snapshot without uploading; reports what would move |
| `rdc backup verify <repo>` | Verify a repository's backup anchor against the chunk store |
| `rdc backup usage` | Show chunk-store bytes stored against your quota |
| `rdc backup manifests <repo>` | List snapshot manifests recorded on the server |
| `rdc storage browse <storage>` | Browse storage contents |

## Repository Migration

| Command | Description |
|---------|-------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Move a repository between machines |
| `rdc repo migrate ... --provision` | Provision on destination before transferring |
| `rdc repo migrate ... --checkpoint` | Checkpoint before migrating |
| `rdc repo migrate ... --skip-dns` | Skip DNS update after migration |
| `rdc repo migrate ... --bwlimit <limit>` | Limit transfer bandwidth |

## Backup Strategies

| Command | Description |
|---------|-------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Create or update a named backup strategy |
| `rdc backup strategy list` | List all defined backup strategies |
| `rdc backup strategy show <name>` | Show details of a strategy |
| `rdc backup strategy remove <name>` | Remove a strategy |
| `rdc backup schedule -m <machine>` | Deploy configured backup strategies to a machine |

## Backup Operations

| Command | Description |
|---------|-------------|
| `rdc backup schedule -m <machine>` | Deploy bound strategies as systemd timers |
| `rdc backup schedule -m <machine> --dry-run` | Preview timer units without deploying (tokens masked) |
| `rdc backup run -m <machine>` | Run all bound strategies immediately |
| `rdc backup run <name> -m <machine>` | Run a specific strategy immediately |
| `rdc backup status -m <machine>` | Show timer status and recent job results |
| `rdc backup status <name> -m <machine>` | Show status for a specific strategy |
| `rdc backup cancel -m <machine>` | Cancel running backups |
| `rdc backup cancel <name> -m <machine>` | Cancel a specific running backup |

## Machine Management

| Command | Description |
|---------|-------------|
| `rdc machine status <machine>` | Full machine status (system, containers, services, repos, network) |
| `rdc machine status <machine> --system` | System info only |
| `rdc machine status <machine> --containers` | Container list only |
| `rdc machine status <machine> --repositories` | Repository list only |
| `rdc machine status <machine> --services` | Service list only |
| `rdc machine status <machine> --network` | Network info only |
| `rdc machine status <machine> --block-devices` | Block device info only |
| `rdc machine list` | List all machines in config |
| `rdc machine setup <machine>` | Run initial machine provisioning |
| `rdc machine prune <machine>` | Remove unused resources from machine |
| `rdc machine deprovision <machine>` | Fully deprovision a machine |

## Terminal and Sync

| Command | Description |
|---------|-------------|
| `rdc term connect <machine>` | Open SSH terminal to machine |
| `rdc term connect <repo>@<machine>` | Open SSH terminal to repository (sets DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Run a command on machine |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Upload one or more local files/dirs to repository |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Upload a single local file to an explicit remote path |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Download repository directory locally |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Download a single remote file into a local dir |
| `rdc vscode connect <repo>@<machine>` | Open VS Code Remote SSH session |

## Configuration

| Command | Description |
|---------|-------------|
| `rdc config init <name>` | Create a named config file |
| `rdc machine add <machine> --ip <host> --user <user>` | Add a machine to config |
| `rdc storage import rclone.conf` | Import storage providers from rclone config |
| `rdc storage list` | List configured storage providers |
| `rdc backup strategy set ...` | Define a named backup strategy |
| `rdc --config <name> <command>` | Use a named config file |

## Debug and Escape Hatch

| Command | Description |
|---------|-------------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | List containers in a repository |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Fetch container logs |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Execute command in container |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Restart a container |
