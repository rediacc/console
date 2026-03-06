---
title: "仓库生命周期"
description: "创建加密仓库、部署容器化应用、检查容器和清理。"
category: "Tutorials"
order: 3
language: zh
sourceHash: "e6c55c46e8e4cd9c"
---

# 如何使用 Rediacc 部署和管理仓库

仓库是 Rediacc 的核心部署单元——每个仓库都是一个隔离的加密环境，拥有自己的 Docker daemon 和专用存储。在本教程中，您将创建一个加密仓库、部署容器化应用、检查运行中的容器并进行清理。完成后，您将体验完整的部署生命周期。

## 前提条件

- 已安装 `rdc` CLI 并初始化配置
- 已配置的机器（参见[教程：机器设置](/zh/docs/tutorial-setup)）
- 包含 `Rediaccfile` 和 `docker-compose.yml` 的简单应用

## 交互式录像

![教程：仓库生命周期](/assets/tutorials/repos-tutorial.cast)

### 步骤 1：创建加密仓库

每个仓库获得自己的 LUKS 加密存储卷。指定机器和存储大小。

```bash
rdc repo create test-app -m server-1 --size 2G
```

Rediacc 创建一个 2 GB 的加密卷，格式化并自动挂载。仓库已准备好上传文件。

### 步骤 2：列出仓库

确认新仓库可用。

```bash
rdc repo list -m server-1
```

显示机器上的所有仓库及其大小、挂载状态和加密状态。

### 步骤 3：检查挂载路径

在部署之前，验证仓库存储已挂载且可访问。

```bash
rdc term server-1 -c "ls -la /mnt/rediacc/mounts/test-app/"
```

挂载目录是应用文件所在的位置——`Rediaccfile`、`docker-compose.yml` 以及任何数据卷。

### 步骤 4：启动服务

通过挂载仓库并启动其 Docker 服务来部署应用。

```bash
rdc repo up test-app -m server-1 --mount
```

这将挂载仓库（如果尚未挂载），启动隔离的 Docker daemon，通过 `prep()` 拉取镜像，并通过 `up()` 启动服务。

> **注意：** 首次部署需要更长时间，因为需要下载 Docker 镜像。后续启动会重用缓存的镜像。

### 步骤 5：查看运行中的容器

```bash
rdc machine containers server-1
```

显示机器上所有仓库中的所有运行容器，包括 CPU 和内存使用情况。

### 步骤 6：访问仓库终端

要在仓库的隔离 Docker 环境中运行命令：

```bash
rdc term server-1 test-app -c "docker ps"
```

终端会话将 `DOCKER_HOST` 设置为仓库的隔离 Docker 套接字。所有 Docker 命令仅针对该仓库的容器执行。

### 步骤 7：停止并清理

完成后，停止服务、关闭加密卷，并可选择删除仓库。

```bash
rdc repo down test-app -m server-1      # 停止服务
rdc repo unmount test-app -m server-1   # 关闭加密卷
rdc repo delete test-app -m server-1    # 永久删除仓库
```

`down` 停止容器和 Docker daemon。`unmount` 关闭 LUKS 卷。`delete` 永久删除仓库及其加密存储。

> **警告：** `repo delete` 不可逆。仓库中的所有数据将被销毁。如需要，请先创建备份。

## 故障排除

**创建仓库时"磁盘空间不足"**
加密卷需要主机上连续的可用空间。使用服务器上的 `df -h` 检查可用空间。考虑使用更小的 `--size` 值或释放磁盘空间。

**`repo up` 期间 Docker 镜像拉取超时**
大型镜像在慢速连接上可能会超时。使用 `rdc repo up` 重试——它会从中断处继续。对于隔离网络环境，请将镜像预加载到仓库的 Docker daemon 中。

**"挂载失败"或"LUKS 打开失败"**
LUKS 密码短语从配置中派生。验证您使用的是创建仓库时的同一配置。如果卷已被另一个进程挂载，请先卸载它。

## 后续步骤

您已创建加密仓库、部署应用、检查容器并完成清理。要监控您的部署：

- [服务](/zh/docs/services)——Rediaccfile 参考、服务网络、自动启动和多服务布局
- [教程：监控与诊断](/zh/docs/tutorial-monitoring)——健康检查、容器检查和诊断
- [工具](/zh/docs/tools)——终端、文件同步和 VS Code 集成
