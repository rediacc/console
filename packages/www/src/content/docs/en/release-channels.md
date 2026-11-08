---
title: "Release Channels"
description: "How Edge and Stable differ, and which channel to run."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: en
---

Rediacc ships CLI updates through two channels: **Stable** and **Edge**. Both connect to the same product, so an account, its plan and its limits are identical on either one. The channels differ only in how soon a release reaches you.

## Stable Channel

Stable is the default. A release reaches it only after sitting on Edge for 7 days with no reported issues.

- Recommended when you prefer a conservative upgrade cadence
- Deployed after 7 days of testing on Edge
- Hotfixes can be pushed directly when critical

## Edge Channel

Edge picks up every change the moment it merges to main. It is the live version of the software, deployed continuously.

- Released on every merge to main
- Same accounts, plans and limits as Stable
- Best for trying new features early

## One Product, Two Channels

Your account lives in your data region on `eu.rediacc.cloud`, `us.rediacc.cloud` or `asia.rediacc.cloud`, whichever channel you run. Switching channels never touches your account, your data or your subscription. For regions, see [Data Regions](/en/docs/data-regions).

## Comparison

| | Stable | Edge |
|---|---|---|
| **Deploy cadence** | After 7-day soak | Every merge to main |
| **Stability** | Tested for 7 days | Production, continuously deployed |
| **Plans and limits** | Same | Same |
| **Account and data** | Shared | Shared |
| **Best for** | Production, paid workloads | Early access, evaluation |

## How Promotions Work

1. Every merge to the main branch is released to Edge immediately.
2. After 7 days without issues, Edge is promoted to Stable automatically.
3. Critical hotfixes can be pushed to both channels simultaneously.

So Stable trails Edge by at most 7 days. The soak window catches regressions on Edge before they ever reach Stable.

## Which Channel Should I Choose?

**Choose Stable if:**
- You prefer a conservative upgrade cadence with a 7-day soak window
- You prefer maximum reliability over latest features

**Choose Edge if:**
- You want to try new features early
- You are evaluating the platform
- You are comfortable with newer, less-tested code

## Installation

See [Installation](/en/docs/installation) for the install commands, package manager configuration, and Docker tags for each channel.

## CLI Channel Management

The CLI uses whichever channel you configured at install. To switch:

```bash
rdc update --channel edge      # Switch to Edge
rdc update --channel stable    # Switch to Stable
```
