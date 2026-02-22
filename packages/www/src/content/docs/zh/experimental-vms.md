---
title: "实验性虚拟机"
description: "使用 rdc ops 配置本地 VM 集群，用于开发和测试。"
category: "Concepts"
order: 2
language: zh
sourceHash: "30b5f6267314cfb2"
---

# 实验性虚拟机

在您的工作站上配置本地 VM 集群，用于开发和测试 — 无需外部云服务商。

## 概述

`rdc ops` 命令允许您在本地创建和管理实验性 VM 集群。这与 CI 流水线用于集成测试的基础设施完全相同，现已开放供实际动手实验使用。

使用场景：
- 无需外部 VM 提供商（Linode、Vultr 等）即可测试 Rediacc 部署
- 在本地开发和调试仓库配置
- 在完全隔离的环境中学习平台
- 在您的工作站上运行集成测试

## 平台支持

| 平台 | 架构 | 后端 | 状态 |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | 完全支持 |
| Linux | ARM64 | KVM (libvirt) | 完全支持 |
| macOS | ARM (Apple Silicon) | QEMU + HVF | 完全支持 |
| macOS | Intel | QEMU + HVF | 完全支持 |
| Windows | x86_64 / ARM64 | Hyper-V | 计划中 |

**Linux (KVM)** 使用 libvirt 进行原生硬件虚拟化，采用桥接网络。

**macOS (QEMU)** 使用 QEMU 配合 Apple 的 Hypervisor Framework (HVF)，实现接近原生的性能，采用用户模式网络和 SSH 端口转发。

**Windows (Hyper-V)** 支持计划中。详情请参阅 [issue #380](https://github.com/rediacc/console/issues/380)。需要 Windows Pro/Enterprise。

## 前提条件和设置

### Linux

```bash
# Install prerequisites automatically
rdc ops setup

# Or manually:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Install prerequisites automatically
rdc ops setup

# Or manually:
brew install qemu cdrtools
```

### 验证设置

```bash
rdc ops check
```

此命令运行特定于平台的检查，并报告每个前提条件的通过/失败状态。

## 快速入门

```bash
# 1. Check prerequisites
rdc ops check

# 2. Provision a minimal cluster (bridge + 1 worker)
rdc ops up --basic

# 3. Check VM status
rdc ops status

# 4. SSH into the bridge VM
rdc ops ssh 1

# 5. Tear down
rdc ops down
```

## 集群组成

默认情况下，`rdc ops up` 会配置：

| 虚拟机 | ID | 角色 |
|----|-----|------|
| Bridge | 1 | 主节点 — 运行 Rediacc 桥接服务 |
| Worker 1 | 11 | 工作节点，用于仓库部署 |
| Worker 2 | 12 | 工作节点，用于仓库部署 |

使用 `--basic` 标志仅配置桥接节点和第一个工作节点（ID 1 和 11）。

使用 `--skip-orchestration` 仅配置虚拟机而不启动 Rediacc 服务 — 适用于单独测试 VM 层。

## 配置

环境变量控制 VM 资源：

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `VM_CPU` | 2 | 每个 VM 的 CPU 核心数 |
| `VM_RAM` | 4096 | 每个 VM 的内存（MB） |
| `VM_DSK` | 16 | 磁盘大小（GB） |
| `VM_NET_BASE` | 192.168.111 | 网络基址（仅 KVM） |
| `RENET_DATA_DIR` | ~/.renet | VM 磁盘和配置的数据目录 |

## 命令参考

| 命令 | 说明 |
|---------|-------------|
| `rdc ops setup` | 安装平台前提条件（KVM 或 QEMU） |
| `rdc ops check` | 验证前提条件已安装且正常工作 |
| `rdc ops up [options]` | 配置 VM 集群 |
| `rdc ops down` | 销毁所有虚拟机并清理 |
| `rdc ops status` | 显示所有虚拟机的状态 |
| `rdc ops ssh <vm-id>` | 通过 SSH 连接到指定虚拟机 |

### `rdc ops up` 选项

| 选项 | 说明 |
|--------|-------------|
| `--basic` | 最小集群（桥接节点 + 1 个工作节点） |
| `--lite` | 轻量级资源 |
| `--force` | 强制重新创建现有虚拟机 |
| `--parallel` | 并行配置虚拟机 |
| `--skip-orchestration` | 仅虚拟机，不启动 Rediacc 服务 |
| `--backend <kvm\|qemu>` | 覆盖自动检测的后端 |
| `--os <name>` | 操作系统镜像（默认：ubuntu-24.04） |
| `--debug` | 详细输出 |

## 平台差异

### Linux (KVM)
- 使用 libvirt 进行 VM 生命周期管理
- 桥接网络 — 虚拟机在虚拟网络上获取 IP（192.168.111.x）
- 直接通过 SSH 连接到 VM IP
- 需要 `/dev/kvm` 和 libvirtd 服务

### macOS (QEMU + HVF)
- 使用通过 PID 文件管理的 QEMU 进程
- 用户模式网络，带 SSH 端口转发（localhost:222XX）
- 通过转发端口进行 SSH 连接，而非直接 IP
- Cloud-init ISO 通过 `mkisofs` 创建

## 故障排除

### 调试模式

在任意命令中添加 `--debug` 以获取详细输出：

```bash
rdc ops up --basic --debug
```

### 常见问题

**KVM 不可用 (Linux)**
- 检查 `/dev/kvm` 是否存在：`ls -la /dev/kvm`
- 在 BIOS/UEFI 中启用虚拟化
- 加载内核模块：`sudo modprobe kvm_intel` 或 `sudo modprobe kvm_amd`

**libvirtd 未运行 (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU 未找到 (macOS)**
```bash
brew install qemu cdrtools
```

**虚拟机无法启动**
- 检查 `~/.renet/disks/` 中的磁盘空间
- 运行 `rdc ops check` 验证所有前提条件
- 尝试 `rdc ops down` 然后 `rdc ops up --force`
