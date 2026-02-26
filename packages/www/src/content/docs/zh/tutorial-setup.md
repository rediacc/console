---
title: "机器设置"
description: "一起观看和操作：创建配置、添加机器、测试连接、运行诊断和配置基础设施。"
category: "Tutorials"
order: 2
language: zh
sourceHash: "743a5b6abe79a1af"
---

# 教程: 机器设置

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## 前提条件

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## 交互式录像

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## 内容说明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### 步骤1: 创建新配置

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### 步骤2: 查看配置

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### 步骤3: 添加机器

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### 步骤4: 查看机器

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### 步骤5: 设置默认机器

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

设置默认机器，这样后续命令中可以省略 `-m bridge-vm`。

### 步骤6: 测试连接

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### 步骤7: 运行诊断

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### 步骤8: 配置基础设施

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Sets the infrastructure configuration for public-facing services. After setting infra, view the configuration:

```bash
rdc config show-infra bridge-vm
```

Deploy the generated Traefik proxy config to the server with `rdc config push-infra bridge-vm`.

## 后续步骤

- [Machine Setup](/zh/docs/setup) — full reference for all config and setup commands
- [Quick Start](/zh/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/zh/docs/tutorial-repos) — create, deploy, and manage repositories
