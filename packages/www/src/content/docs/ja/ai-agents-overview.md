---
title: AIエージェント統合の概要
description: "Claude Code、Cursor、Clineが rdc を通じてRediaccインフラを管理する方法: JSON出力、エージェントイントロスペクション、安全ガードレール。"
category: Guides
order: 30
language: ja
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

`rdc` はもともとエージェントを念頭に置いて設計されています。Claude Code、Cursor、Cline など、サブシェルで `rdc` を呼び出すAIアシスタントはいずれも、構造化されたJSON出力、機械可読なエラー、そして自律的なRediaccインフラ管理に必要なガードレールを自動的に受け取ります。統合の仕組みを以下に説明します。

## なぜセルフホスト + AIエージェントなのか

Rediaccのアーキテクチャはエージェントに適しています:

- **CLIファースト**: すべての操作が `rdc` コマンド、GUIは不要
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

配置するだけで、エージェントは推測せずに動作するために必要な完全なコマンドリファレンス、アーキテクチャコンテキスト、および規約を取得できます。

### 2. JSON出力パイプライン

エージェントがサブシェルで `rdc` を呼び出すと、出力は自動的にJSONに切り替わります（非TTY検出）。すべてのJSONレスポンスは一貫したエンベロープを使用します:

```json
{
  "success": true,
  "command": "machine query",
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
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. エージェント機能の検出

`rdc agent` サブコマンドは構造化されたイントロスペクションを提供します:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## エージェント向けの主要フラグ

| フラグ | 用途 |
|------|---------|
| `--output json` / `-o json` | 機械可読なJSON出力 |
| `--yes` / `-y` | インタラクティブな確認をスキップ |
| `--quiet` / `-q` | 情報的なstderr出力を抑制 |
| `--fields name,status` | 出力を特定のフィールドに限定 |
| `--dry-run` | 破壊的操作を実行せずにプレビュー |

## 安全性とガードレール

CLIはターミナルの人間とエージェントを同一視しません。機密性の高い操作には、現在の状態を既に把握していることの証明（`--current` フラグ）が必要です。インタラクティブエディタのフローはデフォルトで拒否され、すべての拒否は監査ログに記録されます。[AIエージェントの安全性とガードレール](/ja/docs/ai-agents-safety)のリファレンスには、ファイアウォールテーブル全体、ナレッジゲートモデル、`REDIACC_ALLOW_CONFIG_EDIT` スコープオーバーライド、ハッシュチェーン監査ログの詳細が記載されています。

## 次のステップ

- [AIエージェントの安全性とガードレール](/ja/docs/ai-agents-safety), エージェントができることとできないこと、ナレッジゲート、監査ログ
- [Claude Code セットアップガイド](/ja/docs/ai-agents-claude-code), Claude Codeのステップバイステップ設定
- [Cursor セットアップガイド](/ja/docs/ai-agents-cursor), Cursor IDE統合
- [JSON出力リファレンス](/ja/docs/ai-agents-json-output), JSON出力の完全なドキュメント
- [AGENTS.md テンプレート](/ja/docs/agents-md-template), コピー＆ペースト用エージェント設定テンプレート
