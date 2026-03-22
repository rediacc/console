---
title: "Local VM Provisioning"
description: "Provision a local VM cluster, run commands over SSH, and tear it down using the CLI."
category: "Tutorials"
order: 1
language: en
---

# How To Provision Local VMs with Rediacc

Testing infrastructure locally before deploying to production saves time and prevents misconfigurations. In this tutorial, you provision a minimal VM cluster on your workstation, verify connectivity, run commands over SSH, and tear everything down. When you finish, you have a repeatable local development environment.

## Prerequisites

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/en/docs/experimental-vms) for setup instructions

## Interactive Recording

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### Step 1: Verify system requirements

Before provisioning, confirm that your workstation has virtualization support and the required packages installed.

```bash
rdc ops check
```

Rediacc checks for hardware virtualization (VT-x/AMD-V), required packages (libvirt, QEMU), and network configuration. Every check must pass before you can create VMs.

### Step 2: Provision a minimal VM cluster

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

> **Note:** The first provisioning downloads base images, which takes longer. Subsequent runs reuse cached images.

### Step 3: Check cluster status

```bash
rdc ops status
```

Displays the state of each VM in the cluster — IP addresses, resource allocation, and running status. Both VMs should show as running.

### Step 4: Run commands on a VM

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Runs commands on the bridge VM (ID `1`) over SSH. Pass any command after the VM ID. For an interactive shell, omit the command: `rdc ops ssh 1`.

### Step 5: Tear down the cluster

When you're done, destroy all VMs and free resources.

```bash
rdc ops down
```

Removes all VMs and cleans up networking. The cluster can be reprovisioned at any time with `rdc ops up`.

## Troubleshooting

**"KVM not available" or "hardware virtualization not supported"**
Verify that virtualization is enabled in your BIOS/UEFI settings. On Linux, check with `lscpu | grep Virtualization`. On WSL2, nested virtualization requires specific kernel flags.

**"libvirt daemon not running"**
Start the libvirt service: `sudo systemctl start libvirtd`. On macOS, verify QEMU is installed via Homebrew: `brew install qemu`.

**"Insufficient memory for VM allocation"**
The basic cluster requires at least 6 GB of free RAM (1 GB bridge + 4 GB worker + overhead). Close other resource-intensive applications or reduce VM specs.

## Next Steps

You provisioned a local VM cluster, ran commands over SSH, and tore it down. To deploy real infrastructure:

- [Experimental VMs](/en/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Tutorial: Machine Setup](/en/docs/tutorial-setup) — register remote machines and configure infrastructure
- [Quick Start](/en/docs/quick-start) — deploy a containerized service end-to-end
