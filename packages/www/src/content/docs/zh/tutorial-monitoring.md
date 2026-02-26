---
title: "监控与诊断"
description: "一起观看和操作：检查机器健康状况、检查容器、查看服务和运行诊断。"
category: "Tutorials"
order: 4
language: zh
sourceHash: "e121e29d9a6359bc"
---

# 教程: 监控与诊断

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/zh/docs/tutorial-repos))

## 交互式录像

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## 内容说明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### 步骤1: 运行诊断

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### 步骤2: 机器健康检查

```bash
rdc machine health server-1
```

获取全面的健康报告，包括系统运行时间、磁盘使用量、数据存储使用量、容器数量、存储 SMART 状态和已识别的问题。

### 步骤3: 查看运行中的容器

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### 步骤4: 检查 systemd 服务

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### 步骤5: 保险库状态概览

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### 步骤6: 扫描主机密钥

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### 步骤7: 验证连接

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## 后续步骤

- [Monitoring](/zh/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/zh/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/zh/docs/tutorial-tools) — terminal, file sync, and VS Code integration
