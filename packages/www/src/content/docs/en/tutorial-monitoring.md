---
title: "Monitoring & Diagnostics"
description: "Watch and follow along as we check machine health, inspect containers, review services, and run diagnostics."
category: "Tutorials"
order: 4
language: en
---

# Tutorial: Monitoring & Diagnostics

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/en/docs/tutorial-repos))

## Interactive Recording

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## What You'll See

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Step 1: Run diagnostics

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Step 2: Machine health check

```bash
rdc machine health server-1
```

Fetches a comprehensive health report including system uptime, disk usage, datastore usage, container counts, storage SMART status, and any identified issues.

### Step 3: View running containers

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Step 4: Check systemd services

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

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### Step 7: Verify connectivity

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## Next Steps

- [Monitoring](/en/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/en/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/en/docs/tutorial-tools) — terminal, file sync, and VS Code integration
