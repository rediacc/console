---
title: "Architecture"
description: "How Rediacc works: two-tool architecture, operating modes, security model, and configuration structure."
category: "Guides"
order: 2
language: en
---

# Architecture

This page explains how Rediacc works under the hood: the two-tool architecture, operating modes, security model, and configuration structure.

## Two-Tool Architecture

Rediacc uses two binaries that work together over SSH:

![Two-Tool Architecture](/img/arch-two-tool.svg)

- **rdc** runs on your workstation (macOS, Linux, or Windows). It reads your local configuration, connects to remote machines over SSH, and invokes renet commands.
- **renet** runs on the remote server with root privileges. It manages LUKS-encrypted disk images, isolated Docker daemons, service orchestration, and reverse proxy configuration.

Every command you type locally translates to an SSH call that executes renet on the remote machine. You never need to SSH into servers manually.

## Operating Modes

Rediacc supports three modes, each determining where state is stored and how commands are executed.

![Operating Modes](/img/arch-operating-modes.svg)

### Local Mode

The default for self-hosted usage. All state lives in `~/.rediacc/config.json` on your workstation.

- Direct SSH connections to machines
- No external services required
- Single-user, single-workstation
- Context is created with `rdc context create-local`

### Cloud Mode (Experimental)

Uses the Rediacc API for state management and team collaboration.

- State stored in the cloud API
- Multi-user teams with role-based access
- Web console for visual management
- Context is created with `rdc context create`

> **Note:** Cloud mode commands are experimental. Enable them with `rdc --experimental <command>` or by setting `REDIACC_EXPERIMENTAL=1`.

### S3 Mode

Stores encrypted state in an S3-compatible bucket. Combines the self-hosted nature of local mode with portability across workstations.

- State stored in an S3/R2 bucket as `state.json`
- AES-256-GCM encryption with a master password
- Portable: any workstation with the bucket credentials can manage the infrastructure
- Context is created with `rdc context create-s3`

All three modes use the same CLI commands. The mode only affects where state is stored and how authentication works.

## The rediacc User

When you run `rdc context setup-machine`, renet creates a system user called `rediacc` on the remote server:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (cannot log in via SSH)
- **Purpose**: Owns repository files and runs Rediaccfile functions

The `rediacc` user cannot be accessed via SSH directly. Instead, rdc connects as the SSH user you configured (e.g., `deploy`), and renet executes repository operations via `sudo -u rediacc /bin/sh -c '...'`. This means:

1. Your SSH user needs `sudo` privileges
2. All repository data is owned by `rediacc`, not your SSH user
3. Rediaccfile functions (`prep()`, `up()`, `down()`) run as `rediacc`

This separation ensures that repository data has consistent ownership regardless of which SSH user manages it.

## Docker Isolation

Each repository gets its own isolated Docker daemon. When a repository is mounted, renet starts a dedicated `dockerd` process with a unique socket:

![Docker Isolation](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

For example, a repository with network ID `2816` uses:
```
/var/run/rediacc/docker-2816.sock
```

This means:
- Containers from different repositories cannot see each other
- Each repository has its own image cache, networks, and volumes
- The host Docker daemon (if any) is completely separate

Rediaccfile functions automatically have `DOCKER_HOST` set to the correct socket.

## LUKS Encryption

Repositories are LUKS-encrypted disk images stored on the server's datastore (default: `/mnt/rediacc`). Each repository:

1. Has a randomly generated encryption passphrase (the "credential")
2. Is stored as a file: `{datastore}/repos/{guid}.img`
3. Is mounted via `cryptsetup` when accessed

The credential is stored in your local `config.json` but **never** on the server. Without the credential, the repository data cannot be read. When autostart is enabled, a secondary LUKS keyfile is stored on the server to allow automatic mounting on boot.

## Configuration Structure

All configuration is stored in `~/.rediacc/config.json`. Here is an annotated example:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "storages": {
        "backblaze": {
          "provider": "b2",
          "vaultContent": { "...": "..." }
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Key fields:**

| Field | Description |
|-------|-------------|
| `mode` | `"local"`, `"s3"`, or omitted for cloud mode |
| `apiUrl` | `"local://"` for local mode, API URL for cloud mode |
| `ssh.privateKeyPath` | SSH private key used for all machine connections |
| `machines.<name>.user` | SSH username for connecting to the machine |
| `machines.<name>.knownHosts` | SSH host keys from `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID identifying the encrypted disk image |
| `repositories.<name>.credential` | LUKS encryption passphrase (**not stored on server**) |
| `repositories.<name>.networkId` | Determines the IP subnet (2816 + n*64), auto-assigned |
| `nextNetworkId` | Global counter for assigning network IDs |
| `universalUser` | Override the default system user (`rediacc`) |

> This file contains sensitive data (SSH key paths, LUKS credentials). It is stored with `0600` permissions (owner read/write only). Do not share it or commit it to version control.
