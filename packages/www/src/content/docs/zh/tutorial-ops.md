---
title: "本地虚拟机配置"
description: "使用 CLI 配置本地虚拟机集群、通过 SSH 运行命令并清理环境。"
category: "Tutorials"
order: 1
language: zh
sourceHash: "2fdc49f796b03e18"
---

# 如何使用 Rediacc 配置本地虚拟机

在部署到生产环境之前在本地测试基础设施可以节省时间并防止配置错误。在本教程中，您将在工作站上配置一个最小虚拟机集群、验证连接、通过 SSH 运行命令并销毁所有资源。完成后，您将拥有一个可重复的本地开发环境。

## 前提条件

- 启用了硬件虚拟化的 Linux 或 macOS 工作站
- 已安装 `rdc` CLI 并使用本地适配器初始化配置
- 已安装 KVM/libvirt（Linux）或 QEMU（macOS）— 有关设置说明，请参阅[实验性虚拟机](/zh/docs/experimental-vms)

## 交互式录像

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### 步骤 1：验证系统要求

在配置之前，确认您的工作站具有虚拟化支持并且已安装所需的软件包。

```bash
rdc ops check
```

Rediacc 检查硬件虚拟化（VT-x/AMD-V）、所需软件包（libvirt、QEMU）和网络配置。在创建虚拟机之前，所有检查都必须通过。

### 步骤 2：配置最小虚拟机集群

```bash
rdc ops up --basic --skip-orchestration
```

创建一个双虚拟机集群：一个**桥接**虚拟机（1 CPU、1024 MB 内存、8 GB 磁盘）和一个**工作**虚拟机（2 CPU、4096 MB 内存、16 GB 磁盘）。`--skip-orchestration` 标志跳过 Rediacc 平台配置，仅提供具有 SSH 访问权限的裸虚拟机。

> **注意：** 首次配置会下载基础镜像，因此需要更长时间。后续运行将重用缓存的镜像。

### 步骤 3：检查集群状态

```bash
rdc ops status
```

显示集群中每个虚拟机的状态 — IP 地址、资源分配和运行状态。两个虚拟机都应显示为正在运行。

### 步骤 4：在虚拟机上运行命令

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

通过 SSH 在桥接虚拟机（ID `1`）上运行命令。您可以在虚拟机 ID 后传递任何命令。要获得交互式 shell，请省略命令：`rdc ops ssh 1`。

### 步骤 5：销毁集群

完成后，销毁所有虚拟机并释放资源。

```bash
rdc ops down
```

删除所有虚拟机并清理网络。集群可以随时使用 `rdc ops up` 重新配置。

## 故障排除

**"KVM not available" 或 "hardware virtualization not supported"**
验证 BIOS/UEFI 设置中是否启用了虚拟化。在 Linux 上，使用 `lscpu | grep Virtualization` 检查。在 WSL2 上，嵌套虚拟化需要特定的内核标志。

**"libvirt daemon not running"**
启动 libvirt 服务：`sudo systemctl start libvirtd`。在 macOS 上，验证 QEMU 是否通过 Homebrew 安装：`brew install qemu`。

**"Insufficient memory for VM allocation"**
基本集群至少需要 6 GB 可用内存（1 GB 桥接 + 4 GB 工作 + 开销）。关闭其他资源密集型应用程序或减少虚拟机规格。

## 后续步骤

您已配置了本地虚拟机集群、通过 SSH 运行了命令并将其销毁。要部署实际基础设施：

- [实验性虚拟机](/zh/docs/experimental-vms) — `rdc ops` 命令、虚拟机配置和平台支持的完整参考
- [教程：机器设置](/zh/docs/tutorial-setup) — 注册远程机器并配置基础设施
- [快速入门](/zh/docs/quick-start) — 端到端部署容器化服务
