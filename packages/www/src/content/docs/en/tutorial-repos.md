---
title: "Repository Lifecycle"
description: "Watch and follow along as we create an encrypted repository, deploy a containerized app, inspect containers, and clean up."
category: "Tutorials"
order: 3
language: en
---

# Tutorial: Repository Lifecycle

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/en/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Interactive Recording

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## What You'll See

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Step 1: Create an encrypted repository

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### Step 2: List repositories

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Step 3: Upload application files

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### Step 4: Start services

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### Step 5: View running containers

```bash
rdc machine containers server-1
```

Shows all running containers across all repositories on the machine, including CPU and memory usage.

### Step 6: Access the repo via terminal

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### Step 7: Stop and clean up

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## Next Steps

- [Services](/en/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/en/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/en/docs/tools) — terminal, file sync, and VS Code integration
