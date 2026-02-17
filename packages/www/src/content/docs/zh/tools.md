---
title: "工具"
description: "文件同步、终端访问、VS Code 集成、更新和诊断。"
category: "Guides"
order: 4
language: zh
---

# 工具

Rediacc 包含多种生产力工具，用于处理远程仓库。这些工具构建在上下文配置所建立的 SSH 连接之上。

## 文件同步（sync）

通过 SSH 使用 rsync 在您的工作站和远程仓库之间传输文件。

### 上传文件

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### 下载文件

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### 选项

| 选项 | 描述 |
|------|------|
| `-m, --machine <name>` | 目标机器 |
| `--local <path>` | 本地目录路径 |
| `--remote <path>` | 远程路径（相对于仓库挂载点） |
| `--dry-run` | 预览更改而不进行传输 |
| `--delete` | 删除目标中在源中不存在的文件 |

`--dry-run` 标志用于在提交同步之前预览将要传输的内容。

## SSH 终端（term）

打开到机器或直接到仓库挂载路径的交互式 SSH 会话。

### 连接到机器

```bash
rdc term connect server-1
```

### 连接到仓库

```bash
rdc term connect my-app -m server-1
```

连接到仓库时，终端会话将在仓库的挂载目录中启动，并配置好仓库的 Docker 套接字。

## VS Code 集成（vscode）

在 VS Code 中打开远程 SSH 会话，预先配置正确的 SSH 设置和 Remote SSH 扩展。

### 连接到仓库

```bash
rdc vscode connect my-app -m server-1
```

此命令：
1. 检测您的 VS Code 安装
2. 在 `~/.ssh/config` 中配置 SSH 连接
3. 为会话持久化 SSH 密钥
4. 使用 Remote SSH 连接打开 VS Code 到仓库路径

### 列出已配置的连接

```bash
rdc vscode list
```

显示所有已为 VS Code 配置的 SSH 连接。

### 清理连接

```bash
rdc vscode clean
```

删除不再需要的 VS Code SSH 配置。

> **前提条件：**在 VS Code 中安装 [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) 扩展。

## CLI 更新（update）

使用最新功能和错误修复保持 `rdc` CLI 为最新版本。

### 检查更新

```bash
rdc update --check-only
```

### 应用更新

```bash
rdc update
```

更新将被下载并就地应用。新版本在下次运行时生效。

### 回滚

```bash
rdc update rollback
```

恢复到之前安装的版本。仅在应用更新后可用。

### 自动更新状态

```bash
rdc update status
```

显示当前版本、更新通道和自动更新配置。

## 系统诊断（doctor）

对您的 Rediacc 环境进行全面的诊断检查。

```bash
rdc doctor
```

doctor 命令检查：

| 类别 | 检查项 |
|------|--------|
| **环境** | Node.js 版本、CLI 版本、SEA 模式 |
| **Renet** | 二进制文件是否存在、版本、嵌入的 CRIU 和 rsync |
| **配置** | 活动上下文、模式、机器、SSH 密钥 |
| **认证** | 登录状态 |

每项检查会报告**正常**、**警告**或**错误**状态，并附带简要说明。排查任何问题时，请将此作为第一步。
