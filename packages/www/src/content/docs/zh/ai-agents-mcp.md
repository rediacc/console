---
title: MCP 服务器设置
description: 使用模型上下文协议 (MCP) 服务器将 AI 代理连接到 Rediacc 基础设施。
category: Guides
order: 33
language: zh
---

## 概述

`rdc mcp serve` 命令启动一个本地 MCP（模型上下文协议）服务器，AI 代理可以使用该服务器来管理您的基础设施。服务器使用 stdio 传输方式——AI 代理将其作为子进程启动，并通过 JSON-RPC 进行通信。

**前提条件：** 已安装并配置 `rdc`，且至少配置了一台机器。

## Claude Code

添加到项目的 `.mcp.json` 文件中：

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

或使用命名配置：

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

打开设置 → MCP 服务器 → 添加服务器：

- **名称**: `rdc`
- **命令**: `rdc mcp serve`
- **传输方式**: stdio

## 可用工具

### 读取工具（安全，无副作用）

| 工具 | 描述 |
|------|------|
| `machine_info` | 获取系统信息、容器、服务和资源使用情况 |
| `machine_containers` | 列出机器上运行的 Docker 容器 |
| `machine_services` | 列出机器上的 systemd 服务 |
| `machine_repos` | 列出机器上已部署的仓库 |
| `machine_health` | 运行健康检查（系统、容器、服务、存储） |
| `config_repositories` | 列出已配置的仓库及名称到 GUID 的映射 |
| `agent_capabilities` | 列出所有可用的 rdc CLI 命令 |

### 写入工具（具有破坏性）

| 工具 | 描述 |
|------|------|
| `repo_up` | 在机器上部署/更新仓库 |
| `repo_down` | 在机器上停止仓库 |
| `term_exec` | 通过 SSH 在远程机器上执行命令 |

## 示例工作流

**检查机器状态：**
> "我的生产机器状态如何？"

代理调用 `machine_info` → 返回系统信息、运行中的容器、服务和资源使用情况。

**部署应用程序：**
> "在我的预发布机器上部署 gitlab"

代理调用 `repo_up`，参数为 `name: "gitlab"` 和 `machine: "staging"` → 部署仓库，返回成功/失败结果。

**调试故障服务：**
> "我的 nextcloud 很慢，找出问题所在"

代理调用 `machine_health` → `machine_containers` → `term_exec` 读取日志 → 识别问题并建议修复方案。

## 配置选项

| 选项 | 默认值 | 描述 |
|------|--------|------|
| `--config <name>` | （默认配置） | 用于所有命令的命名配置 |
| `--timeout <ms>` | `120000` | 默认命令超时时间（毫秒） |

## 架构

MCP 服务器是无状态的。每次工具调用都会将 `rdc` 作为独立的子进程启动，并使用 `--output json --yes --quiet` 标志。这意味着：

- 工具调用之间不会发生状态泄漏
- 使用您现有的 `rdc` 配置和 SSH 密钥
- 同时支持本地和云端适配器
- 一个命令中的错误不会影响其他命令
