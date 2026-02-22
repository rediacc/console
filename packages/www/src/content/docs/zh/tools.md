---
title: 工具
description: 文件同步、终端访问、VS Code 集成、更新和诊断。
category: Guides
order: 8
language: zh
sourceHash: 80ca3cd3e1a55d4b
---

# 工具

Rediacc 包含用于远程仓库操作的生产力工具：文件同步、SSH 终端、VS Code 集成和 CLI 更新。

## 文件同步 (sync)

使用基于 SSH 的 rsync 在工作站和远程仓库之间传输文件。

### 上传文件

```bash
rdc sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### 下载文件

```bash
rdc sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### 检查同步状态

```bash
rdc sync status -m server-1 -r my-app
```

### 选项

| 选项 | 说明 |
|--------|-------------|
| `-m, --machine <name>` | 目标机器 |
| `-r, --repository <name>` | 目标仓库 |
| `--local <path>` | 本地目录路径 |
| `--remote <path>` | 远程路径（相对于仓库挂载点） |
| `--dry-run` | 预览更改，不实际传输 |
| `--mirror` | 将源镜像到目标（删除多余文件） |
| `--verify` | 传输后验证校验和 |
| `--confirm` | 交互式确认，带详细视图 |
| `--exclude <patterns...>` | 排除文件模式 |
| `--skip-router-restart` | 操作后跳过重启路由服务器 |

## SSH 终端 (term)

打开到机器或仓库环境的交互式 SSH 会话。

### 简写语法

最快的连接方式：

```bash
rdc term server-1                    # 连接到机器
rdc term server-1 my-app             # 连接到仓库
```

### 运行命令

无需打开交互式会话即可执行命令：

```bash
rdc term server-1 -c "uptime"
rdc term server-1 my-app -c "docker ps"
```

连接到仓库时，`DOCKER_HOST` 会自动设置为该仓库的隔离 Docker 套接字，因此 `docker ps` 只显示该仓库的容器。

### connect 子命令

`connect` 子命令通过显式标志提供相同的功能：

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### 容器操作

直接与运行中的容器交互：

```bash
# 在容器内打开 shell
rdc term server-1 my-app --container <container-id>

# 查看容器日志
rdc term server-1 my-app --container <container-id> --container-action logs

# 实时跟踪日志
rdc term server-1 my-app --container <container-id> --container-action logs --follow

# 查看容器统计信息
rdc term server-1 my-app --container <container-id> --container-action stats

# 在容器中执行命令
rdc term server-1 my-app --container <container-id> --container-action exec -c "ls -la"
```

| 选项 | 说明 |
|--------|-------------|
| `--container <id>` | 目标 Docker 容器 ID |
| `--container-action <action>` | 操作：`terminal`（默认）、`logs`、`stats`、`exec` |
| `--log-lines <n>` | 显示的日志行数（默认：50） |
| `--follow` | 持续跟踪日志 |
| `--external` | 使用外部终端而非内联 SSH |

## VS Code 集成 (vscode)

在 VS Code 中打开远程 SSH 会话，已预配置正确的 SSH 设置。

### 连接到仓库

```bash
rdc vscode connect my-app -m server-1
```

此命令会：
1. 检测您的 VS Code 安装
2. 在 `~/.ssh/config` 中配置 SSH 连接
3. 为会话持久化 SSH 密钥
4. 使用远程 SSH 连接打开 VS Code 到仓库路径

### 列出已配置的连接

```bash
rdc vscode list
```

### 清理连接

```bash
rdc vscode clean
```

移除不再需要的 VS Code SSH 配置。

### 检查配置

```bash
rdc vscode check
```

验证 VS Code 安装、Remote SSH 扩展和活动连接。

> **前提条件：** 在 VS Code 中安装 [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) 扩展。

## CLI 更新 (update)

保持 `rdc` CLI 为最新版本。

### 检查更新

```bash
rdc update --check-only
```

### 应用更新

```bash
rdc update
```

更新会就地下载并应用。CLI 会自动为您的平台（Linux、macOS 或 Windows）选择正确的二进制文件。新版本将在下次运行时生效。

### 回滚

```bash
rdc update rollback
```

恢复到之前安装的版本。仅在应用更新后可用。

### 更新状态

```bash
rdc update status
```

显示当前版本、更新通道和自动更新配置。
