---
title: "Release Channels"
description: "Understanding Edge and Stable release channels, their differences, and how to choose."
category: "Concepts"
order: 2
language: en
---

Rediacc publishes updates through two release channels: **Stable** and **Edge**. Each channel serves a different audience and comes with different trade-offs.

## Stable Channel

Stable is the default channel for all users. Releases are promoted from Edge after a 7-day soak period with no reported issues.

- Recommended when you prefer a conservative upgrade cadence and want access to paid plans
- Deployed after 7 days of testing on Edge
- Hotfixes can be pushed directly when critical
- Domains: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge Channel

Edge receives every change immediately after it merges to main. It is the latest version of the software, deployed continuously.

- Continuously deployed production, released on every merge to main
- 2X Community plan limits (see table below)
- Free forever. No paid plans available on Edge.
- Separate accounts from Stable. Data does not transfer between channels.
- Domains: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Comparison

| | Stable | Edge |
|---|---|---|
| **Deploy cadence** | After 7-day soak | Every merge to main |
| **Stability** | Tested for 7 days | Production, continuously deployed |
| **Community plan limits** | 10 GB repos, 500 issuances/month, 2 machines | 20 GB repos, 1,000 issuances/month, 4 machines |
| **Paid plans** | Available (Professional, Business, Enterprise) | Not available |
| **Accounts** | Independent | Independent (separate from Stable) |
| **Best for** | Production, paid workloads | Production, side projects, early access |

## Edge 2X Limits

Edge users on the Community plan receive doubled resource limits at no cost:

| Resource | Stable Community | Edge Community |
|---|---|---|
| Repository size | 10 GB | 20 GB |
| License issuances per month | 500 | 1,000 |
| Machine activations | 2 | 4 |

If you need higher limits or paid plan features, create an account on the Stable channel and upgrade there.

## Separate Accounts

Edge and Stable run on separate infrastructure with separate databases. An account created on Edge does not exist on Stable, and vice versa. There is no migration path between channels. If you start on Edge and later want a paid plan, you will need to create a new account on Stable.

## How Promotions Work

1. Every merge to the main branch deploys to Edge immediately.
2. After 7 days without issues, Edge is promoted to Stable automatically.
3. Critical hotfixes can be pushed to both channels simultaneously.

This means Stable is always at most 7 days behind Edge. The soak period catches regressions before they propagate from Edge to Stable.

## Which Channel Should I Choose?

**Choose Stable if:**
- You prefer a conservative upgrade cadence with a 7-day soak window
- You need paid plans (Professional, Business, Enterprise)
- You prefer maximum reliability over latest features

**Choose Edge if:**
- You want to try new features early
- You are evaluating the platform
- You want generous free limits for side projects
- You are comfortable with newer, less-tested code

## Installation

See [Installation](/en/docs/installation) for commands to install from either channel, including package manager configuration and Docker tags.

## CLI Channel Management

The CLI automatically uses the channel configured during installation or login. To switch channels:

```bash
rdc update --channel edge      # Switch to Edge
rdc update --channel stable    # Switch to Stable
```

When you run `rdc subscription login` and select an Edge region, the CLI automatically configures the Edge update channel. No manual `--channel` flag is needed.
