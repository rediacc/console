---
title: "Backup & Networking"
description: "Watch and follow along as we configure backup schedules, storage providers, and network infrastructure."
category: "Tutorials"
order: 6
language: en
---

# Tutorial: Backup & Networking

This tutorial covers backup scheduling, storage configuration, and infrastructure networking setup: the commands you use to protect data and expose services.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/en/docs/tutorial-setup))

## Interactive Recording

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

## What You'll See

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Step 1: View current storages

```bash
rdc config storages
```

Lists all configured storage providers (S3, B2, Google Drive, etc.) imported from rclone configs. Storages are used as backup destinations.

### Step 2: Configure backup schedule

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Sets an automated backup schedule: push all repositories to the `my-s3` storage every day at 2 AM. The schedule is stored in your config and can be deployed to machines as a systemd timer.

### Step 3: View backup schedule

```bash
rdc backup schedule show
```

Shows the current backup schedule configuration: destination, cron expression, and enabled status.

### Step 4: Configure infrastructure

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Configures the machine's public networking: its external IP, base domain for auto-routes, and email for Let's Encrypt TLS certificates.

### Step 5: Add TCP/UDP ports

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Registers additional TCP/UDP ports for the reverse proxy. These create Traefik entrypoints (`tcp-25`, `udp-53`, etc.) that can be referenced in Docker labels.

### Step 6: View infrastructure config

```bash
rdc config show-infra server-1
```

Displays the full infrastructure configuration for a machine: public IPs, domain, email, and registered ports.

### Step 7: Disable backup schedule

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

Disables the automated backup schedule. The configuration is preserved so it can be re-enabled later.

## Next Steps

- [Backup & Restore](/en/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/en/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/en/docs/tutorial-setup) — initial configuration and provisioning
