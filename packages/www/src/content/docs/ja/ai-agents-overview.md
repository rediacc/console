---
title: AIエージェント統合の概要
description: Claude Code、Cursor、ClineなどのAIコーディングアシスタントが、自律的なデプロイと管理のためにRediaccインフラストラクチャとどのように統合するか。
category: Guides
order: 30
language: ja
sourceHash: "3374e0f154375ffb"
---

AIコーディングアシスタントは、`rdc` CLIを通じてRediaccインフラストラクチャを自律的に管理できます。このガイドでは、統合アプローチと開始方法について説明します。

## なぜセルフホスト + AIエージェントなのか

Rediaccのアーキテクチャは本質的にエージェントフレンドリーです:

- **CLIファースト**: すべての操作が `rdc` コマンド — GUIは不要
- **SSHベース**: トレーニングデータからエージェントが最もよく知っているプロトコル
- **JSON出力**: すべてのコマンドが一貫したエンベロープ付きの `--output json` をサポート
- **Docker分離**: 各リポジトリが独自のデーモンとネットワーク名前空間を持つ
- **スクリプト化可能**: `--yes` で確認をスキップ、`--dry-run` で破壊的操作をプレビュー

## 統合アプローチ

### 1. AGENTS.md / CLAUDE.md テンプレート

最も手軽な開始方法です。[AGENTS.md テンプレート](/ja/docs/agents-md-template)をプロジェクトルートにコピーしてください:

- Claude Code用に `CLAUDE.md`
- Cursor用に `.cursorrules`
- Windsurf用に `.windsurfrules`

これにより、利用可能なコマンド、アーキテクチャ、規約の完全なコンテキストがエージェントに提供されます。

### 2. JSON出力パイプライン

エージェントがサブシェルで `rdc` を呼び出すと、出力は自動的にJSONに切り替わります（非TTY検出）。すべてのJSONレスポンスは一貫したエンベロープを使用します:

```json
{
  "success": true,
  "command": "machine info",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

エラーレスポンスには `retryable` と `guidance` フィールドが含まれます:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
  }]
}
```

### 3. エージェント機能の検出

`rdc agent` サブコマンドは構造化されたイントロスペクションを提供します:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine info"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine info"
```

## エージェント向けの主要フラグ

| フラグ | 用途 |
|------|---------|
| `--output json` / `-o json` | 機械可読なJSON出力 |
| `--yes` / `-y` | インタラクティブな確認をスキップ |
| `--quiet` / `-q` | 情報的なstderr出力を抑制 |
| `--fields name,status` | 出力を特定のフィールドに限定 |
| `--dry-run` | 破壊的操作を実行せずにプレビュー |

## 次のステップ

- [Claude Code セットアップガイド](/ja/docs/ai-agents-claude-code) — Claude Codeのステップバイステップ設定
- [Cursor セットアップガイド](/ja/docs/ai-agents-cursor) — Cursor IDE統合
- [JSON出力リファレンス](/ja/docs/ai-agents-json-output) — JSON出力の完全なドキュメント
- [AGENTS.md テンプレート](/ja/docs/agents-md-template) — コピー＆ペースト用エージェント設定テンプレート
