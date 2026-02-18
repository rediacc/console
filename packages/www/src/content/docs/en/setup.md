---
title: "Machine Setup"
description: "Create a context, add machines, provision servers, and configure infrastructure."
category: "Guides"
order: 3
language: en
---

# Machine Setup

This page walks you through setting up your first machine: creating a context, registering a server, provisioning it, and optionally configuring infrastructure for public access.

## Step 1: Create a Local Context

A **context** is a named configuration that stores your SSH credentials, machine definitions, and repository mappings. Think of it as a project workspace.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Required | Description |
|--------|----------|-------------|
| `--ssh-key <path>` | Yes | Path to your SSH private key. Tilde (`~`) is expanded automatically. |
| `--renet-path <path>` | No | Custom path to the renet binary on remote machines. Defaults to the standard install location. |

This creates a local context named `my-infra` and stores it in `~/.rediacc/config.json`.

> You can have multiple contexts (e.g., `production`, `staging`, `dev`). Switch between them with the `--context` flag on any command.

## Step 2: Add a Machine

Register your remote server as a machine in the context:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--ip <address>` | Yes | - | IP address or hostname of the remote server |
| `--user <username>` | Yes | - | SSH username on the remote server |
| `--port <port>` | No | `22` | SSH port |
| `--datastore <path>` | No | `/mnt/rediacc` | Path on the server where Rediacc stores encrypted repositories |

After adding the machine, rdc automatically runs `ssh-keyscan` to fetch the server's host keys. You can also run this manually:

```bash
rdc context scan-keys server-1
```

To view all registered machines:

```bash
rdc context machines
```

## Step 3: Set Up the Machine

Provision the remote server with all required dependencies:

```bash
rdc context setup-machine server-1
```

This command:
1. Uploads the renet binary to the server via SFTP
2. Installs Docker, containerd, and cryptsetup (if not present)
3. Creates the `rediacc` system user (UID 7111)
4. Creates the datastore directory and prepares it for encrypted repositories

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Datastore directory on the server |
| `--datastore-size <size>` | No | `95%` | How much of the available disk to allocate for the datastore |
| `--debug` | No | `false` | Enable verbose output for troubleshooting |

> Setup only needs to be run once per machine. It is safe to re-run if needed.

## Host Key Management

If a server's SSH host key changes (e.g., after reinstallation), refresh the stored keys:

```bash
rdc context scan-keys server-1
```

This updates the `knownHosts` field in your config for that machine.

## Test SSH Connectivity

Verify your machine is reachable before proceeding:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

This tests the SSH connection and reports:
- Connection status
- Authentication method used
- SSH key configuration
- Known hosts entry

You can save the verified host key to your machine config with `--save -m server-1`.

## Infrastructure Configuration

For machines that need to serve traffic publicly, configure infrastructure settings:

### Set Infrastructure

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Option | Description |
|--------|-------------|
| `--public-ipv4 <ip>` | Public IPv4 address for external access |
| `--public-ipv6 <ip>` | Public IPv6 address for external access |
| `--base-domain <domain>` | Base domain for applications (e.g., `example.com`) |
| `--cert-email <email>` | Email for Let's Encrypt TLS certificates |
| `--cf-dns-token <token>` | Cloudflare DNS API token for ACME DNS-01 challenges |
| `--tcp-ports <ports>` | Comma-separated additional TCP ports to forward (e.g., `25,143,465,587,993`) |
| `--udp-ports <ports>` | Comma-separated additional UDP ports to forward (e.g., `53`) |

### View Infrastructure

```bash
rdc context show-infra server-1
```

### Push to Server

Generate and deploy the Traefik reverse proxy configuration to the server:

```bash
rdc context push-infra server-1
```

This pushes the proxy configuration based on your infra settings. Traefik handles TLS termination, routing, and port forwarding.

## Setting Defaults

Set default values so you don't need to specify them on every command:

```bash
rdc context set machine server-1    # Default machine
rdc context set team my-team        # Default team (cloud mode, experimental)
```

After setting a default machine, you can omit `-m server-1` from commands:

```bash
rdc repo create my-app --size 10G   # Uses default machine
```

## Multiple Contexts

Manage multiple environments with named contexts:

```bash
# Create separate contexts
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# Use a specific context
rdc repo list -m server-1 --context production
rdc repo list -m staging-1 --context staging
```

View all contexts:

```bash
rdc context list
```

Show current context details:

```bash
rdc context show
```
