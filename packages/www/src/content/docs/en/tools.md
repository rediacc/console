---
title: "Tools"
description: "File sync, terminal access, VS Code integration, and CLI updates."
category: "Guides"
order: 8
language: en
---

# Tools

Rediacc includes productivity tools for working with remote repositories: file sync, SSH terminal, VS Code integration, and CLI updates.

## File Synchronization (sync)

Transfer files between your workstation and a remote repository using rsync over SSH.

### Upload Files

```bash
rdc sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### Download Files

```bash
rdc sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### Check Sync Status

```bash
rdc sync status -m server-1 -r my-app
```

### Options

| Option | Description |
|--------|-------------|
| `-m, --machine <name>` | Target machine |
| `-r, --repository <name>` | Target repository |
| `--local <path>` | Local directory path |
| `--remote <path>` | Remote path (relative to repository mount) |
| `--dry-run` | Preview changes without transferring |
| `--mirror` | Mirror source to destination (delete extra files) |
| `--verify` | Verify checksums after transfer |
| `--confirm` | Interactive confirmation with detail view |
| `--exclude <patterns...>` | Exclude file patterns |

## SSH Terminal (term)

Open an interactive SSH session to a machine or into a repository's environment.

### Shorthand Syntax

The fastest way to connect:

```bash
rdc term server-1                    # Connect to a machine
rdc term server-1 my-app             # Connect to a repository
```

### Run a Command

Execute a command without opening an interactive session:

```bash
rdc term server-1 -c "uptime"
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket, so `docker ps` shows only that repository's containers.

### Connect Subcommand

The `connect` subcommand provides the same functionality with explicit flags:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Container Actions

Interact directly with a running container:

```bash
# Open a shell inside a container
rdc term server-1 my-app --container <container-id>

# View container logs
rdc term server-1 my-app --container <container-id> --container-action logs

# Follow logs in real-time
rdc term server-1 my-app --container <container-id> --container-action logs --follow

# View container stats
rdc term server-1 my-app --container <container-id> --container-action stats

# Execute a command in a container
rdc term server-1 my-app --container <container-id> --container-action exec -c "ls -la"
```

| Option | Description |
|--------|-------------|
| `--container <id>` | Target Docker container ID |
| `--container-action <action>` | Action: `terminal` (default), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Number of log lines to show (default: 50) |
| `--follow` | Follow logs continuously |
| `--external` | Use external terminal instead of inline SSH |

## VS Code Integration (vscode)

Open a remote SSH session in VS Code, pre-configured with the correct SSH settings.

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

### Clean Up Connections

```bash
rdc vscode clean
```

Removes VS Code SSH configurations that are no longer needed.

### Check Configuration

```bash
rdc vscode check
```

Verifies VS Code installation, Remote SSH extension, and active connections.

> **Prerequisite:** Install the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) extension in VS Code.

## CLI Updates (update)

Keep the `rdc` CLI up to date.

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

### Update Status

```bash
rdc update status
```

Shows current version, update channel, and auto-update configuration.
