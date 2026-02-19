---
title: "Requirements"
description: "System requirements and supported platforms for running Rediacc."
category: "Guides"
order: 0
language: en
---

# Requirements

Before deploying with Rediacc, make sure your workstation and remote servers meet the following requirements.

## Workstation (Control Plane)

The `rdc` CLI runs on your workstation and orchestrates remote servers over SSH.

| Platform | Minimum Version | Notes |
|----------|----------------|-------|
| macOS | 12 (Monterey)+ | Intel and Apple Silicon supported |
| Linux (x86_64) | Any modern distribution | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Native support via PowerShell installer |

**Additional requirements:**
- An SSH key pair (e.g., `~/.ssh/id_ed25519` or `~/.ssh/id_rsa`)
- Network access to your remote servers on the SSH port (default: 22)

## Remote Server (Data Plane)

The `renet` binary runs on remote servers with root privileges. It manages encrypted disk images, isolated Docker daemons, and service orchestration.

If you are unsure which binary to use, see [rdc vs renet](/en/docs/rdc-vs-renet). In short: use `rdc` for normal operations, and use direct `renet` only for advanced remote-side tasks.

### Supported Operating Systems

| OS | Version | Architecture |
|----|---------|-------------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |

These are the distributions tested in CI. Other Linux distributions with systemd, Docker support, and cryptsetup may work but are not officially supported.

### Server Prerequisites

- A user account with `sudo` privileges (passwordless sudo recommended)
- Your SSH public key added to `~/.ssh/authorized_keys`
- At least 20 GB of free disk space (more depending on your workloads)
- Internet access for pulling Docker images (or a private registry)

### Installed Automatically

The `rdc context setup-machine` command installs the following on the remote server:

- **Docker** and **containerd** (container runtime)
- **cryptsetup** (LUKS disk encryption)
- **renet** binary (uploaded via SFTP)

You do not need to install these manually.
