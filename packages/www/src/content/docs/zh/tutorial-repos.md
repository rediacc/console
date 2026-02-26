---
title: "仓库生命周期"
description: "一起观看和操作：创建加密仓库、部署容器化应用、检查容器和清理。"
category: "Tutorials"
order: 3
language: zh
sourceHash: "b692ef9f49ac4aa0"
---

# 教程: 仓库生命周期

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/zh/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## 交互式录像

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## 内容说明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### 步骤1: 创建加密仓库

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### 步骤2: 列出仓库

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### 步骤3: 上传应用程序文件

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### 步骤4: 启动服务

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### 步骤5: 查看运行中的容器

```bash
rdc machine containers server-1
```

显示机器上所有仓库中的所有运行容器，包括 CPU 和内存使用情况。

### 步骤6: 通过终端访问仓库

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### 步骤7: 停止并清理

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## 后续步骤

- [Services](/zh/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/zh/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/zh/docs/tools) — terminal, file sync, and VS Code integration
