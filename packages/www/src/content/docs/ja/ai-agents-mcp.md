---
title: MCPサーバーのセットアップ
description: Model Context Protocol（MCP）サーバーを使用して、AIエージェントをRediacc基盤に接続します。
category: Guides
order: 33
language: ja
sourceHash: "51c5a7f855ead072"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
---

## 概要

`rdc mcp serve` コマンドは、AIエージェントがインフラストラクチャを管理するために使用できるローカルMCP（Model Context Protocol）サーバーを起動します。サーバーはstdioトランスポートを使用し、AIエージェントがサブプロセスとして起動してJSON-RPCで通信します。

**前提条件:** `rdc` がインストールされ、少なくとも1台のマシンが設定されていること。

## Claude Code

プロジェクトの `.mcp.json` に以下を追加します:

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

名前付きコンフィグを使用する場合:

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

設定 → MCP Servers → サーバーを追加:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## 利用可能なツール

### 読み取りツール（安全、副作用なし）

| Tool | 説明 |
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

### 書き込みツール（破壊的操作）

| Tool | 説明 |
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

## ワークフロー例

**マシンの状態を確認:**
> 「本番マシンの状態はどうなっていますか？」

エージェントが `machine_info` を呼び出し、システム情報、実行中のコンテナ、サービス、リソース使用状況を返します。

**アプリケーションをデプロイ:**
> 「ステージングマシンにgitlabをデプロイして」

エージェントが `repo_up` を `name: "gitlab"` と `machine: "staging"` で呼び出し、リポジトリをデプロイして成功/失敗を返します。

**障害のあるサービスをデバッグ:**
> 「nextcloudが遅いので、原因を調べて」

エージェントが `machine_health` → `machine_containers` → `term_exec` でログを確認し、問題を特定して修正案を提示します。

## 設定オプション

| Option | Default | 説明 |
|--------|---------|------|
| `--config <name>` | （デフォルトコンフィグ） | すべてのコマンドで使用する名前付きコンフィグ |
| `--timeout <ms>` | `120000` | デフォルトのコマンドタイムアウト（ミリ秒） |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## セキュリティ

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

環境変数 `REDIACC_ALLOW_GRAND_REPO` を特定のリポジトリ名、またはすべてのリポジトリに対する `*` に設定することもできます。

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## アーキテクチャ

MCPサーバーはステートレスです。各ツール呼び出しは `--output json --yes --quiet` フラグを付けて `rdc` を独立した子プロセスとして起動します。これにより:

- ツール呼び出し間で状態が漏洩しない
- 既存の `rdc` 設定とSSH鍵を使用
- ローカルアダプターとクラウドアダプターの両方で動作
- 1つのコマンドのエラーが他に影響しない
