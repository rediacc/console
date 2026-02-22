---
title: "安装"
description: "在 Linux、macOS 或 Windows 上安装 Rediacc CLI。"
category: "Guides"
order: 1
language: zh
---

# 安装

在您的工作站上安装 `rdc` CLI。这是您唯一需要手动安装的工具 -- 当您设置远程机器时，其他一切都会自动处理。

## Linux 和 macOS

运行安装脚本：

```bash
curl -fsSL https://get.rediacc.com | sh
```

此命令会将 `rdc` 二进制文件下载到 `$HOME/.local/bin/`。请确保该目录在您的 PATH 中：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

将此行添加到您的 shell 配置文件（`~/.bashrc`、`~/.zshrc` 等）以使其永久生效。

## Windows

在 PowerShell 中运行安装脚本：

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

这将把 `rdc.exe` 二进制文件下载到 `%LOCALAPPDATA%\rediacc\bin\`。请确保该目录已添加到您的 PATH 中。安装程序会在未添加时提示您添加。

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

注意：`gcompat` 包（glibc 兼容层）会作为依赖项自动安装。

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## 验证安装

```bash
rdc --version
```

您应该能看到已安装的版本号。

## 更新

将 `rdc` 更新到最新版本：

```bash
rdc update
```

仅检查更新而不安装：

```bash
rdc update --check-only
```

更新后回滚到之前的版本：

```bash
rdc update rollback
```
