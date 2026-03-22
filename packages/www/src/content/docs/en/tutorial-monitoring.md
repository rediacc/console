---
title: "Monitoring & Diagnostics"
description: "Check machine health, inspect containers, review systemd services, scan host keys, and run environment diagnostics."
category: "Tutorials"
order: 4
language: en
---

# How To Monitor and Diagnose Infrastructure with Rediacc

Keeping infrastructure healthy requires visibility into machine state, container status, and service health. In this tutorial, you run environment diagnostics, check machine health, inspect containers and services, review vault status, and verify connectivity. When you finish, you know how to identify and investigate issues across your infrastructure.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/en/docs/tutorial-repos))

## Interactive Recording

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

### Step 1: Run diagnostics

Start by checking your local environment for any configuration issues.

```bash
rdc doctor
```

Checks Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Step 2: Machine health check

```bash
rdc machine health server-1
```

Fetches a comprehensive health report from the remote machine: system uptime, disk usage, datastore usage, container counts, storage SMART status, and any identified issues.

### Step 3: View running containers

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Step 4: Check systemd services

To see the underlying services that power each repository's Docker daemon and networking:

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### Step 5: Vault status overview

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### Step 6: Scan host keys

If a machine was rebuilt or its IP changed, refresh the stored SSH host key.

```bash
rdc config machine scan-keys server-1
```

Fetches the server's current host keys and updates your config. This prevents "host key verification failed" errors.

### Step 7: Verify connectivity

A quick SSH connectivity check to confirm the machine is reachable and responding.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

The hostname confirms you're connected to the right server. The uptime confirms the system is running normally.

## Troubleshooting

**Health check times out or shows "SSH connection failed"**
Verify the machine is online and reachable: `ping <ip>`. Check that your SSH key is configured correctly with `rdc term <machine> -c "echo ok"`.

**"Service not found" in service listing**
Rediacc services only appear after at least one repository has been deployed. If no repositories exist, the service list is empty.

**Container listing shows stale or stopped containers**
Containers from previous deployments may linger if `repo down` was not run cleanly. Stop them with `rdc repo down <repo> -m <machine>` or inspect directly via `rdc term <machine> <repo> -c "docker ps -a"`.

## Next Steps

You ran diagnostics, checked machine health, inspected containers and services, and verified connectivity. To work with your deployments:

- [Monitoring](/en/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/en/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/en/docs/tutorial-tools) — terminal, file sync, and VS Code integration
