---
title: "工具"
description: "使用 SSH 终端访问、文件同步、VS Code 集成和 CLI 更新命令。"
category: "Tutorials"
order: 5
language: zh
sourceHash: "f581499837e09360"
---

# 如何在 Rediacc 中使用终端、同步和 VS Code 工具

CLI 包含日常操作的生产力工具：SSH 终端访问、通过 rsync 进行文件同步、VS Code 远程开发和 CLI 更新。在本教程中，您将运行远程命令、将文件同步到仓库、检查 VS Code 集成并验证您的 CLI 版本。

## 前提条件

- 已安装并初始化配置的 `rdc` CLI
- 具有正在运行的仓库的已配置机器（参见[教程：仓库生命周期](/zh/docs/tutorial-repos)）

## 交互式录像

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### 步骤1：连接到机器

无需打开交互式会话，通过 SSH 在远程机器上运行内联命令。

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

`-c` 标志执行单个命令并返回输出。省略 `-c` 可打开交互式 SSH 会话。

### 步骤2：连接到仓库

要在仓库的隔离 Docker 环境中运行命令：

```bash
rdc term server-1 my-app -c "docker ps"
```

连接到仓库时，`DOCKER_HOST` 会自动设置为仓库的隔离 Docker 套接字。任何 Docker 命令仅针对该仓库的容器运行。

### 步骤3：预览文件同步（模拟运行）

在传输文件之前，预览将会发生的更改。

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

`--dry-run` 标志显示新文件、已更改的文件和总传输大小，而不实际上传任何内容。

### 步骤4：上传文件

将文件从本地机器传输到远程仓库挂载点。

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

文件通过 SSH 上的 rsync 传输。后续上传仅发送更改的文件。

### 步骤5：验证已上传的文件

通过列出仓库的挂载目录来确认文件已到达。

```bash
rdc term server-1 my-app -c "ls -la"
```

### 步骤6：VS Code 集成检查

要使用 VS Code 进行远程开发，请验证所需组件已安装。

```bash
rdc vscode check
```

检查您的 VS Code 安装、Remote SSH 扩展和 SSH 配置。按照输出解决任何缺失的前提条件，然后使用 `rdc vscode <machine> [repo]` 连接。

### 步骤7：检查 CLI 更新

```bash
rdc update --check-only
```

报告是否有更新版本的 CLI 可用。要安装更新，请运行不带 `--check-only` 的 `rdc update`。

## 故障排除

**文件同步期间出现 "rsync: command not found"**
在本地机器和远程服务器上都安装 rsync。在 Debian/Ubuntu 上：`sudo apt install rsync`。在 macOS 上：rsync 默认包含。

**同步上传期间出现 "Permission denied"**
验证您的 SSH 用户对仓库挂载目录具有写入权限。仓库挂载点由机器注册期间指定的用户拥有。

**"VS Code Remote SSH extension not found"**
从 VS Code 市场安装扩展：搜索 Microsoft 的 "Remote - SSH"。安装后，重新启动 VS Code 并再次运行 `rdc vscode check`。

## 后续步骤

您已运行远程命令、同步文件、检查 VS Code 集成并验证了 CLI 更新。要保护您的数据：

- [Tools](/zh/docs/tools) — 终端、同步、VS Code 和更新命令的完整参考
- [教程：备份与网络](/zh/docs/tutorial-backup) — 备份调度和网络配置
- [服务](/zh/docs/services) — Rediaccfile 参考和服务网络
