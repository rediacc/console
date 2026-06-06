---
title: Requirements
description: System requirements and supported platforms for running Rediacc.
category: Guides
order: 0
language: en
---

# Requirements

Most of this is standard Linux server setup. A few details are specific to how Rediacc works, so check them before you start.

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

Remote servers run the `renet` binary and host the encrypted, per-repo Docker daemons. The following five distributions are exercised by the Bridge Workers matrix in CI on every pull request, and are the only ones officially supported:

| OS | Version | Default Kernel | Notes |
|----|---------|----------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | Recommended. AppArmor enabled by default. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 also works (kernel 6.1 minimum). |
| Fedora | 43 | 6.12 | SELinux enforcing by default. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor enabled by default. |
| Oracle Linux | 10 | UEK 7+ | Uses UEK, which retains the btrfs module. SELinux enforcing by default. See "Why UEK?" below. |

All rows are `x86_64`. `arm64` is built but not continuously tested for every server OS; open an issue if you need it on a specific distro. Other Linux distributions with systemd, Docker support, and cryptsetup may work but are not officially supported and may break on upgrades without notice.

#### Why UEK? (and why Rocky 10 / stock RHEL 10 is not supported)

Rediacc's encrypted storage backend requires the in-tree `btrfs` kernel module. **RHEL 10's stock kernel ships without it**: `modprobe btrfs` fails with "Module btrfs not found" and `dnf search btrfs` returns nothing. Rocky Linux 10 and AlmaLinux 10 inherit the same kernel and therefore cannot run as Rediacc servers.

Oracle Linux 10 uses the **Unbreakable Enterprise Kernel (UEK)** by default, which keeps btrfs built in. That is the only RHEL-compatible target on the supported list. If you must run a RHEL-family server, use Oracle Linux 10 with UEK. (The ground truth for this decision lives in `.github/workflows/ct-tests.yml` as the CI Bridge Workers matrix.)

#### Workstation-only (CLI install targets)

The `rdc` CLI additionally installs cleanly on Alpine 3.19+ (APK with the `gcompat` compatibility layer, installed automatically) and Arch Linux (rolling, via pacman). These are client-side install paths only (see [Installation](/en/docs/installation)) and are not supported as `renet` server targets.

### Security Policies by OS

The per-repo Docker daemon and the repo containers themselves run with **default container labels** on every supported OS. `rdc config machine setup` does not install custom SELinux policies or AppArmor profiles. Behavior by OS:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor is enabled by default. The default docker-container profile applies; no extra setup required.
- **Fedora 43, Oracle Linux 10**: SELinux runs enforcing. The per-repo daemon labels containers with the standard `container_t` context. No custom SELinux policy is needed.
- **CRIU** (checkpoint/restore) is the one case that bypasses the AppArmor profile with `apparmor=unconfined`, since upstream CRIU's AppArmor support is not yet stable. See the CRIU notes in [Rules of Rediacc](/en/docs/rules-of-rediacc).

If a setup step fails with SELinux AVC denials or AppArmor rejections, see [Troubleshooting](/en/docs/troubleshooting) → Distribution-Specific Setup Issues.

### Server Prerequisites

- A user account with `sudo` privileges (passwordless sudo recommended)
- Your SSH public key added to `~/.ssh/authorized_keys`
- At least 20 GB of free disk space (more depending on your workloads)
- Internet access for pulling Docker images (or a private registry)

### Installed Automatically

The `rdc config machine setup` command installs the following on the remote server:

- **Docker** and **containerd** (container runtime)
- **cryptsetup** (LUKS disk encryption)
- **renet** binary (uploaded via SFTP)

You do not need to install these manually.

## Local Virtual Machines (Optional)

If you want to test deployments locally using `rdc ops`, your workstation needs virtualization support: KVM on Linux or QEMU on macOS. See the [Experimental VMs](/en/docs/experimental-vms) guide for setup steps and platform details.
