---
title: "本地虚拟机配置"
description: "一起观看和操作：配置本地虚拟机集群、通过 SSH 运行命令并清理环境。"
category: "Tutorials"
order: 1
language: zh
sourceHash: "990c6fd433c7c847"
---

# 教程: 本地虚拟机配置

本教程介绍完整的 `rdc ops` 工作流程：检查系统要求、配置最小虚拟机集群、通过 SSH 在虚拟机上运行命令以及销毁所有资源。

## 前提条件

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/zh/docs/experimental-vms) for setup instructions

## 交互式录像

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## 内容说明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### 步骤1: 验证系统要求

```bash
rdc ops check
```

检查硬件虚拟化支持、所需软件包（libvirt、QEMU）和网络配置。在配置虚拟机之前，此检查必须通过。

### 步骤2: 配置最小虚拟机集群

```bash
rdc ops up --basic --skip-orchestration
```

创建一个双虚拟机集群：一个**桥接**虚拟机（1 CPU、1024 MB 内存、8 GB 磁盘）和一个**工作**虚拟机（2 CPU、4096 MB 内存、16 GB 磁盘）。`--skip-orchestration` 标志跳过 Rediacc 平台配置，仅提供具有 SSH 访问权限的裸虚拟机。

### 步骤3: 检查集群状态

```bash
rdc ops status
```

显示集群中每个虚拟机的状态 — IP 地址、资源分配和运行状态。

### 步骤4: 在虚拟机上运行命令

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

通过 SSH 在桥接虚拟机（ID `1`）上运行命令。您可以在虚拟机 ID 后传递任何命令。要获得交互式 shell，请省略命令：`rdc ops ssh 1`。

### 步骤5: 销毁集群

```bash
rdc ops down
```

销毁所有虚拟机并清理资源。集群可以随时使用 `rdc ops up` 重新配置。

## 后续步骤

- [Experimental VMs](/zh/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/zh/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/zh/docs/quick-start) — deploy a containerized service end-to-end
