---
title: "rdc vs renet"
description: "When to use rdc and when to use renet."
category: "Concepts"
order: 1
language: en
---

# rdc vs renet

Rediacc has two binaries. Here is when to use each one.

| | rdc | renet |
|---|-----|-------|
| **Runs on** | Your workstation | The remote server |
| **Connects via** | SSH | Runs locally with root |
| **Used by** | Everyone | Advanced debugging only |
| **Install** | You install it | `rdc` provisions it automatically |

> For day-to-day work, use `rdc`. You rarely need `renet` directly.

## How They Work Together

`rdc` connects to your server over SSH and runs `renet` commands for you. You type a single command on your workstation, and `rdc` handles the rest:

1. Reads your local config (`~/.rediacc/rediacc.json`)
2. Connects to the server over SSH
3. Updates the `renet` binary if needed
4. Runs the matching `renet` operation on the server
5. Returns the result to your terminal

## Use `rdc` for Normal Work

All common tasks go through `rdc` on your workstation:

```bash
# Set up a new server
rdc config setup-machine server-1

# Create and start a repository
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Stop a repository
rdc repo down my-app -m server-1

# Check machine health
rdc machine health server-1
```

See the [Quick Start](/en/docs/quick-start) for a full walkthrough.

## Use `renet` for Server-Side Debugging

You only need `renet` directly when you SSH into a server for:

- Emergency debugging when `rdc` cannot connect
- Checking system internals not available through `rdc`
- Low-level recovery operations

All `renet` commands need root privileges (`sudo`). See [Server Reference](/en/docs/server-reference) for the full list of `renet` commands.

## Experimental: `rdc ops` (Local VMs)

`rdc ops` wraps `renet ops` for managing local VM clusters on your workstation:

```bash
rdc ops setup              # Install prerequisites (KVM or QEMU)
rdc ops up --basic         # Start a minimal cluster
rdc ops status             # Check VM status
rdc ops ssh 1              # SSH into bridge VM
rdc ops ssh 1 hostname     # Run a command on bridge VM
rdc ops down               # Destroy cluster
```

> Requires the local adapter. Not available with the cloud adapter.

These commands run `renet` locally (not over SSH). See [Experimental VMs](/en/docs/experimental-vms) for full documentation.

## Rediaccfile Note

You may see `renet compose -- ...` inside a `Rediaccfile`. That is normal — Rediaccfile functions run on the server where `renet` is available.

From your workstation, start and stop workloads with `rdc repo up` and `rdc repo down`.
