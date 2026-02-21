---
title: "Experimental VMs"
description: "Provision local VM clusters for development and testing with rdc ops."
category: "Guides"
order: 15
language: de
---

# Experimental VMs

Provision local VM clusters on your workstation for development and testing — no external cloud providers required.

## Overview

Mit den `rdc ops`-Befehlen können Sie experimentelle VM-Cluster lokal erstellen und verwalten. Dies ist dieselbe Infrastruktur, die von der CI-Pipeline für Integrationstests verwendet wird, und steht nun für praktische Experimente zur Verfügung.

Use cases:
- Test Rediacc deployments without external VM providers (Linode, Vultr, etc.)
- Develop and debug repository configurations locally
- Learn the platform in a fully isolated environment
- Run integration tests on your workstation

## Platform Support

| Platform | Architecture | Backend | Status |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | Full support |
| Linux | ARM64 | KVM (libvirt) | Full support |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Full support |
| macOS | Intel | QEMU + HVF | Full support |
| Windows | x86_64 / ARM64 | Hyper-V | Planned |

**Linux (KVM)** uses libvirt for native hardware virtualization with bridged networking.

**macOS (QEMU)** uses QEMU with Apple's Hypervisor Framework (HVF) for near-native performance, with user-mode networking and SSH port forwarding.

**Windows (Hyper-V)** support is planned. See [issue #380](https://github.com/rediacc/console/issues/380) for details. Requires Windows Pro/Enterprise.

## Prerequisites & Setup

### Linux

```bash
# Install prerequisites automatically
rdc ops setup

# Or manually:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Install prerequisites automatically
rdc ops setup

# Or manually:
brew install qemu cdrtools
```

### Verify Setup

```bash
rdc ops check
```

This runs platform-specific checks and reports pass/fail for each prerequisite.

## Quick Start

```bash
# 1. Check prerequisites
rdc ops check

# 2. Provision a minimal cluster (bridge + 1 worker)
rdc ops up --basic

# 3. Check VM status
rdc ops status

# 4. SSH into the bridge VM
rdc ops ssh 1

# 5. Tear down
rdc ops down
```

## Cluster Composition

By default, `rdc ops up` provisions:

| VM | ID | Role |
|----|-----|------|
| Bridge | 1 | Primary node — runs the Rediacc bridge service |
| Worker 1 | 11 | Worker node for repository deployments |
| Worker 2 | 12 | Worker node for repository deployments |

Use the `--basic` flag to provision only the bridge and first worker (IDs 1 and 11).

Use `--skip-orchestration` to provision VMs without starting Rediacc services — useful for testing the VM layer in isolation.

## Configuration

Environment variables control VM resources:

| Variable | Default | Description |
|----------|---------|-------------|
| `VM_CPU` | 2 | CPU cores per VM |
| `VM_RAM` | 4096 | RAM in MB per VM |
| `VM_DSK` | 16 | Disk size in GB |
| `VM_NET_BASE` | 192.168.111 | Network base (KVM only) |
| `RENET_DATA_DIR` | ~/.renet | Data directory for VM disks and config |

## Command Reference

| Command | Description |
|---------|-------------|
| `rdc ops setup` | Install platform prerequisites (KVM or QEMU) |
| `rdc ops check` | Verify prerequisites are installed and working |
| `rdc ops up [options]` | Provision VM cluster |
| `rdc ops down` | Destroy all VMs and cleanup |
| `rdc ops status` | Show status of all VMs |
| `rdc ops ssh <vm-id>` | SSH into a specific VM |

### `rdc ops up` Options

| Option | Description |
|--------|-------------|
| `--basic` | Minimal cluster (bridge + 1 worker) |
| `--lite` | Lightweight resources |
| `--force` | Force recreate existing VMs |
| `--parallel` | Provision VMs in parallel |
| `--skip-orchestration` | VMs only, no Rediacc services |
| `--backend <kvm\|qemu>` | Override auto-detected backend |
| `--os <name>` | OS image (default: ubuntu-24.04) |
| `--debug` | Verbose output |

## Platform Differences

### Linux (KVM)
- Uses libvirt for VM lifecycle management
- Bridged networking — VMs get IPs on a virtual network (192.168.111.x)
- Direct SSH to VM IPs
- Requires `/dev/kvm` and libvirtd service

### macOS (QEMU + HVF)
- Uses QEMU processes managed via PID files
- User-mode networking with SSH port forwarding (localhost:222XX)
- SSH via forwarded ports, not direct IPs
- Cloud-init ISOs created via `mkisofs`

## Troubleshooting

### Debug mode

Add `--debug` to any command for verbose output:

```bash
rdc ops up --basic --debug
```

### Common issues

**KVM not available (Linux)**
- Check `/dev/kvm` exists: `ls -la /dev/kvm`
- Enable virtualization in BIOS/UEFI
- Load the kernel module: `sudo modprobe kvm_intel` or `sudo modprobe kvm_amd`

**libvirtd not running (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU not found (macOS)**
```bash
brew install qemu cdrtools
```

**VMs won't start**
- Check disk space in `~/.renet/disks/`
- Run `rdc ops check` to verify all prerequisites
- Try `rdc ops down` then `rdc ops up --force`
