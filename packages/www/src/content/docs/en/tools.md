---
title: "Tools"
description: "File sync, terminal access, VS Code integration, and CLI updates."
category: "Guides"
order: 9
language: en
---

# Tools

Rediacc ships four tools for day-to-day work on your machines and repositories: file sync over SSH, an SSH terminal, VS Code integration, and CLI self-updates. All four run over SSH. No agent or daemon required on the remote side. If you need a GUI for any of this, you are looking at the wrong page.

## File Synchronization (sync)

Transfer files between your workstation and a remote repository using rsync over SSH.

### Upload Files

`--local` accepts one or more paths. Each path may be a file or a directory. Files land at `<remote>/<basename>`; directory contents merge into `<remote>/`. For a single file, prefer `--remote-file` to give the file its destination path explicitly.

```bash
# Directory (contents merged into remote)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Single file dropped into a remote directory (basename preserved)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Single file, explicit destination path
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Multiple sources in one call
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` and `--remote-file` are mutually exclusive. `--remote-file` requires exactly one `--local` path that points at a file.

`--mirror` cannot be combined with a file source; it would delete sibling files in the remote directory.

### Download Files

Use `--remote` for a directory (the default) or `--remote-file` for a single file. The two flags are mutually exclusive.

```bash
# Directory
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Single file: --local must be an existing directory
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Check Sync Status

```bash
rdc repo sync status -m server-1 -r my-app
```

### Options

| Option | Description |
|--------|-------------|
| `-m, --machine <name>` | Target machine |
| `-r, --repository <name>` | Target repository |
| `--local <paths...>` | One or more local file or directory paths (upload) or local destination directory (download) |
| `--remote <path>` | Remote directory (relative to repository mount) |
| `--remote-file <path>` | Remote file path for single-file uploads or downloads (alternative to `--remote`) |
| `--dry-run` | Preview changes without transferring |
| `--mirror` | Mirror source to destination, delete extra files (directory sources only) |
| `--verify` | Verify checksums after transfer |
| `--confirm` | Interactive confirmation with detail view |
| `--exclude <patterns...>` | Exclude file patterns |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## SSH Terminal (term)

Open an interactive SSH session to a machine or into a repository's environment.

### Shorthand Syntax

The fastest way to connect:

```bash
rdc term connect -m server-1                    # Connect to a machine
rdc term connect -m server-1 -r my-app             # Connect to a repository
```

### Run a Command

Execute a command without opening an interactive session:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket, so `docker ps` shows only that repository's containers.

### Connect Subcommand

Or use the `connect` subcommand for the same result, with explicit flags:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Container Actions

Interact directly with a running container:

```bash
# Open a shell inside a container
rdc term connect -m server-1 -r my-app --container <container-id>

# View container logs
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Follow logs in real-time
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# View container stats
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Execute a command in a container
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
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
rdc vscode connect -r my-app -m server-1
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
rdc vscode cleanup
```

Removes VS Code SSH configurations that are no longer needed.

### Check Configuration

```bash
rdc vscode check
```

Verifies VS Code installation, Remote SSH extension, and active connections.

> **Prerequisite:** Install the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) extension in VS Code.

### VS Code in the Browser

No local VS Code? Serve the editor from inside the repository sandbox and open it in any browser:

```bash
rdc vscode connect -r my-app -m server-1 --browser
```

This command:
1. Installs the open-source editor server on the machine once (read-only shared path, checksum-verified)
2. Starts it inside the repository sandbox, so the file tree, the integrated terminal, and every child process see exactly what the repository sees
3. Opens an SSH tunnel to a local port and launches your browser with a per-session token URL

The server keeps running after you close the tunnel; reconnecting reuses it. Manage it with:

```bash
rdc vscode serve status -r my-app -m server-1
rdc vscode serve stop -r my-app -m server-1
```

| Option | Description |
|--------|-------------|
| `--no-open` | Print the URL instead of launching the browser |
| `--url-only` | Print exactly one URL line on stdout (for scripting) and hold the tunnel |
| `--local <port>` | Pick the local tunnel port |
| `--server-provider <id>` | Editor server implementation: `openvscode` (default) or `code-server` |
| `--server-archive <file>` | Install from a pre-staged tarball on the machine (no internet needed) |

Works from Linux, macOS, Windows, or a tablet. The only local requirement is a browser.

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

Updates are downloaded and applied in-place. The CLI automatically picks the right binary for your platform (Linux, macOS, or Windows). The new version takes effect on the next run.

### Rollback

```bash
rdc update --rollback
```

Reverts to the previously installed version. Only available after an update has been applied.

### Update Status

```bash
rdc update --status
```

Shows current version, update channel, and auto-update configuration.

#### Release Channels

```bash
rdc update --channel edge      # Continuously deployed production updates
rdc update --channel stable    # Promoted from edge after 7-day soak (default)
rdc update --status            # Show current channel and version info
```
