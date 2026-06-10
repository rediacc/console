---
title: MCP 服务器设置
description: 使用模型上下文协议 (MCP) 服务器将 AI 代理连接到 Rediacc 基础设施。
category: Guides
order: 33
language: zh
sourceHash: "4483eb3da34a6c03"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## 概述

`rdc mcp serve` 命令启动一个本地 MCP（模型上下文协议）服务器，AI 代理可以使用该服务器管理您的基础设施。服务器使用 stdio 传输方式，代理将其作为子进程启动，并通过 JSON-RPC 进行通信。

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
| `machine_query` | 获取机器的系统信息、容器、服务和资源使用情况 |
| `machine_containers` | 列出 Docker 容器的状态、健康状况、资源使用、标签和自动路由域名 |
| `machine_services` | 列出 rediacc 管理的 systemd 服务（名称、状态、子状态、重启次数、内存、所属仓库） |
| `machine_repos` | 列出已部署的仓库（名称、GUID、大小、挂载状态、Docker 状态、容器数量、磁盘用量、修改日期、Rediaccfile 是否存在） |
| `machine_health` | 对机器执行健康检查（系统、容器、服务、存储） |
| `machine_list` | 列出所有已配置的机器 |
| `config_repositories` | 列出已配置的仓库及其名称与 GUID 的映射关系 |
| `config_show_infra` | 显示机器的基础设施配置（基础域名、公网 IP、TLS、Cloudflare 区域） |
| `config_providers` | 列出用于机器供应的已配置云服务商 |
| `agent_capabilities` | 列出所有可用的 rdc CLI 命令及其参数和选项 |
| `repo_secret_list` | 列出仓库的密钥名称和投递模式（不含值，不含摘要）。只读操作，安全无副作用。 |
| `repo_secret_get` | 获取密钥的 SHA-256 摘要和投递模式。出于设计原因，永远不返回明文值。可用于验证密钥是否存在或已完成轮换。 |

### 写入工具（具有破坏性）

| 工具 | 描述 |
|------|------|
| `repo_create` | 在机器上创建新的加密仓库 |
| `repo_up` | 部署/更新仓库（运行 Rediaccfile up，启动容器）。首次部署或拉取后使用 `mount` |
| `repo_down` | 停止仓库容器。默认不卸载。使用 `unmount` 同时关闭 LUKS 容器 |
| `repo_delete` | 删除仓库（销毁容器、卷和加密镜像）。凭据归档以供恢复 |
| `repo_fork` | 创建具有新 GUID 和 networkId 的 CoW 分叉（完全独立的副本，支持在线分叉） |
| `backup_push` | 将仓库备份推送到存储或其他机器（相同 GUID，备份/迁移，非分叉） |
| `backup_pull` | 从存储或机器拉取仓库备份。拉取后使用 `repo_up`（mount=true）进行部署 |
| `machine_provision` | 使用 OpenTofu 在云服务商上供应新机器 |
| `machine_deprovision` | 销毁云供应的机器并从配置中移除 |
| `config_add_provider` | 添加用于机器供应的云服务商配置 |
| `config_remove_provider` | 移除云服务商配置 |
| `term_exec` | 通过 SSH 在远程机器上执行命令 |

## 示例工作流

**检查机器状态：**
> "我的生产机器状态如何？"

代理调用 `machine_query` → 返回系统信息、运行中的容器、服务和资源使用情况。

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

## 安全

MCP 服务器通过两层保护机制来保障安全：

### 仅分叉模式（默认）

默认情况下，服务器以**仅分叉模式**运行：写入工具（`repo_up`、`repo_down`、`repo_delete`、`backup_push`、`backup_pull`、`term_exec`）只能操作分叉仓库。代理无法修改 grand（原始）仓库，此为设计行为。

> **每个仓库的密钥管理仅限 CLI 操作，此为设计决策。** `repo_secret_set` 和 `repo_secret_unset` 有意**不**作为 MCP 工具暴露。写入操作需要 `--current <previous-value>` 前置条件（或使用 `--rotate-secret` 确认未经验证的轮换），该操作需要人工审核。如果代理需要建议密钥轮换，应先调用 `repo_secret_get` 确认摘要，然后通过 JSON 错误信封中 `next.options[].run` 字段的结构化输出，将面向操作人员的 CLI 命令传递给用户。完整模式请参阅 [AI 代理安全](/en/docs/ai-agents-safety#structured-next-action-hints)，用户操作指南请参阅[仓库 § 密钥](/en/docs/repositories#secrets)。

要允许代理修改 grand 仓库，请在启动托管 MCP 服务器的代理**之前**在终端中导出 `REDIACC_ALLOW_GRAND_REPO`：

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # 一个仓库
# 或 'repo1,repo2,repo3'（条目周围的空白会被忽略），或 '*' 用于所有仓库
claude   # 或 cursor、gemini 等
```

覆盖是根据进程祖先验证的：仅当覆盖已存在于代理进程本身的环境中时才算数，这意味着你在代理（以及它启动的 MCP 服务器）启动之前导出了它。代理无法通过在会话中途设置该变量来自我授予访问权限。故意没有服务器标志用于此目的：MCP 服务器参数中的标志不能证明是谁设置的，而祖先检查可以。机器级访问（例如 `term connect -m <machine>` 不指定仓库）仍需要 `*`；仓库名称列表无法解锁该权限。

### 每仓库 SSH 密钥与服务端沙箱

每个仓库都有独立的 SSH 密钥对。公钥部署到 `authorized_keys` 时带有 `command=` 前缀，强制所有 SSH 会话通过 `renet sandbox-gateway <repo-name>` 进行，这是一个服务端 ForceCommand，任何客户端（包括 VS Code）都无法绕过。

**工作原理：**
1. `rdc repo create` 或 `rdc repo fork` 为每个仓库生成独立的 ed25519 密钥对
2. 公钥以 `command="renet sandbox-gateway <name>"` 形式部署到远端
3. 使用该密钥的所有 SSH 连接均通过网关，网关会执行：
   - **Landlock LSM**，内核级文件系统限制，作用范围为仓库的挂载路径
   - **OverlayFS 家目录覆盖**，对 `$HOME` 的写入按仓库捕获，读取则穿透到真实家目录
   - **每仓库 TMPDIR**，位于 `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Docker 访问**，通过仓库隔离的 Docker socket
   - **权限降级**，切换到通用用户（`rediacc`）
4. 仓库的 `.envrc` 会自动加载，用于 Docker 和环境配置

**允许读写（RW）**：仓库挂载路径、每仓库沙箱工作区、家目录（通过覆盖层）、Docker socket
**允许只读（RO）**：系统路径（`/usr`、`/bin`、`/etc`、`/proc`、`/sys`）
**阻止**：其他仓库的挂载路径、允许列表之外的系统文件

**VS Code 集成**：每个仓库在 `<datastore>/.interim/sandbox/<name>/.vscode-server/` 目录下拥有独立的 VS Code 服务器实例。多个仓库可同时打开，各自拥有独立的沙箱环境，仓库之间不共享服务器。

这可以防止横向移动。即使代理获得了对某个分叉的 shell 访问权限，也无法读取或修改同一机器上的其他仓库。机器级 SSH（不指定仓库）使用团队密钥，不受沙箱限制。

## 架构

MCP 服务器是无状态的。每次工具调用都会将 `rdc` 作为独立的子进程启动，并使用 `--output json --yes --quiet` 标志。这意味着：

- 工具调用之间不会发生状态泄漏
- 使用您现有的 `rdc` 配置和 SSH 密钥
- 同时支持本地和云端适配器
- 一个命令中的错误不会影响其他命令
