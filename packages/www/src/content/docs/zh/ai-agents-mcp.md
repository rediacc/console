---
title: MCP 服务器设置
description: 使用模型上下文协议 (MCP) 服务器将 AI 代理连接到 Rediacc 基础设施。
category: Guides
order: 33
language: zh
sourceHash: "51c5a7f855ead072"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
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
| `machine_info` | Get system info, containers, services, and resource usage for a machine |
| `machine_containers` | List Docker containers with status, health, resource usage, labels, and auto-route domain |
| `machine_services` | List rediacc-managed systemd services (name, state, sub-state, restart count, memory, owning repository) |
| `machine_repos` | List deployed repositories (name, GUID, size, mount status, Docker state, container count, disk usage, modified date, Rediaccfile present) |
| `machine_health` | Run health check on a machine (system, containers, services, storage) |
| `machine_list` | List all configured machines |
| `config_repositories` | List configured repositories with name-to-GUID mappings |
| `config_show_infra` | Show infrastructure configuration for a machine (base domain, public IPs, TLS, Cloudflare zone) |
| `config_providers` | List configured cloud providers for machine provisioning |
| `agent_capabilities` | List all available rdc CLI commands with their arguments and options |

### 写入工具（具有破坏性）

| 工具 | 描述 |
|------|------|
| `repo_create` | Create a new encrypted repository on a machine |
| `repo_up` | Deploy/update a repository (runs Rediaccfile up, starts containers). Use `mount` for first deploy or after pull |
| `repo_down` | Stop repository containers. Does NOT unmount by default. Use `unmount` to also close the LUKS container |
| `repo_delete` | Delete a repository (destroys containers, volumes, encrypted image). Credential archived for recovery |
| `repo_fork` | Create a CoW fork with new GUID and networkId (fully independent copy, online forking supported) |
| `backup_push` | Push repository backup to storage or another machine (same GUID -- backup/migration, not fork) |
| `backup_pull` | Pull repository backup from storage or machine. After pull, deploy with `repo_up` (mount=true) |
| `machine_provision` | Provision a new machine on a cloud provider using OpenTofu |
| `machine_deprovision` | Destroy a cloud-provisioned machine and remove from config |
| `config_add_provider` | Add a cloud provider configuration for machine provisioning |
| `config_remove_provider` | Remove a cloud provider configuration |
| `term_exec` | Execute a command on a remote machine via SSH |

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
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## 安全

The MCP server enforces two layers of protection:

### Fork-only mode (default)

By default, the server runs in **fork-only mode** — write tools (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) can only operate on fork repositories. Grand (original) repositories are protected from agent modifications.

To allow an agent to modify grand repos, start with `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

你也可以将环境变量 `REDIACC_ALLOW_GRAND_REPO` 设置为某个特定仓库名称，或设置为适用于所有仓库的 `*`。

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## 架构

MCP 服务器是无状态的。每次工具调用都会将 `rdc` 作为独立的子进程启动，并使用 `--output json --yes --quiet` 标志。这意味着：

- 工具调用之间不会发生状态泄漏
- 使用您现有的 `rdc` 配置和 SSH 密钥
- 同时支持本地和云端适配器
- 一个命令中的错误不会影响其他命令
