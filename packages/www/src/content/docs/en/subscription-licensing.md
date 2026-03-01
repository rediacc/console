---
title: "Subscription & Licensing"
description: "Manage subscriptions and machine licenses for local deployments."
category: "Guides"
order: 7
language: en
---

# Subscription & Licensing

Machines running in local deployments need a subscription license to enforce plan-based resource limits. The CLI automatically delivers signed license blobs to remote machines via SSH — no manual activation or cloud connection required from the server side.

## Overview

1. Login with `rdc subscription login` (opens browser for authentication)
2. Use any machine command — licenses are handled automatically

When you run a command targeting a machine (`rdc machine info`, `rdc repo up`, etc.), the CLI automatically checks if the machine has a valid license. If not, it fetches one from the account server and delivers it via SSH.

## Login

```bash
rdc subscription login
```

Opens a browser for authentication via the device code flow. After approval, the CLI stores an API token locally at `~/.config/rediacc/api-token.json`.

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `-t, --token <token>` | No | - | API token (skips browser flow) |
| `--server <url>` | No | `https://account.rediacc.com` | Account server URL |

## Checking Status

```bash
# Account-level status (plan, machines)
rdc subscription status

# Include license details from a specific machine
rdc subscription status -m hostinger
```

Shows subscription details from the account server. With `-m`, also SSHes to the machine and displays its current license info.

## Force-Refreshing a License

```bash
rdc subscription refresh -m <machine>
```

Force re-issues and delivers a fresh license to the specified machine. This is normally not needed — licenses are refreshed automatically every 50 minutes during normal CLI usage.

## How It Works

1. **Login** stores an API token on your workstation
2. **Any machine command** triggers an automatic license check via SSH
3. If the remote license is missing or older than 50 minutes, the CLI:
   - Reads the remote machine's hardware ID via SSH
   - Calls the account API to issue a new license
   - Delivers both the machine license and subscription blob to the remote via SSH
4. A 50-minute in-memory cache prevents redundant SSH round-trips within the same session

Each machine activation consumes one slot in your subscription. To free a slot, deactivate a machine from the account portal.

## Grace Period & Degradation

If a license expires and cannot be refreshed within the 3-day grace period, the machine's resource limits degrade to Community plan defaults. Once the license is refreshed (by restoring connectivity and running any `rdc` command), the original plan limits are restored immediately.

## Plan Limits

### Floating License Limits

| Plan | Floating Licenses |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### Resource Limits

| Resource | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|
| Bridges | 0 | 1 | 2 | 10 |
| Max reserved jobs | 1 | 2 | 3 | 5 |
| Job timeout (hours) | 2 | 24 | 72 | 96 |
| Repository size (GB) | 10 | 100 | 500 | 2,048 |
| Jobs per month | 500 | 5,000 | 20,000 | 100,000 |
| Pending per user | 5 | 10 | 20 | 50 |
| Tasks per machine | 1 | 2 | 3 | 5 |

### Feature Availability

| Feature | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| Permission groups | - | Yes | Yes | Yes |
| Queue priority | - | - | Yes | Yes |
| Advanced analytics | - | - | Yes | Yes |
| Priority support | - | Yes | Yes | Yes |
| Audit log | - | Yes | Yes | Yes |
| Advanced queue | - | - | Yes | Yes |
| Custom branding | - | Yes | Yes | Yes |
| Dedicated account | - | - | - | Yes |
