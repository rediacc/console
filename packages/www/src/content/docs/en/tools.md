---
title: "Tools"
description: "File sync, terminal access, VS Code integration, updates, and diagnostics."
category: "Getting Started"
order: 4
language: en
---

# Tools

Rediacc includes several productivity tools for working with remote repositories. These tools build on top of the SSH connection established by your context configuration.

## File Synchronization (sync)

Transfer files between your workstation and a remote repository using rsync over SSH.

### Upload Files

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### Download Files

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### Options

| Option | Description |
|--------|-------------|
| `-m, --machine <name>` | Target machine |
| `--local <path>` | Local directory path |
| `--remote <path>` | Remote path (relative to repository mount) |
| `--dry-run` | Preview changes without transferring |
| `--delete` | Delete files at the destination that don't exist at the source |

The `--dry-run` flag is useful for previewing what will be transferred before committing to the sync.

## SSH Terminal (term)

Open an interactive SSH session to a machine or directly into a repository's mount path.

### Connect to a Machine

```bash
rdc term connect server-1
```

### Connect to a Repository

```bash
rdc term connect my-app -m server-1
```

When connecting to a repository, the terminal session starts in the repository's mount directory with the repository's Docker socket configured.

## VS Code Integration (vscode)

Open a remote SSH session in VS Code, pre-configured with the correct SSH settings and the Remote SSH extension.

### Connect to a Repository

```bash
rdc vscode connect my-app -m server-1
```

This command:
1. Detects your VS Code installation
2. Configures the SSH connection in `~/.ssh/config`
3. Persists the SSH key for the session
4. Opens VS Code with a Remote SSH connection to the repository path

### List Configured Connections

```bash
rdc vscode list
```

Shows all SSH connections that have been configured for VS Code.

### Clean Up Connections

```bash
rdc vscode clean
```

Removes VS Code SSH configurations that are no longer needed.

> **Prerequisite:** Install the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) extension in VS Code.

## CLI Updates (update)

Keep the `rdc` CLI up to date with the latest features and bug fixes.

### Check for Updates

```bash
rdc update --check-only
```

### Apply Update

```bash
rdc update
```

Updates are downloaded and applied in-place. The new version takes effect on the next run.

### Rollback

```bash
rdc update rollback
```

Reverts to the previously installed version. Only available after an update has been applied.

### Auto-Update Status

```bash
rdc update status
```

Shows current version, update channel, and auto-update configuration.

## System Diagnostics (doctor)

Run a comprehensive diagnostic check of your Rediacc environment.

```bash
rdc doctor
```

The doctor command checks:

| Category | Checks |
|----------|--------|
| **Environment** | Node.js version, CLI version, SEA mode |
| **Renet** | Binary presence, version, embedded CRIU and rsync |
| **Configuration** | Active context, mode, machines, SSH key |
| **Authentication** | Login status |

Each check reports **OK**, **Warning**, or **Error** with a brief explanation. Use this as a first step when troubleshooting any issue.
