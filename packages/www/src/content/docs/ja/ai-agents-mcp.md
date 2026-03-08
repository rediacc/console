---
title: MCPサーバーのセットアップ
description: Model Context Protocol（MCP）サーバーを使用して、AIエージェントをRediacc基盤に接続します。
category: Guides
order: 33
language: ja
sourceHash: "1b6cd5ba5d8d0ffe"
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
| `machine_info` | システム情報、コンテナ、サービス、リソース使用状況を取得 |
| `machine_containers` | マシン上で実行中のDockerコンテナを一覧表示 |
| `machine_services` | マシン上のsystemdサービスを一覧表示 |
| `machine_repos` | マシン上にデプロイされたリポジトリを一覧表示 |
| `machine_health` | ヘルスチェックを実行（システム、コンテナ、サービス、ストレージ） |
| `config_repositories` | 名前からGUIDへのマッピングを含む設定済みリポジトリを一覧表示 |
| `agent_capabilities` | 利用可能なすべてのrdc CLIコマンドを一覧表示 |

### 書き込みツール（破壊的操作）

| Tool | 説明 |
|------|------|
| `repo_up` | マシン上にリポジトリをデプロイ/更新 |
| `repo_down` | マシン上のリポジトリを停止 |
| `term_exec` | SSH経由でリモートマシン上でコマンドを実行 |

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

## アーキテクチャ

MCPサーバーはステートレスです。各ツール呼び出しは `--output json --yes --quiet` フラグを付けて `rdc` を独立した子プロセスとして起動します。これにより:

- ツール呼び出し間で状態が漏洩しない
- 既存の `rdc` 設定とSSH鍵を使用
- ローカルアダプターとクラウドアダプターの両方で動作
- 1つのコマンドのエラーが他に影響しない
