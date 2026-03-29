---
title: Quick Start
description: Get a containerized service running on your server in minutes.
category: Guides
order: -1
language: en
---

# Quick Start

Deploy an encrypted, isolated container environment on your own server. No cloud accounts or SaaS dependencies. Everything runs on hardware you control.

---

## Introduction

### Key Concepts

A repo is a single encrypted file on disk. Move it, back it up, fork it. It's just a file. When mounted, it becomes a folder with a dedicated Docker daemon and your app data inside.

Think of a repo like a USB drive. It's something in your hand, and when you plug it in it becomes visible and accessible to the system. Your apps and data are completely portable. Plug & Run on any machine on any cloud provider.

**Two tools, two roles:**

- **rdc** = CLI on your laptop (TypeScript, installed globally)
- **renet** = orchestrator on the server (Go binary, manages daemons/networks/isolation)
- RDC provisions renet automatically during `config machine setup`. No manual setup on the server.

> [Architecture](/en/docs/architecture) explains the security model. [rdc vs renet](/en/docs/rdc-vs-renet) explains which tool to use when.

### 1. Install the CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Verify: Node, SSH key, renet, Docker
```

> Windows, Alpine, Arch: see [Installation](/en/docs/installation). Full system requirements: [Requirements](/en/docs/requirements).

### 2. SSH Key Setup

rdc connects over SSH. The server must trust your public key before rdc can reach it.

```bash
# Generate a key (skip if you already have one)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Copy public key to the server (will prompt for password)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Tell rdc which key to use
rdc config ssh set --key ~/.ssh/id_ed25519
```

Every rdc command now authenticates with this key. No passwords.

### 3. Add Your Server

```bash
rdc config machine add my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup my-server        # Provisions renet + creates datastore
```

**What happens:** SSH host key scanned, renet binary uploaded, encrypted datastore initialized on the server. Ready for repos.

> Datastore sizing, Ceph RBD, cloud providers: [Machine Setup](/en/docs/setup). SSH failures: [Troubleshooting](/en/docs/troubleshooting).

### 4. Config File

```bash
rdc config show                            # Human-readable summary
cat ~/.config/rediacc/rediacc.json         # Raw JSON: machines, repos, storages, SSH key
```

**One file = one environment.** Copy it to another laptop and you're ready.

---

## Working with a Repo

### 1. Create a Repo

```bash
rdc repo create my-app -m my-server --size 2G       # Create 2 GB encrypted repo
```

Creates the encrypted volume, mounts it, and starts its Docker daemon. The repo is registered in your config and ready for use.

> Resize, delete, validation: [Repositories](/en/docs/repositories).

### 2. Apply a Template

```bash
rdc repo template list                                        # Show embedded templates
rdc repo template apply app-postgres -m my-server -r my-app   # Deploy docker-compose.yml + Rediaccfile
```

Templates provide a `docker-compose.yml`, `Rediaccfile`, and supporting files. Without a template (or your own compose file), there is nothing to start.

### 3. Start the Repo

```bash
rdc repo up my-app -m my-server                      # Run Rediaccfile up()
rdc repo list -m my-server                           # See all repos on the machine
rdc repo status my-app -m my-server                  # Mount state, Docker, size, encryption
```

`repo up` auto-mounts if needed. No flags required.

### 4. VS Code

```bash
rdc vscode my-server my-app              # Opens VS Code SSH, lands inside the repo sandbox
```

You're editing files *inside* the encrypted volume. `docker ps` only shows this repo's containers. Save, compose up, iterate.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Where you run it** | Your laptop (CLI) | Inside VS Code sandbox |
| **What it does** | SSH → auto-mount → run Rediaccfile `up()` | Runs Rediaccfile `up()` directly |
| **Use case** | CI/CD, automation, remote ops | Developer inner loop |
| **Isolation** | Orchestrates from outside | Already inside the sandbox |

**Demo flow:** `rdc repo template apply` → `rdc vscode my-server my-app` → edit `docker-compose.yml` → `renet dev up` → see app running → iterate.

> Rediaccfile structure: [Services](/en/docs/services). When to use which tool: [rdc vs renet](/en/docs/rdc-vs-renet).

### 6. Isolation Model

- **Universal user** (`rediacc`): Same UID across every machine. Move a repo to another server and file ownership just works. No `chown` headaches.
- **Per-repo Docker daemon**: Each repo gets its own isolated Docker daemon. `docker ps` only shows THIS repo's containers.
- **Landlock + OverlayFS sandbox**: The VS Code shell is filesystem-restricted. You can't read other repos. Writes to `$HOME` are per-repo overlays.

> How isolation works: [Architecture](/en/docs/architecture). Rediaccfile lifecycle: [Services](/en/docs/services).

### 7. Terminal, Sync & Tunnel

**Terminal:**
```bash
rdc term my-server my-app                            # SSH into repo sandbox
rdc term my-server my-app -c "curl localhost:3000"   # Run command & exit
rdc term my-server                                   # SSH to machine (no sandbox)
```

**File Sync (rsync over SSH):**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src       # Push local files to repo
rdc repo sync download -m my-server -r my-app --local ./backup  # Pull repo files to local
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run  # Preview first
```

