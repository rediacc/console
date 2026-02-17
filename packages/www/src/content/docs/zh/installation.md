---
title: "安装"
description: "在 Linux、macOS 或 Windows 上安装 Rediacc CLI。"
category: "Getting Started"
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

## Windows (WSL2)

Rediacc 在 Windows 上运行于 WSL2 中。如果您尚未设置 WSL2：

```powershell
wsl --install
```

然后在您的 WSL2 Linux 发行版中运行相同的安装脚本：

```bash
curl -fsSL https://get.rediacc.com | sh
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
