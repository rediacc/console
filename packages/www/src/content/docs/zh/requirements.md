---
title: 系统要求
description: 运行 Rediacc 的系统要求和支持的平台。
category: Guides
order: 0
language: zh
sourceHash: 35e75948e9858c6d
---

# 系统要求

如果你不确定该使用哪个工具，请参考 [rdc vs renet](/zh/docs/rdc-vs-renet)。

在使用 Rediacc 进行部署之前，请确保您的工作站和远程服务器满足以下要求。

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

### 支持的操作系统

| 操作系统 | 版本 | 架构 |
|----------|------|------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |
| Alpine | 3.19+ | x86_64（需要 gcompat） |
| Arch Linux | 滚动发布 | x86_64 |

以上是在 CI 中测试过的发行版。其他具有 systemd、Docker 支持和 cryptsetup 的 Linux 发行版可能可以工作，但未获得官方支持。

### 服务器前提条件

- 具有 `sudo` 权限的用户账户（建议使用免密码 sudo）
- 您的 SSH 公钥已添加到 `~/.ssh/authorized_keys`
- 至少 20 GB 的可用磁盘空间（根据工作负载可能需要更多）
- 用于拉取 Docker 镜像的互联网连接（或私有 registry）

### 自动安装的组件

`rdc context setup-machine` 命令会在远程服务器上安装以下组件：

- **Docker** 和 **containerd**（容器运行时）
- **cryptsetup**（LUKS 磁盘加密）
- **renet** 二进制文件（通过 SFTP 上传）

您无需手动安装这些组件。

## Local Virtual Machines (Optional)

If you want to test deployments locally using `rdc ops`, your workstation needs virtualization support: KVM on Linux or QEMU on macOS. See the [Experimental VMs](/zh/docs/experimental-vms) guide for setup steps and platform details.