**Tunnel (SSH port-forwarding to container):**
```bash
rdc repo tunnel my-server my-app                     # Auto-detect container & port
rdc repo tunnel my-server my-app --port 5432         # Tunnel Postgres
rdc repo tunnel my-server my-app --port 5432 --local 15432  # Custom local port
```

Run tunnel → open `localhost:3000` in browser → live app from remote server.

> Sync, terminal, VS Code details: [Tools](/en/docs/tools).

---

## Fork & Backup

### 1. Grand & Fork Repos

```bash
rdc repo fork my-app -m my-server --tag experiment --up     # Instant CoW clone + start
rdc repo list -m my-server                                  # Shows: my-app (grand) + my-app:experiment (fork)
rdc repo delete my-app:experiment -m my-server              # Delete fork, grand untouched
```

**Instant, zero-copy clone.** CoW (copy-on-write). Microseconds, no data copied. Blocks are shared until one side writes.

**Use cases:**
- **AI / ML:** Fork production dataset, run experiment, discard or promote
- **DevOps:** Fork → test migration → delete if bad, promote if good
- **Backup:** Fork = instant snapshot, push it offsite

> Fork lifecycle, cross-machine forks: [Repositories](/en/docs/repositories).

### 2. Push to Another Machine

```bash
# Push repo to another machine
rdc repo push my-app -m my-server --to backup-server

# Push and auto-deploy on target
rdc repo push my-app -m my-server --to backup-server --up

# Push with CRIU checkpoint (live migration, preserves memory state)
rdc repo push my-app -m my-server --to new-server --checkpoint --up

# Push to a new machine (auto-provision via cloud provider)
rdc repo push my-app -m my-server --to new-server --provision linode --up
```

### 3. Push to Cloud Storage (OneDrive, Google Drive, S3)

```bash
# Import your rclone config as a storage backend
rdc config storage import ~/rclone.conf

# List available storages
rdc storage list

# Push repo to cloud storage
rdc repo push my-app -m my-server --to my-s3-backup

# List backups on storage
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` auto-detects whether the target is a machine or a storage backend. Works with any rclone-supported provider: S3, R2, B2, OneDrive, Google Drive, SFTP, etc.

### 4. Pull from Remote

```bash
# Pull repo from a cloud machine to your local server
rdc repo pull my-app -m my-local-server --from cloud-server

# Pull from cloud storage
rdc repo pull my-app -m my-local-server --from my-s3-backup

# Pull and start immediately
rdc repo pull my-app -m my-local-server --from my-s3-backup --up
```

**Why pull?** Your local machine is behind NAT. The cloud can't push to you. But you can reach the cloud. Pull brings the repo home.

**Full cycle:** Create on dev → push to cloud → pull on production → `--up`. One repo, any machine, any cloud.

> Scheduling, automated backups, restore: [Backup & Restore](/en/docs/backup-restore).

---

## Proxy & SSL

### 1. Infrastructure Config

```bash
rdc config infra set my-server           # Configure: base domain, public IPs, port ranges
rdc config infra show my-server          # Review configuration
rdc config infra push my-server          # Push proxy config to remote
```

**How routing works:**
- Traefik auto-discovers containers via `rediacc.service_name` and `rediacc.service_port` labels
- Routes: `{service}-{networkId}.{baseDomain}` → container IP:port
- SSL: Let's Encrypt via Cloudflare DNS-01 challenge (auto-renewal, wildcard certs)

### 2. Proxy Template

```bash
rdc repo template apply proxy -m my-server -r infra     # Deploy proxy into a repo
rdc repo up infra -m my-server                           # Start Traefik
```

Traefik now routes external traffic to all repos on this machine. Every container gets an HTTPS endpoint automatically.

```bash
# Navigate to https://my-app.example.com → routed to container
# TCP/UDP forwarding for databases:
#   rediacc.tcp_ports=3306,5432 → auto-allocated external ports
```

> Routing rules, DNS, TLS configuration: [Networking](/en/docs/networking).

---

## Next Steps

- **[Migration Guide](/en/docs/migration)** - Bring existing projects into Rediacc repositories
- **[Monitoring](/en/docs/monitoring)** - Machine health, containers, services, diagnostics
- **[CLI Reference](/en/docs/cli-application)** - Complete command reference
- **[Cheat Sheet](/en/docs/rdc-cheat-sheet)** - Quick command lookup
- **[Troubleshooting](/en/docs/troubleshooting)** - Solutions for common issues
- **[Rules of Rediacc](/en/docs/rules-of-rediacc)** - Rediaccfile best practices and deployment checklist
