---
title: "Subscription & Licensing"
description: "Activate a subscription, issue machine licenses, and manage plan enforcement in local deployments."
category: "Guides"
order: 7
language: en
---

# Subscription & Licensing

Machines running in local deployments need a subscription license to enforce plan-based resource limits. The CLI delivers signed license blobs directly to each machine — no cloud API connection required after initial activation.

## Overview

The licensing flow has four steps:

1. Create an API token in the account web portal
2. Login on the machine with `rdc subscription login`
3. Activate the machine with `rdc subscription activate`
4. Licenses auto-refresh in the background during normal CLI usage

Licenses are short-lived (1 hour), Ed25519-signed blobs that the CLI refreshes automatically. A 3-day grace period ensures continuity if a check-in is temporarily missed.

## Step 1: Get an API Token

Log into the account portal at `https://account.rediacc.com`. Navigate to your subscription settings and create an API token with the following scopes:

- `license:read` — check subscription and license status
- `license:activate` — activate machines and issue licenses

Copy the token — it is only shown once.

## Step 2: Login

```bash
rdc subscription login --token <your-token>
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `-t, --token <token>` | No | - | API token. Prompts interactively if omitted. |
| `--server <url>` | No | `https://account.rediacc.com` | Account server URL |

This validates the token against the account server and stores it locally at `~/.config/rediacc/api-token.json`. On success, it displays your plan name and machine quota.

## Step 3: Activate

```bash
rdc subscription activate
```

This reads the machine's hardware ID, calls the account server to issue a license, and stores it at `/var/lib/rediacc/license/license.json`. If the CLI cannot write to that path directly, it will retry with `sudo`.

Each activation consumes one machine slot in your subscription. To free a slot, deactivate a machine from the account portal.

## Checking Status

```bash
rdc subscription status
```

Shows both local license info and remote subscription details:

- **Local**: plan, status, machine ID, issued/expiry times, sequence number
- **Remote**: plan, subscription status, active machines and their last-seen timestamps

## Refreshing a License

```bash
rdc subscription refresh
```

Manually reissues the license for this machine. This is normally not needed — see auto-refresh below.

## Auto-Refresh

Every CLI command automatically checks the local license age. If the license is older than 50 minutes, it refreshes in the background without blocking the command. No user action is required.

If the machine is offline, the current license remains valid until its 1-hour expiry. After that, the grace period begins.

## Grace Period & Degradation

If a license expires and cannot be refreshed within the 3-day grace period, the machine's resource limits degrade to Community plan defaults. Once the license is refreshed (by restoring connectivity and running any `rdc` command), the original plan limits are restored immediately.

## Plan Limits

### Machine Limits

| Plan | Max Machines |
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
| Repository size (GB) | 10 | 100 | 500 | 1,024 |
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
