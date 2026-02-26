---
title: "工具"
description: "一起观看和操作：使用终端、文件同步、VS Code 集成和 CLI 更新命令。"
category: "Tutorials"
order: 5
language: zh
sourceHash: "6cf8e14712148f7f"
---

# 教程: 工具

本教程演示了 `rdc` 中内置的生产力工具：SSH 终端访问、文件同步、VS Code 集成和 CLI 更新。

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/zh/docs/tutorial-repos))

## 交互式录像

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## 内容说明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### 步骤1: 连接到机器

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

通过 SSH 在远程机器上运行内联命令。`-c` 标志执行单个命令并返回输出，而不打开交互式会话。

### 步骤2: 连接到仓库

```bash
rdc term server-1 my-app -c "docker ps"
```

连接到仓库时，`DOCKER_HOST` 会自动设置为仓库的隔离 Docker 套接字。任何 Docker 命令仅针对该仓库的容器运行。

### 步骤3: 预览文件同步（模拟运行）

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

`--dry-run` 标志预览将要传输的内容，而不实际上传文件。显示新文件、更改的文件和总传输大小。

### 步骤4: 上传文件

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

通过 SSH 上的 rsync 将文件从本地机器传输到远程仓库挂载点。

### 步骤5: 验证已上传的文件

```bash
rdc term server-1 my-app -c "ls -la"
```

通过列出仓库的挂载目录来确认文件已到达。

### 步骤6: VS Code 集成检查

```bash
rdc vscode check
```

验证您的 VS Code 安装、Remote SSH 扩展和用于远程开发的 SSH 配置。显示需要配置的设置。

### 步骤7: 检查 CLI 更新

```bash
rdc update --check-only
```

检查是否有较新版本的 `rdc` CLI 可用，但不应用更新。使用 `rdc update`（不带 `--check-only`）安装更新。

## 后续步骤

- [Tools](/zh/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/zh/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/zh/docs/services) — Rediaccfile reference and service networking
