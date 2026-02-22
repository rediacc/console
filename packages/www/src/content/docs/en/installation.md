---
title: "Installation"
description: "Install the Rediacc CLI on Linux, macOS, or Windows."
category: "Guides"
order: 1
language: en
---

# Installation

Install the `rdc` CLI on your workstation. This is the only tool you need to install manually — everything else is handled automatically when you set up remote machines.

## Linux and macOS

Run the install script:

```bash
curl -fsSL https://get.rediacc.com | sh
```

This downloads the `rdc` binary to `$HOME/.local/bin/`. Make sure this directory is in your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add this line to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) to make it permanent.

## Windows

Run the install script in PowerShell:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

This downloads the `rdc.exe` binary to `%LOCALAPPDATA%\rediacc\bin\`. Make sure this directory is in your PATH. The installer will prompt you to add it if it is not already present.

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

Note: The `gcompat` package (glibc compatibility layer) is installed automatically as a dependency.

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## Verify Installation

```bash
rdc --version
```

You should see the installed version number.

## Updating

To update `rdc` to the latest version:

```bash
rdc update
```

To check for updates without installing:

```bash
rdc update --check-only
```

To rollback to the previous version after an update:

```bash
rdc update rollback
```

### Remote Binary Updates

When you run commands against a remote machine, the CLI automatically provisions the matching `renet` binary. If the binary is updated, the route server (`rediacc-router`) is restarted automatically so it picks up the new version.

The restart is transparent and causes **no downtime**:

- The route server restarts in ~1–2 seconds.
- During that window, Traefik continues serving traffic using its last known routing configuration. No routes are dropped.
- Traefik picks up the new configuration on its next poll cycle (within 5 seconds).
- **Existing client connections (HTTP, TCP, UDP) are not affected.** The route server is a configuration provider — it is not in the data path. Traefik handles all traffic directly.
- Your application containers are not touched — only the system-level route server process is restarted.

To skip the automatic restart, pass `--skip-router-restart` to any command, or set the `RDC_SKIP_ROUTER_RESTART=1` environment variable.
