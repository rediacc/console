---
title: "Backup & Networking"
description: "Configure automated backup schedules, manage storage providers, set up infrastructure networking, and register service ports."
category: "Tutorials"
order: 6
language: en
---

# How To Configure Backups and Networking with Rediacc

Automated backups protect your repositories, and infrastructure networking exposes services to the outside world. In this tutorial, you configure backup schedules with storage providers, set up public networking with TLS certificates, register service ports, and verify the configuration. When you finish, your machine is ready for production traffic.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/en/docs/tutorial-setup))

## Interactive Recording

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### Step 1: View current storages

Storage providers (S3, B2, Google Drive, etc.) serve as backup destinations. Check which providers are configured.

```bash
rdc config storages
```

Lists all configured storage providers imported from rclone configs. If empty, add a storage provider first — see [Backup & Restore](/en/docs/backup-restore).

### Step 2: Configure backup schedule

Set up automated backups that run on a cron schedule.

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
```

You can configure multiple destinations with different schedules:

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

This schedules daily backups at 2 AM to `my-s3` and at 6 AM to `azure-backup`. Each destination gets its own schedule. The schedules are stored in your config and can be deployed to machines as systemd timers.

### Step 3: View backup schedule

Verify the schedule was applied.

```bash
rdc config backup-strategy show
```

Shows the current backup configuration: destination, cron expression, and enabled status.

### Step 4: Configure infrastructure

For public-facing services, the machine needs its external IP, base domain, and a certificate email for Let's Encrypt TLS.

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediacc generates a Traefik reverse proxy configuration from these settings.

### Step 5: Add TCP/UDP ports

If your services need non-HTTP ports (e.g., SMTP, DNS), register them as Traefik entrypoints.

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

This creates Traefik entrypoints (`tcp-25`, `udp-53`, etc.) that Docker services can reference via labels.

### Step 6: View infrastructure config

Verify the full infrastructure configuration.

```bash
rdc config show-infra server-1
```

Displays public IPs, domain, certificate email, and all registered ports.

### Step 7: Disable backup schedule

To stop automated backups without removing the configuration:

```bash
rdc config backup-strategy set --disable
rdc config backup-strategy show
```

The configuration is preserved and can be re-enabled later with `--enable`.

## Troubleshooting

**"Invalid cron expression"**
Cron format is `minute hour day month weekday`. Common schedules: `0 2 * * *` (daily 2 AM), `0 */6 * * *` (every 6 hours), `0 0 * * 0` (weekly Sunday midnight).

**"Storage destination not found"**
The destination name must match a configured storage provider. Run `rdc config storages` to see available names. Add new providers via rclone configuration.

**"Infrastructure config incomplete" when deploying**
All three fields are required: `--public-ipv4`, `--base-domain`, and `--cert-email`. Run `rdc config show-infra <machine>` to check which fields are missing.

## Next Steps

You configured automated backups, set up infrastructure networking, registered service ports, and verified the configuration. To manage backups:

- [Backup & Restore](/en/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/en/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/en/docs/tutorial-setup) — initial configuration and provisioning
