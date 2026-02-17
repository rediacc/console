---
title: "Installation"
description: "Install the Rediacc CLI on Linux, macOS, or Windows."
category: "Getting Started"
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

## Windows (WSL2)

Rediacc runs inside WSL2 on Windows. If you don't have WSL2 set up:

```powershell
wsl --install
```

Then inside your WSL2 Linux distribution, run the same install script:

```bash
curl -fsSL https://get.rediacc.com | sh
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
