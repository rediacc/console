---
title: "Machine Setup"
description: "Create a configuration profile, register a remote machine, verify SSH connectivity, and configure infrastructure settings."
category: "Tutorials"
order: 2
language: en
---

# How To Set Up a Machine with Rediacc

Every Rediacc deployment starts with a configuration profile and a registered machine. In this tutorial, you create a config, register a remote server, verify SSH connectivity, run environment diagnostics, and configure infrastructure networking. When you finish, your machine is ready for repository deployments.

## Prerequisites

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Interactive Recording

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

### Step 1: Create a new config

A configuration profile stores machine definitions, SSH credentials, and infrastructure settings. Create one for this environment.

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

This creates a named config file at `~/.config/rediacc/tutorial-demo.json`.

### Step 2: View configs

Verify the new profile appears in the config list.

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Step 3: Add a machine

Register a machine with its IP address and SSH user. The CLI automatically fetches and stores the server's host keys via `ssh-keyscan`.

```bash
rdc config machine add bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### Step 4: View machines

Confirm the machine was registered correctly.

```bash
rdc config machine list --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Step 5: Set default machine

Setting a default machine avoids repeating `-m bridge-vm` on every command.

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### Step 6: Test connectivity

Before deploying anything, verify the machine is reachable over SSH.

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Both commands run on the remote machine and return immediately. If either fails, check that your SSH key is correct and the server is reachable.

### Step 7: Run diagnostics

```bash
rdc doctor
```

Checks your local environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites. Each check reports **OK**, **Warning**, or **Error**.

### Step 8: Configure infrastructure

For public-facing services, the machine needs networking configuration — its external IP, a base domain, and a certificate email for TLS.

```bash
rdc config infra set bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Verify the configuration:

```bash
rdc config infra show bridge-vm
```

Deploy the generated Traefik proxy config to the server with `rdc config infra push bridge-vm`.

## Troubleshooting

**"SSH key not found" or "Permission denied (publickey)"**
Verify the key path passed to `config init` exists and matches the server's `authorized_keys`. Check permissions: the private key file must be `600` (`chmod 600 ~/.ssh/id_ed25519`).

**"Connection refused" on SSH commands**
Confirm the server is running and the IP is correct. Check that port 22 is open: `nc -zv <ip> 22`. If using a non-standard port, pass `--port` when adding the machine.

**"Host key verification failed"**
The stored host key doesn't match the server's current key. This happens after a server rebuild or IP reassignment. Run `rdc config machine scan-keys <machine>` to refresh the key.

## Next Steps

You created a configuration profile, registered a machine, verified connectivity, and configured infrastructure networking. To deploy applications:

- [Machine Setup](/en/docs/setup) — full reference for all config and setup commands
- [Tutorial: Repository Lifecycle](/en/docs/tutorial-repos) — create, deploy, and manage repositories
- [Quick Start](/en/docs/quick-start) — deploy a containerized application end-to-end
