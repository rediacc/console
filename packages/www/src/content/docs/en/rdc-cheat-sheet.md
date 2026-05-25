---
title: RDC CLI Cheat Sheet
description: Quick reference for all rdc commands, configs, repos, machines, sync, containers, and more.
category: Guides
order: 3
language: en
---

# RDC CLI Cheat Sheet

Quick reference for the most common `rdc` commands. Run any command with `--help` for full options.

## Repository Lifecycle

| Command | Description |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Create a new repository on a machine |
| `rdc repo up --name <repo> -m <machine>` | Deploy or update a repository |
| `rdc repo down --name <repo> -m <machine>` | Stop a repository |
| `rdc repo delete --name <repo> -m <machine>` | Delete a repository |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Fork a repository (near-instant, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Take ownership of an existing repository |
| `rdc config repository list` | List all repositories with name and GUID |

## Per-repo Secrets

Write-only deploy-time credentials. `get` returns the digest only. The value is never returned. See [Repositories § Secrets](/en/docs/repositories#secrets) for the full guide.

| Command | Description |
|---------|-------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Create a new secret (`--current ""` for first-write) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | Overwrite an existing secret (passwd-style precondition) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | Overwrite without verifying prior value (audited as rotation) |
| `rdc repo secret list --name <repo>` | List secret names + delivery modes (never values, never digests) |
| `rdc repo secret get --name <repo> --key <KEY>` | Show secret digest + mode (no plaintext value, ever) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | Delete a secret |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | Delete without verifying prior value |

> Forks inherit no secrets. Set them on the fork explicitly with `rdc repo secret set --name <repo>:<tag>`.

## Backup and Restore

| Command | Description |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Push a repository backup to storage |
| `rdc repo push --to <storage> -m <machine>` | Push all repositories to storage |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Restore a repository from storage |
| `rdc repo pull --from <storage> -m <machine>` | Restore all repositories from storage |
| `rdc repo push ... --bwlimit <limit>` | Limit rsync bandwidth during push (e.g. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limit rsync bandwidth during pull |
| `rdc repo push ... --checkpoint` | Checkpoint containers before pushing |
| `rdc repo backup list --from <storage> -m <machine>` | List available backups in storage |
| `rdc storage browse --name <storage>` | Browse storage contents |

## Repository Migration

| Command | Description |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Move a repository between machines |
| `rdc repo migrate ... --provision` | Provision on destination before transferring |
| `rdc repo migrate ... --checkpoint` | Checkpoint before migrating |
| `rdc repo migrate ... --skip-dns` | Skip DNS update after migration |
| `rdc repo migrate ... --bwlimit <limit>` | Limit transfer bandwidth |

## Backup Strategies

| Command | Description |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Create or update a named backup strategy |
| `rdc config backup-strategy list` | List all defined backup strategies |
| `rdc config backup-strategy show --name <name>` | Show details of a strategy |
| `rdc config backup-strategy remove --name <name>` | Remove a strategy |
| `rdc machine backup schedule -m <machine>` | Deploy configured backup strategies to a machine |

## Backup Operations

| Command | Description |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | Deploy bound strategies as systemd timers |
| `rdc machine backup schedule -m <machine> --dry-run` | Preview timer units without deploying (tokens masked) |
| `rdc machine backup now -m <machine>` | Run all bound strategies immediately |
| `rdc machine backup now -m <machine> --strategy <name>` | Run a specific strategy immediately |
| `rdc machine backup status -m <machine>` | Show timer status and recent job results |
| `rdc machine backup status -m <machine> --strategy <name>` | Show status for a specific strategy |
| `rdc machine backup cancel -m <machine>` | Cancel running backups |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Cancel a specific running backup |

## Machine Management

| Command | Description |
|---------|-------------|
| `rdc machine query --name <machine>` | Full machine status (system, containers, services, repos, network) |
| `rdc machine query --name <machine> --system` | System info only |
| `rdc machine query --name <machine> --containers` | Container list only |
| `rdc machine query --name <machine> --repositories` | Repository list only |
| `rdc machine query --name <machine> --services` | Service list only |
| `rdc machine query --name <machine> --network` | Network info only |
| `rdc machine query --name <machine> --block-devices` | Block device info only |
| `rdc machine list` | List all machines in config |
| `rdc config machine setup --name <machine>` | Run initial machine provisioning |
| `rdc machine prune --name <machine>` | Remove unused resources from machine |
| `rdc machine deprovision --name <machine>` | Fully deprovision a machine |
| `rdc machine vault-status --name <machine>` | Show LUKS vault status |

## Terminal and Sync

| Command | Description |
|---------|-------------|
| `rdc term connect -m <machine>` | Open SSH terminal to machine |
| `rdc term connect -m <machine> -r <repo>` | Open SSH terminal to repository (sets DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Run a command on machine |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Upload one or more local files/dirs to repository |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | Upload a single local file to an explicit remote path |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Download repository directory locally |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Download a single remote file into a local dir |
| `rdc vscode connect -m <machine> -r <repo>` | Open VS Code Remote SSH session |

## Configuration

| Command | Description |
|---------|-------------|
| `rdc config init --name <name>` | Create a named config file |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Add a machine to config |
| `rdc config storage import --file rclone.conf` | Import storage providers from rclone config |
| `rdc config storage list` | List configured storage providers |
| `rdc config backup-strategy set ...` | Define a named backup strategy |
| `rdc --config <name> <command>` | Use a named config file |

## Debug and Escape Hatch

| Command | Description |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | List containers in a repository |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Fetch container logs |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Execute command in container |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Restart a container |
