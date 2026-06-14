---
title: 工具
description: 文件同步、终端访问、VS Code 集成和 CLI 更新。
category: Guides
order: 9
language: zh
sourceHash: "59abc2faa1157369"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# 工具

Rediacc 提供四个工具用于日常远程工作：基于 SSH 的文件同步、SSH 终端、VS Code 集成和 CLI 自更新。四个工具都通过 SSH 运行。远程端无需代理或守护程序。如果您需要图形界面，那么这个页面不是您要找的。

## 文件同步 (sync)

使用 SSH 上的 rsync 在工作站和远程仓库之间传输文件。

### 上传文件

`--local` 接受一个或多个路径。每个路径可以是文件或目录。文件落地到 `<remote>/<basename>`；目录内容合并到 `<remote>/`。对于单个文件，建议使用 `--remote-file` 明确指定文件的目标路径。

```bash
# 目录（内容合并到远程）
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# 单个文件放入远程目录（保留基础名称）
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# 单个文件，明确指定目标路径
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# 一次调用中的多个源
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` 和 `--remote-file` 互斥。`--remote-file` 要求恰好一个 `--local` 路径指向文件。

`--mirror` 不能与文件源组合使用；它会删除远程目录中的同级文件。

### 下载文件

对于目录使用 `--remote`（默认），对于单个文件使用 `--remote-file`。两个标志互斥。

```bash
# 目录
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# 单个文件：--local 必须是现有目录
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### 检查同步状态

```bash
rdc repo sync status -m server-1 -r my-app
```

### 选项

| 选项 | 说明 |
|--------|-------------|
| `-m, --machine <name>` | 目标机器 |
| `-r, --repository <name>` | 目标仓库 |
| `--local <paths...>` | 一个或多个本地文件或目录路径（上传）或本地目标目录（下载） |
| `--remote <path>` | 远程目录（相对于仓库挂载点） |
| `--remote-file <path>` | 远程文件路径，用于单文件上传或下载（`--remote` 的替代项） |
| `--dry-run` | 预览更改，不实际传输 |
| `--mirror` | 将源镜像到目标，删除多余文件（仅限目录源） |
| `--verify` | 传输后验证校验和 |
| `--confirm` | 交互式确认，带详细视图 |
| `--exclude <patterns...>` | 排除文件模式 |
| `--skip-router-restart` | 操作后跳过重启路由服务器 |

## SSH 终端 (term)

打开到机器或仓库环境的交互式 SSH 会话。

### 简写语法

最快的连接方式：

```bash
rdc term connect -m server-1                    # 连接到机器
rdc term connect -m server-1 -r my-app             # 连接到仓库
```

### 运行命令

无需打开交互式会话即可执行命令：

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

连接到仓库时，`DOCKER_HOST` 会自动设置为该仓库的隔离 Docker 套接字，因此 `docker ps` 只显示该仓库的容器。

### connect 子命令

或使用 `connect` 子命令实现相同结果，并带有显式标志：

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### 容器操作

直接与运行中的容器交互：

```bash
# 在容器内打开 shell
rdc term connect -m server-1 -r my-app --container <container-id>

# 查看容器日志
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# 实时跟踪日志
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# 查看容器统计信息
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# 在容器中执行命令
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
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
rdc vscode connect -r my-app -m server-1
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
rdc vscode cleanup
```

移除不再需要的 VS Code SSH 配置。

### 检查配置

```bash
rdc vscode check
```

验证 VS Code 安装、Remote SSH 扩展和活动连接。

> **前提条件：** 在 VS Code 中安装 [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) 扩展。

### 在浏览器中使用 VS Code

没有本地 VS Code？从仓库沙盒内部启动编辑器服务端，在任意浏览器中打开：

```bash
rdc vscode connect -r my-app -m server-1 --browser
```

此命令会：
1. 在机器上一次性安装开源编辑器服务端（只读共享路径，校验和验证）
2. 在仓库沙盒内启动，文件树、集成终端和每个子进程看到的都与仓库看到的完全一致
3. 打开 SSH 隧道到本地端口，并使用每会话令牌 URL 启动浏览器

关闭隧道后服务端继续运行；重新连接时直接复用。管理命令：

```bash
rdc vscode serve status -r my-app -m server-1
rdc vscode serve stop -r my-app -m server-1
```

| 选项 | 说明 |
|--------|-------------|
| `--no-open` | 打印 URL 而不是启动浏览器 |
| `--url-only` | 在标准输出打印一行 URL（用于脚本）并保持隧道连接 |
| `--local <port>` | 选择本地隧道端口 |
| `--server-provider <id>` | 编辑器服务端实现：`openvscode`（默认）或 `code-server` |
| `--server-archive <file>` | 从机器上预置的压缩包安装（无需联网） |

支持 Linux、macOS、Windows 或平板。本地唯一的要求是一个浏览器。

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
rdc update --rollback
```

恢复到之前安装的版本。仅在应用更新后可用。

### 更新状态

```bash
rdc update --status
```

显示当前版本、更新通道和自动更新配置。

#### 发布通道

```bash
rdc update --channel edge      # 连续部署的生产更新
rdc update --channel stable    # 从 edge 经过 7 天稳定期后提升（默认）
rdc update --status            # 显示当前通道和版本信息
```
