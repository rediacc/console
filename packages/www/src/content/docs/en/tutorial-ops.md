---
title: "Local VM Provisioning"
description: "Watch and follow along as we provision a local VM cluster, run commands over SSH, and tear it down — all from the rdc CLI."
category: "Tutorials"
order: 1
language: en
---

# Tutorial: Local VM Provisioning

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## Prerequisites

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/en/docs/experimental-vms) for setup instructions

## Interactive Recording

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## What You'll See

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Step 1: Verify system requirements

```bash
rdc ops check
```

Checks for hardware virtualization support, required packages (libvirt, QEMU), and network configuration. This must pass before you can provision VMs.

### Step 2: Provision a minimal VM cluster

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### Step 3: Check cluster status

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### Step 4: Run commands on a VM

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Runs commands on the bridge VM (ID `1`) over SSH. You can pass any command after the VM ID. For an interactive shell, omit the command: `rdc ops ssh 1`.

### Step 5: Tear down the cluster

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## Next Steps

- [Experimental VMs](/en/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/en/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/en/docs/quick-start) — deploy a containerized service end-to-end
