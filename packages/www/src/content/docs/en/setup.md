---
title: "Machine Setup"
description: "Create a config, add machines, provision servers, and configure infrastructure."
category: "Guides"
order: 3
language: en
---

# Machine Setup

This page walks you through setting up your first machine: creating a config, registering a server, provisioning it, and optionally configuring infrastructure for public access.

## Step 1: Create a Config

A **config** is a named configuration file that stores your SSH credentials, machine definitions, and repository mappings. Think of it as a project workspace.

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| Option | Required | Description |
|--------|----------|-------------|
| `--ssh-key <path>` | Yes | Path to your SSH private key. Tilde (`~`) is expanded automatically. |
| `--renet-path <path>` | No | Custom path to the renet binary on remote machines. Defaults to the standard install location. |

This creates a config named `my-infra` and stores it in `~/.config/rediacc/my-infra.json`. The default config (when no name is given) is stored as `~/.config/rediacc/rediacc.json`.

> You can have multiple configs (e.g., `production`, `staging`, `dev`). Switch between them with the `--config` flag on any command.

## Step 2: Add a Machine

Register your remote server as a machine in the config:

```bash
rdc config machine add server-1 --ip 203.0.113.50 --user deploy
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--ip <address>` | Yes | - | IP address or hostname of the remote server |
| `--user <username>` | Yes | - | SSH username on the remote server |
| `--port <port>` | No | `22` | SSH port |
| `--datastore <path>` | No | `/mnt/rediacc` | Path on the server where Rediacc stores encrypted repositories |

After adding the machine, rdc automatically runs `ssh-keyscan` to fetch the server's host keys. You can also run this manually:

```bash
rdc config machine scan-keys server-1
```

To view all registered machines:

```bash
rdc config machine list
```

## Step 3: Set Up the Machine

Provision the remote server with all required dependencies:

```bash
rdc config machine setup server-1
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
rdc config machine scan-keys server-1
```

This updates the `knownHosts` field in your config for that machine.

## Test SSH Connectivity

After adding a machine, verify it's reachable:

```bash
rdc term server-1 -c "hostname"
```

This opens an SSH connection to the machine and runs the command. If it succeeds, your SSH configuration is correct.

For more detailed diagnostics, run:

```bash
rdc doctor
```

> **Cloud adapter only**: The `rdc machine test-connection` command provides detailed SSH diagnostics but requires the cloud adapter. For the local adapter, use `rdc term` or `ssh` directly.

## Infrastructure Configuration

For machines that need to serve traffic publicly, configure infrastructure settings:

### Set Infrastructure

```bash
rdc config infra set server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Option | Scope | Description |
|--------|-------|-------------|
| `--public-ipv4 <ip>` | Machine | Public IPv4 address — proxy entrypoints are only created for configured address families |
| `--public-ipv6 <ip>` | Machine | Public IPv6 address — proxy entrypoints are only created for configured address families |
| `--base-domain <domain>` | Machine | Base domain for applications (e.g., `example.com`) |
| `--cert-email <email>` | Config | Email for Let's Encrypt TLS certificates (shared across machines) |
| `--cf-dns-token <token>` | Config | Cloudflare DNS API token for ACME DNS-01 challenges (shared across machines) |
| `--tcp-ports <ports>` | Machine | Comma-separated additional TCP ports to forward (e.g., `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | Comma-separated additional UDP ports to forward (e.g., `53`) |

Machine-scoped options are stored per-machine. Config-scoped options (`--cert-email`, `--cf-dns-token`) are shared across all machines in the config — set them once and they apply everywhere.

### View Infrastructure

```bash
rdc config infra show server-1
```

### Push to Server

Generate and deploy the Traefik reverse proxy configuration to the server:

```bash
rdc config infra push server-1
```

This command:
1. Deploys the renet binary to the remote machine
2. Configures Traefik reverse proxy, router, and systemd services
3. Creates Cloudflare DNS records for the machine subdomain (`server-1.example.com` and `*.server-1.example.com`) if `--cf-dns-token` is set

The DNS step is automatic and idempotent — it creates missing records, updates records with changed IPs, and skips records that are already correct. If no Cloudflare token is configured, DNS is skipped with a warning. Per-repo wildcard DNS records (for auto-routes) are created automatically when you run `rdc repo up`.

## Cloud Provisioning

Instead of manually creating VMs, you can configure a cloud provider and let `rdc` provision machines automatically using [OpenTofu](https://opentofu.org/).

### Prerequisites

Install OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Ensure your SSH config includes a public key:

```bash
rdc config set ssh.privateKeyPath ~/.ssh/id_ed25519
```

### Add a Cloud Provider

```bash
rdc config provider add my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Option | Required | Description |
|--------|----------|-------------|
| `--provider <source>` | Yes* | Known provider source (e.g., `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Yes* | Custom OpenTofu provider source (for unknown providers) |
| `--token <token>` | Yes | API token for the cloud provider |
| `--region <region>` | No | Default region for new machines |
| `--type <type>` | No | Default instance type/size |
| `--image <image>` | No | Default OS image |
| `--ssh-user <user>` | No | SSH username (default: `root`) |

\* Either `--provider` or `--source` is required. Use `--provider` for known providers (built-in defaults). Use `--source` with additional `--resource`, `--ipv4-output`, `--ssh-key-attr` flags for custom providers.

### Provision a Machine

```bash
rdc machine provision prod-2 --provider my-linode
```

This single command:
1. Creates a VM on the cloud provider via OpenTofu
2. Waits for SSH connectivity
3. Registers the machine in your config
4. Installs renet and all dependencies
5. Configures Traefik proxy and Cloudflare DNS (auto-detects base domain from sibling machines, or pass `--base-domain` explicitly)

| Option | Description |
|--------|-------------|
| `--provider <name>` | Cloud provider name (from `add-provider`) |
| `--region <region>` | Override the provider's default region |
| `--type <type>` | Override the default instance type |
| `--image <image>` | Override the default OS image |
| `--base-domain <domain>` | Base domain for infrastructure. Auto-detected from sibling machines if not specified |
| `--no-infra` | Skip infrastructure configuration (proxy + DNS) entirely |
| `--debug` | Show detailed provisioning output |

### Deprovision a Machine

```bash
rdc machine deprovision prod-2
```

Destroys the VM via OpenTofu and removes it from your config. Requires confirmation unless `--force` is used. Only works for machines created with `machine provision`.

### List Providers

```bash
rdc config provider list
```

## Setting Defaults

Set default values so you don't need to specify them on every command:

```bash
rdc config set machine server-1    # Default machine
rdc config set team my-team        # Default team (cloud adapter, experimental)
```

After setting a default machine, you can omit `-m server-1` from commands:

```bash
rdc repo create my-app --size 10G   # Uses default machine
```

## Multiple Configs

Manage multiple environments with named configs:

```bash
# Create separate configs
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# Use a specific config
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

View all configs:

```bash
rdc config list
```

Show current config details:

```bash
rdc config show
```
