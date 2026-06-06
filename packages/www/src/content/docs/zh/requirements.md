---
title: 系统要求
description: 运行 Rediacc 的系统要求和支持的平台。
category: Guides
order: 0
language: zh
sourceHash: "e84db3bb90270473"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 系统要求

这些基本上都是标准的 Linux 服务器设置。有些细节特定于 Rediacc 的工作方式，所以在开始之前请检查一下。

## 工作站（控制平面）

`rdc` CLI 运行在您的工作站上，通过 SSH 编排远程服务器。

| 平台 | 最低版本 | 备注 |
|------|----------|------|
| macOS | 12 (Monterey)+ | 支持 Intel 和 Apple Silicon |
| Linux (x86_64) | 任何现代发行版 | glibc 2.31+（Ubuntu 20.04+、Debian 11+、Fedora 34+） |
| Windows | 10+ | 通过 PowerShell 安装程序提供原生支持 |

**额外要求：**
- 一对 SSH 密钥（例如 `~/.ssh/id_ed25519` 或 `~/.ssh/id_rsa`）
- 通过 SSH 端口（默认：22）访问远程服务器的网络连接

## 远程服务器（数据平面）

`renet` 二进制文件以 root 权限运行在远程服务器上。它管理加密磁盘映像、隔离的 Docker 守护进程和服务编排。

如果您不确定该使用哪个工具，请参考 [rdc vs renet](/en/docs/rdc-vs-renet)。简而言之：正常操作使用 `rdc`，仅在高级服务器端任务时才直接使用 `renet`。

### 支持的操作系统

远程服务器运行 `renet` 二进制文件，并托管每个仓库专属的加密隔离 Docker 守护进程。以下五个发行版在每次拉取请求时都会由 CI 中的 Bridge Workers 矩阵进行测试，是唯一获得官方支持的系统：

| 操作系统 | 版本 | 默认内核 | 备注 |
|----------|------|----------|------|
| Ubuntu | 24.04 LTS | 6.8 | 推荐。AppArmor 默认启用。 |
| Debian | 13 (Trixie) | 6.12 | Debian 12 也可用（内核最低 6.1）。 |
| Fedora | 43 | 6.12 | SELinux 默认处于 enforcing 模式。 |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor 默认启用。 |
| Oracle Linux | 10 | UEK 7+ | 使用保留了 btrfs 模块的 UEK。SELinux 默认处于 enforcing 模式。请参阅下方"为什么选择 UEK？"。 |

所有行均为 `x86_64`。`arm64` 已构建但未针对每个服务器 OS 持续测试；如果您需要在特定发行版上使用，请提交 issue。其他具有 systemd、Docker 支持和 cryptsetup 的 Linux 发行版可能可以工作，但未获得官方支持，升级时可能在未通知的情况下停止工作。

#### 为什么选择 UEK？（以及为什么 Rocky 10 / 原生 RHEL 10 不受支持）

Rediacc 的加密存储后端需要树内 `btrfs` 内核模块。**RHEL 10 的原生内核不包含该模块**：`modprobe btrfs` 会提示 "Module btrfs not found"，`dnf search btrfs` 也不返回任何结果。Rocky Linux 10 和 AlmaLinux 10 继承了相同的内核，因此无法作为 Rediacc 服务器运行。

Oracle Linux 10 默认使用 **Unbreakable Enterprise Kernel (UEK)**，该内核保留了内置的 btrfs。这是支持列表中唯一兼容 RHEL 的目标。如果必须运行 RHEL 系列服务器，请使用带有 UEK 的 Oracle Linux 10。（此决策的真实依据位于 `.github/workflows/ct-tests.yml` 中，作为 CI Bridge Workers 矩阵。）

#### 仅限工作站（CLI 安装目标）

`rdc` CLI 还可以在 Alpine 3.19+（带有自动安装的 `gcompat` 兼容层的 APK）和 Arch Linux（滚动版，通过 pacman）上干净安装。这些是仅限客户端的安装路径（参见[安装](/en/docs/installation)），不支持作为 `renet` 服务器目标。

### 各操作系统的安全策略

每个仓库的 Docker 守护进程和仓库容器本身在所有受支持的操作系统上均以**默认容器标签**运行。`rdc config machine setup` 不安装自定义 SELinux 策略或 AppArmor 配置文件。各操作系统的行为如下：

- **Ubuntu 24.04、openSUSE Leap 16.0**：AppArmor 默认启用。应用默认的 docker-container 配置文件，无需额外设置。
- **Fedora 43、Oracle Linux 10**：SELinux 处于 enforcing 状态运行。每个仓库的守护进程使用标准 `container_t` 上下文为容器打标签。不需要自定义 SELinux 策略。
- **CRIU**（checkpoint/restore）是唯一使用 `apparmor=unconfined` 绕过 AppArmor 配置文件的情况，因为上游 CRIU 的 AppArmor 支持尚未稳定。请参阅 [Rediacc 规则](/en/docs/rules-of-rediacc) 中的 CRIU 说明。

如果某个设置步骤因 SELinux AVC 拒绝或 AppArmor 拒绝而失败，请参阅[故障排除](/en/docs/troubleshooting)中的"特定发行版设置问题"部分。

### 服务器前提条件

- 具有 `sudo` 权限的用户账户（建议使用免密码 sudo）
- 您的 SSH 公钥已添加到 `~/.ssh/authorized_keys`
- 至少 20 GB 的可用磁盘空间（根据工作负载可能需要更多）
- 用于拉取 Docker 镜像的互联网连接（或私有 registry）

### 自动安装的组件

`rdc config machine setup` 命令会在远程服务器上安装以下组件：

- **Docker** 和 **containerd**（容器运行时）
- **cryptsetup**（LUKS 磁盘加密）
- **renet** 二进制文件（通过 SFTP 上传）

您无需手动安装这些组件。

## 本地虚拟机（可选）

如果您希望使用 `rdc ops` 在本地测试部署，您的工作站需要虚拟化支持：Linux 上的 KVM 或 macOS 上的 QEMU。有关设置步骤和平台详情，请参阅[实验性虚拟机](/en/docs/experimental-vms)指南。
