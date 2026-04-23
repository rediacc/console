---
title: "Installation"
description: "Install the Rediacc CLI on Linux, macOS, or Windows."
category: "Guides"
order: 1
language: en
---

# Installation

Install the `rdc` CLI on your workstation. This is the only tool you need to install manually -- everything else is handled automatically when you set up remote machines.

## Quick Install

### Linux and macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

This downloads the `rdc` binary to `$HOME/.local/bin/`. Make sure this directory is in your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add this line to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) to make it permanent.

### Windows

Run in PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

This downloads `rdc.exe` to `%LOCALAPPDATA%\rediacc\bin\`. The installer will prompt you to add it to your PATH if needed.

## Package Managers

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL-compatible)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux, AlmaLinux, and Rocky Linux all use the same DNF flow; any RHEL-compatible distribution with `dnf` can pull the repo above. Note: **Oracle Linux 10 is the only RHEL-family distribution officially supported as a Rediacc server target** (see [Requirements](/en/docs/requirements)). Rocky/Alma 10 lack the btrfs kernel module needed by the renet data plane, though the `rdc` CLI installs on them fine.

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

Tested on openSUSE Leap 16.0+.

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Note: The `gcompat` package (glibc compatibility layer) is installed automatically as a dependency.

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

### npm (Node.js)

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-latest.tgz
```

Requires Node.js 22 or later. To install a specific version:

```bash
npm install -g https://releases.rediacc.com/npm/stable/rediacc-cli-0.8.5.tgz
```

## Docker

Pull and run the CLI as a container:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

Create an alias for convenience:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

Available Docker tags:

| Tag | Description |
|-----|-------------|
| `:stable` | Latest stable release (recommended) |
| `:edge` | Latest edge release |
| `:0.8.4` | Pinned version (immutable) |
| `:latest` | Alias for `:stable` |

## Verify Installation

```bash
rdc --version
```

## Updating

Update to the latest version:

```bash
rdc update
```

Check for updates without installing:

```bash
rdc update --check-only
```

View current update status:

```bash
rdc update --status
```

Rollback to the previous version:

```bash
rdc update --rollback
```

## Release Channels

Rediacc uses a channel-based release system. The channel determines which version you receive for CLI updates, package manager installs, and Docker pulls.

| Channel | Description | When updated |
|---------|-------------|--------------|
| `stable` | Production, promoted from edge after 7-day soak | Weekly soak promotion |
| `edge` | Continuously deployed production | Every merge to main |
| `pr-N` | PR preview builds | Automatically per pull request |

### Switching channels

```bash
rdc update --channel edge      # Switch to edge channel
rdc update --channel stable    # Switch back to stable
```

Install directly from the edge channel:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

For package managers, replace `stable` with `edge` in the repository URL:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### How channels work

The channel applies uniformly across all delivery methods:

- **Install scripts**: `REDIACC_CHANNEL` env var selects the channel
- **Package repos**: `releases.rediacc.com/{format}/{channel}/`
- **Docker tags**: `ghcr.io/rediacc/elite/cli:{channel}`
- **CLI updates**: `rdc update` checks the channel configured during install

### PR preview auto-configuration

When you install from a PR preview deployment (e.g., `pr-420.rediacc.workers.dev`), the channel and account server are auto-configured:

- CLI binary is downloaded from the `pr-420` channel
- `rdc update` checks the `pr-420` channel for updates
- All account/subscription commands connect to the PR preview server
- Docker commands on the preview site show `cli:pr-420`

No manual configuration needed. The install script detects the deployment context from the URL.

## Remote Binary Updates

When you run commands against a remote machine, the CLI automatically provisions the matching `renet` binary. If the binary is updated, the route server (`rediacc-router`) is restarted automatically so it picks up the new version.

The restart is transparent and causes **no downtime**:

- The route server restarts in ~1-2 seconds.
- During that window, Traefik continues serving traffic using its last known routing configuration. No routes are dropped.
- Traefik picks up the new configuration on its next poll cycle (within 5 seconds).
- **Existing client connections (HTTP, TCP, UDP) are not affected.** The route server is a configuration provider -- it is not in the data path. Traefik handles all traffic directly.
- Your application containers are not touched -- only the system-level route server process is restarted.

To skip the automatic restart, pass `--skip-router-restart` to any command, or set the `RDC_SKIP_ROUTER_RESTART=1` environment variable.
