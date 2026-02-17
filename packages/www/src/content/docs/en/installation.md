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
