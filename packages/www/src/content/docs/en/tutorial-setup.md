---
title: "Machine Setup"
description: "Watch and follow along as we create a config, add a machine, test connectivity, run diagnostics, and configure infrastructure."
category: "Tutorials"
order: 2
language: en
---

# Tutorial: Machine Setup

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## Prerequisites

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Interactive Recording

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## What You'll See

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Step 1: Create a new config

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### Step 2: View configs

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Step 3: Add a machine

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### Step 4: View machines

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Step 5: Set default machine

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

Sets a default machine so you can omit `-m bridge-vm` from subsequent commands.

### Step 6: Test connectivity

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### Step 7: Run diagnostics

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### Step 8: Configure infrastructure

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Sets the infrastructure configuration for public-facing services. After setting infra, view the configuration:

```bash
rdc config show-infra bridge-vm
```

Deploy the generated Traefik proxy config to the server with `rdc config push-infra bridge-vm`.

## Next Steps

- [Machine Setup](/en/docs/setup) — full reference for all config and setup commands
- [Quick Start](/en/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/en/docs/tutorial-repos) — create, deploy, and manage repositories
