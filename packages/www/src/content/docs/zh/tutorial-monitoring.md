---
title: "监控与诊断"
description: "检查机器健康状况、检查容器、查看 systemd 服务、扫描主机密钥和运行环境诊断。"
category: "Tutorials"
order: 4
language: zh
sourceHash: "af9f17a05dfb13b9"
---

# 如何使用 Rediacc 监控和诊断基础设施

保持基础设施健康需要对机器状态、容器状态和服务健康状况有清晰的了解。在本教程中，您将运行环境诊断、检查机器健康状况、检查容器和服务、查看保险库状态并验证连接。完成后，您将知道如何在整个基础设施中识别和调查问题。

## 前提条件

- 已安装 `rdc` CLI 并初始化配置
- 一台已配置的机器，至少有一个正在运行的仓库（参见[教程: 仓库生命周期](/zh/docs/tutorial-repos)）

## 交互式录像

![教程: 监控与诊断](/assets/tutorials/monitoring-tutorial.cast)

### 步骤1: 运行诊断

首先检查您的本地环境是否存在配置问题。

```bash
rdc doctor
```

检查 Node.js、CLI 版本、renet 二进制文件、配置和虚拟化支持。每项检查报告 **OK**、**Warning** 或 **Error**。

### 步骤2: 机器健康检查

```bash
rdc machine health server-1
```

从远程机器获取全面的健康报告：系统运行时间、磁盘使用量、数据存储使用量、容器数量、存储 SMART 状态和已识别的问题。

### 步骤3: 查看运行中的容器

```bash
rdc machine containers server-1
```

列出机器上所有仓库中所有运行中的容器，显示名称、状态、运行状态、健康状况、CPU 使用量、内存使用量以及每个容器所属的仓库。

### 步骤4: 检查 systemd 服务

要查看支撑每个仓库的 Docker daemon 和网络的底层服务：

```bash
rdc machine services server-1
```

列出与 Rediacc 相关的 systemd 服务（Docker daemon、loopback 别名）及其状态、子状态、重启次数和内存使用量。

### 步骤5: 保险库状态概览

```bash
rdc machine vault-status server-1
```

提供机器的高级概览：主机名、运行时间、内存、磁盘、数据存储和仓库总数。

### 步骤6: 扫描主机密钥

如果机器被重建或其 IP 发生变化，请刷新存储的 SSH 主机密钥。

```bash
rdc config machine scan-keys server-1
```

获取服务器当前的主机密钥并更新您的配置。这可以防止"host key verification failed"错误。

### 步骤7: 验证连接

快速 SSH 连接检查，确认机器可达并正在响应。

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

主机名确认您连接到了正确的服务器。运行时间确认系统正常运行。

## 故障排除

**健康检查超时或显示"SSH connection failed"**
验证机器在线且可达：`ping <ip>`。使用 `rdc term <machine> -c "echo ok"` 检查您的 SSH 密钥是否配置正确。

**服务列表中显示"Service not found"**
Rediacc 服务仅在部署至少一个仓库后才会出现。如果没有仓库，服务列表为空。

**容器列表显示过时或已停止的容器**
如果 `repo down` 未干净执行，之前部署的容器可能会残留。使用 `rdc repo down <repo> -m <machine>` 停止它们，或通过 `rdc term <machine> <repo> -c "docker ps -a"` 直接检查。

## 后续步骤

您已运行诊断、检查了机器健康状况、检查了容器和服务并验证了连接。要使用您的部署：

- [监控](/zh/docs/monitoring) — 所有监控命令的完整参考
- [故障排除](/zh/docs/troubleshooting) — 常见问题和解决方案
- [教程: 工具](/zh/docs/tutorial-tools) — 终端、文件同步和 VS Code 集成
