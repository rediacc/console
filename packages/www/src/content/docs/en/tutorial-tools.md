---
title: "Tools"
description: "Use SSH terminal access, file synchronization, VS Code integration, and CLI update commands."
category: "Tutorials"
order: 5
language: en
---

# How To Use Terminal, Sync, and VS Code Tools with Rediacc

The CLI includes productivity tools for day-to-day operations: SSH terminal access, file synchronization via rsync, VS Code remote development, and CLI updates. In this tutorial, you run remote commands, sync files to a repository, check VS Code integration, and verify your CLI version.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/en/docs/tutorial-repos))

## Interactive Recording

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### Step 1: Connect to a machine

Run inline commands on a remote machine via SSH without opening an interactive session.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

The `-c` flag executes a single command and returns the output. Omit `-c` to open an interactive SSH session.

### Step 2: Connect to a repository

To run commands inside a repository's isolated Docker environment:

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Step 3: Preview file sync (dry-run)

Before transferring files, preview what would change.

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag shows new files, changed files, and total transfer size without actually uploading anything.

### Step 4: Upload files

Transfer files from your local machine to the remote repository mount.

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Files are transferred via rsync over SSH. Only changed files are sent on subsequent uploads.

### Step 5: Verify uploaded files

Confirm the files arrived by listing the repository's mount directory.

```bash
rdc term server-1 my-app -c "ls -la"
```

### Step 6: VS Code integration check

To develop remotely with VS Code, verify that the required components are installed.

```bash
rdc vscode check
```

Checks your VS Code installation, Remote SSH extension, and SSH configuration. Follow the output to resolve any missing prerequisites, then connect with `rdc vscode <machine> [repo]`.

### Step 7: Check for CLI updates

```bash
rdc update --check-only
```

Reports whether a newer version of the CLI is available. To install the update, run `rdc update` without `--check-only`.

## Troubleshooting

**"rsync: command not found" during file sync**
Install rsync on both your local machine and the remote server. On Debian/Ubuntu: `sudo apt install rsync`. On macOS: rsync is included by default.

**"Permission denied" during sync upload**
Verify that your SSH user has write access to the repository mount directory. Repository mounts are owned by the user specified during machine registration.

**"VS Code Remote SSH extension not found"**
Install the extension from the VS Code marketplace: search for "Remote - SSH" by Microsoft. After installing, restart VS Code and run `rdc vscode check` again.

## Next Steps

You ran remote commands, synced files, checked VS Code integration, and verified CLI updates. To protect your data:

- [Tools](/en/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Networking](/en/docs/tutorial-backup) — backup scheduling and network configuration
- [Services](/en/docs/services) — Rediaccfile reference and service networking
