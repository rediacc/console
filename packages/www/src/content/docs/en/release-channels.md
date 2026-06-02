---
title: "Release Channels"
description: "How Edge and Stable differ, and which channel to run."
category: "Concepts"
order: 2
language: en
---

Rediacc ships updates through two channels: **Stable** and **Edge**. They run on separate infrastructure and carry different trade-offs.

## Stable Channel

Stable is the default. A release reaches it only after sitting on Edge for 7 days with no reported issues.

- Recommended when you prefer a conservative upgrade cadence and want access to paid plans
- Deployed after 7 days of testing on Edge
- Hotfixes can be pushed directly when critical
- Domains: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge Channel

Edge picks up every change the moment it merges to main. It is the live version of the software, deployed continuously.

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

Run Edge on the Community plan and your resource limits double, at no extra cost:

| Resource | Stable Community | Edge Community |
|---|---|---|
| Repository size | 10 GB | 20 GB |
| License issuances per month | 500 | 1,000 |
| Machine activations | 2 | 4 |

Need higher limits or paid features? Create your account on Stable and upgrade there.

## Separate Accounts

Edge and Stable run on separate infrastructure with separate databases. An account on one does not exist on the other, and there is no migration path. Start on Edge, later decide you want a paid plan, and you will create a fresh account on Stable from scratch.

## How Promotions Work

1. Every merge to the main branch deploys to Edge immediately.
2. After 7 days without issues, Edge is promoted to Stable automatically.
3. Critical hotfixes can be pushed to both channels simultaneously.

So Stable trails Edge by at most 7 days. The soak window catches regressions on Edge before they ever reach Stable.

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

See [Installation](/en/docs/installation) for the install commands, package manager configuration, and Docker tags for each channel.

## CLI Channel Management

The CLI uses whichever channel you configured at install or login. To switch:

```bash
rdc update --channel edge      # Switch to Edge
rdc update --channel stable    # Switch to Stable
```

Run `rdc subscription login` and pick an Edge region, and the CLI sets the Edge update channel for you. No `--channel` flag required.
