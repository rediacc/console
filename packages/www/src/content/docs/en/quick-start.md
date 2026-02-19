---
title: "Quick Start"
description: "Get a containerized service running on your server in 5 minutes."
category: "Guides"
order: -1
language: en
translationPending: true
translationPendingReason: "English content changed in this PR; locale sync tracked in follow-up translation update"
---

# Quick Start

Deploy an encrypted, isolated container environment on your own server in 5 minutes. This guide uses **local mode** — no cloud accounts or SaaS dependencies.

## Prerequisites

- A Linux or macOS workstation
- A remote server (Ubuntu 24.04+, Debian 12+, or Fedora 43+) with SSH access and sudo privileges
- An SSH key pair (e.g., `~/.ssh/id_ed25519`)

## 1. Install the CLI

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. Create a Context

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. Add Your Server

```bash
rdc context add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. Provision the Server

```bash
rdc context setup-machine server-1
```

This installs Docker, cryptsetup, and the renet binary on your server.

## 5. Create an Encrypted Repository

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. Deploy Services

Mount the repository, create your `docker-compose.yml` and `Rediaccfile` inside it, then start:

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. Verify

```bash
rdc machine containers server-1
```

You should see your containers running.

## What is Rediacc?

Rediacc deploys containerized services on remote servers you control. Everything is encrypted at rest using LUKS, every repository gets its own isolated Docker daemon, and all orchestration happens over SSH from your workstation.

No cloud accounts. No SaaS dependencies. Your data stays on your servers.

## Next Steps

- **[Architecture](/en/docs/architecture)** — Understand how Rediacc works: modes, security model, Docker isolation
- **[rdc vs renet](/en/docs/rdc-vs-renet)** — Understand which CLI to use for daily operations vs low-level remote work
- **[Machine Setup](/en/docs/setup)** — Detailed setup guide: contexts, machines, infrastructure configuration
- **[Repositories](/en/docs/repositories)** — Create, manage, resize, fork, and validate repositories
- **[Services](/en/docs/services)** — Rediaccfiles, service networking, deployment, autostart
- **[Backup & Restore](/en/docs/backup-restore)** — Back up to external storage and schedule automated backups
- **[Monitoring](/en/docs/monitoring)** — Machine health, containers, services, diagnostics
- **[Tools](/en/docs/tools)** — File sync, SSH terminal, VS Code integration
- **[Migration Guide](/en/docs/migration)** — Bring existing projects into Rediacc repositories
- **[Troubleshooting](/en/docs/troubleshooting)** — Solutions for common issues
- **[CLI Reference](/en/docs/cli-application)** — Complete command reference
