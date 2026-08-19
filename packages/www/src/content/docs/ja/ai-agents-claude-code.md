---
title: Claude Code セットアップガイド
description: Claude CodeをRediaccインフラストラクチャの自律管理用に設定するためのステップバイステップガイド。
category: Guides
tags:
  - ai-agents
  - cli
order: 31
language: ja
sourceHash: "2c925f7e46d63e9a"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Claude Codeは `rdc` CLIを通じてRediaccとネイティブに連携します。このガイドでは、セットアップ、権限、一般的なワークフローについて説明します。

## クイックセットアップ

1. CLIをインストール: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md テンプレート](/ja/docs/agents-md-template)をプロジェクトルートに `CLAUDE.md` としてコピー
3. プロジェクトディレクトリでClaude Codeを起動

Claude Codeは起動時に `CLAUDE.md` を読み込み、すべてのインタラクションの永続的なコンテキストとして使用します。

## CLAUDE.md の設定

プロジェクトルートに配置してください。完全版は [AGENTS.md テンプレート](/ja/docs/agents-md-template) を参照してください。主要なセクション:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## ツールの権限

Claude Codeは `rdc` コマンドの実行許可を要求します。一般的な操作をClaude Codeの設定で事前に許可できます:

- `rdc machine status *` を許可, 読み取り専用のステータス確認
- `rdc machine status * --containers` を許可, コンテナ一覧の取得
- `rdc machine health *` を許可, ヘルスチェック
- `rdc repo list` を許可, リポジトリ一覧の取得

破壊的な操作（`rdc repo up`、`rdc repo delete`）については、明示的に許可しない限り、Claude Codeは常に確認を求めます。

## ワークフローの例

### インフラストラクチャのステータス確認

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### リポジトリのデプロイ

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### コンテナの問題診断

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### ファイル同期

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## ヒント

- Claude Codeは非TTYを自動検出してJSON出力に切り替えます, ほとんどの場合 `-o json` の指定は不要です
- `rdc --help-all` を使用すると、Claude Codeが利用可能なすべてのコマンドを発見できます
- `--fields` フラグを使用すると、特定のデータのみが必要な場合にコンテキストウィンドウの使用量を抑えられます
