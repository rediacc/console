---
title: "安装"
description: "在 Linux、macOS 或 Windows 上安装 Rediacc CLI。"
category: "Guides"
order: 1
language: zh
sourceHash: "2651baa400d94f8c"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# 安装

在您的工作站上安装 `rdc` CLI。这是唯一需要手动安装的工具 -- 在设置远程机器时，其他一切都会自动处理。

## 快速安装

### Linux 和 macOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

此命令将 `rdc` 二进制文件下载到 `$HOME/.local/bin/`。请确保此目录在您的 PATH 中：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

将此行添加到您的 shell 配置文件（`~/.bashrc`、`~/.zshrc` 等）以使其永久生效。

### Windows

在 PowerShell 中运行：

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

此命令将 `rdc.exe` 下载到 `%LOCALAPPDATA%\rediacc\bin\`。如果需要，安装程序会提示您将其添加到 PATH。

## 包管理器

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL 兼容)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

Oracle Linux、AlmaLinux 和 Rocky Linux 均使用相同的 DNF 流程；任何带有 `dnf` 的 RHEL 兼容发行版都可以添加上述软件源。注意：**Oracle Linux 10 是唯一官方支持作为 Rediacc 服务器目标的 RHEL 系列发行版**（参见[系统要求](/en/docs/requirements)）。Rocky/Alma 10 缺少 renet 数据平面所需的 btrfs 内核模块，但 `rdc` CLI 可以在这些系统上正常安装。

### Zypper (openSUSE Leap)

```bash
sudo zypper addrepo https://releases.rediacc.com/rpm/stable/rediacc.repo
sudo zypper --gpg-auto-import-keys refresh
sudo zypper install rediacc-cli
```

已在 openSUSE Leap 16.0+ 上测试。

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

注意：`gcompat` 包（glibc 兼容层）会作为依赖项自动安装。

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

拉取并作为容器运行 CLI：

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

创建别名以方便使用：

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

可用的 Docker 标签：

| 标签 | 说明 |
|------|------|
| `:stable` | 最新稳定版（推荐） |
| `:edge` | 最新 edge 版本 |
| `:0.8.4` | 固定版本（不可变） |
| `:latest` | `:stable` 的别名 |

## 验证安装

```bash
rdc --version
```

## 更新

更新到最新版本：

```bash
rdc update
```

仅检查更新而不安装：

```bash
rdc update --check-only
```

查看当前更新状态：

```bash
rdc update --status
```

回滚到上一个版本：

```bash
rdc update --rollback
```

## 发布渠道

Rediacc 使用基于渠道的发布系统。渠道决定了您通过 CLI 更新、包管理器安装和 Docker 拉取获得的版本。

| 渠道 | 说明 | 更新时间 |
|------|------|----------|
| `stable` | 生产就绪版本 | 经过 7 天验证期后从 edge 提升 |
| `edge` | 最新功能和修复 | 每次合并到 main |
| `pr-N` | PR 预览构建 | 每个 pull request 自动生成 |

### 切换渠道

```bash
rdc update --channel edge      # 切换到 edge 渠道
rdc update --channel stable    # 切换回 stable 渠道
```

直接从 edge 渠道安装：

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

对于包管理器，将仓库 URL 中的 `stable` 替换为 `edge`：

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### 渠道工作原理

渠道统一应用于所有分发方式：

- **安装脚本**：`REDIACC_CHANNEL` 环境变量选择渠道
- **包仓库**：`releases.rediacc.com/{格式}/{渠道}/`
- **Docker 标签**：`ghcr.io/rediacc/elite/cli:{渠道}`
- **CLI 更新**：`rdc update` 检查安装时配置的渠道

### PR 预览自动配置

当您从 PR 预览部署（例如 `pr-420.rediacc.workers.dev`）安装时，渠道和账户服务器会自动配置：

- CLI 二进制文件从 `pr-420` 渠道下载
- `rdc update` 检查 `pr-420` 渠道的更新
- 所有账户/订阅命令连接到 PR 预览服务器
- 预览站点上的 Docker 命令显示 `cli:pr-420`

无需手动配置。安装脚本会从 URL 检测部署上下文。

## 远程二进制更新

当您对远程机器执行命令时，CLI 会自动配置匹配的 `renet` 二进制文件。如果二进制文件已更新，路由服务器（`rediacc-router`）会自动重启以采用新版本。

重启是透明的，**不会造成停机**：

- 路由服务器在约 1-2 秒内重启。
- 在此期间，Traefik 使用其最后已知的路由配置继续提供流量服务。不会丢失任何路由。
- Traefik 在下一个轮询周期（5 秒内）获取新配置。
- **现有客户端连接（HTTP、TCP、UDP）不受影响。** 路由服务器是配置提供者 -- 它不在数据路径中。Traefik 直接处理所有流量。
- 您的应用容器不会受到影响 -- 只有系统级的路由服务器进程会重启。

要跳过自动重启，请向任何命令传递 `--skip-router-restart`，或设置环境变量 `RDC_SKIP_ROUTER_RESTART=1`。
