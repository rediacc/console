---
title: "Repository Lifecycle"
description: "Create an encrypted repository, deploy a containerized application, inspect containers, and clean up."
category: "Tutorials"
order: 3
language: en
---

# How To Deploy and Manage Repositories with Rediacc

Repositories are the core deployment unit in Rediacc — each one is an isolated, encrypted environment with its own Docker daemon and dedicated storage. In this tutorial, you create an encrypted repository, deploy a containerized application, inspect running containers, and clean up. When you finish, you have completed a full deployment lifecycle.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/en/docs/tutorial-setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Interactive Recording

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

### Step 1: Create an encrypted repository

Each repository gets its own LUKS-encrypted storage volume. Specify the machine and storage size.

```bash
rdc repo create test-app -m server-1 --size 2G
```

Rediacc creates a 2 GB encrypted volume, formats it, and mounts it automatically. The repository is ready for file uploads.

### Step 2: List repositories

Confirm the new repository is available.

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Step 3: Inspect the mount path

Before deploying, verify the repository's storage is mounted and accessible.

```bash
rdc term server-1 -c "ls -la /mnt/rediacc/mounts/test-app/"
```

The mount directory is where application files live — `Rediaccfile`, `docker-compose.yml`, and any data volumes.

### Step 4: Start services

Deploy the application by mounting the repository and starting its Docker services.

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, and starts services via `up()`.

> **Note:** The first deployment takes longer as Docker images are downloaded. Subsequent starts reuse cached images.

### Step 5: View running containers

```bash
rdc machine containers server-1
```

Shows all running containers across all repositories on the machine, including CPU and memory usage.

### Step 6: Access the repository terminal

To run commands inside the repository's isolated Docker environment:

```bash
rdc term server-1 test-app -c "docker ps"
```

The terminal session sets `DOCKER_HOST` to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Step 7: Stop and clean up

When you're done, stop services, close the encrypted volume, and optionally delete the repository.

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

> **Warning:** `repo delete` is irreversible. All data in the repository is destroyed. Create a backup first if needed.

> **Note:** After deletion, the config entry is preserved (the repo may exist on other machines). Use `rdc config repository remove <name>` to remove it, or `--archive-config` to preserve credentials for recovery.

## Troubleshooting

**"Insufficient disk space" during repository creation**
The encrypted volume needs contiguous free space on the host. Check available space with `df -h` on the server. Consider a smaller `--size` value or freeing disk space.

**Docker image pull timeout during `repo up`**
Large images may time out on slow connections. Retry with `rdc repo up` — it resumes where it left off. For air-gapped environments, pre-load images into the repository's Docker daemon.

**"Mount failed" or "LUKS open failed"**
The LUKS passphrase is derived from the config. Verify you're using the same config that created the repository. If the volume is already mounted by another process, unmount it first.

## Next Steps

You created an encrypted repository, deployed an application, inspected containers, and cleaned up. To monitor your deployments:

- [Services](/en/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring & Diagnostics](/en/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/en/docs/tools) — terminal, file sync, and VS Code integration
