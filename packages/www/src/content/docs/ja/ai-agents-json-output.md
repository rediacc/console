---
title: JSON出力リファレンス
description: rdc CLIのJSON出力形式、エンベロープスキーマ、エラー処理、エージェント検出コマンドの完全なリファレンス。
category: Reference
order: 51
language: ja
sourceHash: "49cfcc5e2e4621a9"
---

すべての `rdc` コマンドは、AIエージェントやスクリプトによるプログラム的な利用のために構造化されたJSON出力をサポートしています。

## JSON出力の有効化

### 明示的なフラグ

```bash
rdc machine query prod-1 --output json
rdc machine query prod-1 -o json
```

### 自動検出

`rdc` が非TTY環境（パイプ、サブシェル、AIエージェントからの起動）で実行されると、出力は自動的にJSONに切り替わります。フラグは不要です。

```bash
# These all produce JSON automatically
result=$(rdc machine query prod-1)
echo '{}' | rdc agent exec "machine query"
```

## JSONエンベロープ

すべてのJSONレスポンスは一貫したエンベロープを使用します:

```json
{
  "success": true,
  "command": "machine query",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| フィールド | 型 | 説明 |
|-------|------|-------------|
| `success` | `boolean` | コマンドが正常に完了したかどうか |
| `command` | `string` | 完全なコマンドパス（例: `"machine query"`、`"repo up"`） |
| `data` | `object \| array \| null` | 成功時のコマンド固有ペイロード、エラー時は `null` |
| `errors` | `array \| null` | 失敗時のエラーオブジェクト、成功時は `null` |
| `warnings` | `string[]` | 実行中に収集された非致命的な警告 |
| `metrics` | `object` | 実行メタデータ |

## エラーレスポンス

失敗したコマンドは、復旧ヒント付きの構造化エラーを返します:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### エラーフィールド

| フィールド | 型 | 説明 |
|-------|------|-------------|
| `code` | `string` | 機械可読なエラーコード |
| `message` | `string` | 人間が読める説明 |
| `retryable` | `boolean` | 同じコマンドの再試行で成功する可能性があるかどうか |
| `guidance` | `string` | エラーを解決するための推奨アクション |

### リトライ可能なエラー

以下のエラータイプは `retryable: true` としてマークされます:

- **NETWORK_ERROR** — SSH接続またはネットワーク障害
- **RATE_LIMITED** — リクエスト過多、待機してからリトライ
- **API_ERROR** — 一時的なバックエンド障害

リトライ不可能なエラー（認証、未検出、無効な引数）は、リトライ前に修正アクションが必要です。

## 出力のフィルタリング

`--fields` を使用して出力を特定のキーに限定できます。特定のデータのみが必要な場合にトークン使用量を削減します:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## ドライラン出力

破壊的なコマンドは `--dry-run` をサポートし、実行前にプレビューできます:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

`--dry-run` をサポートするコマンド: `repo up`、`repo down`、`repo delete`、`snapshot delete`、`sync upload`、`sync download`。

## エージェント検出コマンド

`rdc agent` サブコマンドは、AIエージェントが実行時に利用可能な操作を発見するための構造化されたイントロスペクションを提供します。

### すべてのコマンドの一覧

```bash
rdc agent capabilities
```

引数、オプション、説明を含む完全なコマンドツリーを返します:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine query",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### コマンドスキーマの取得

```bash
rdc agent schema "machine query"
```

型やデフォルト値を含む、単一コマンドの詳細なスキーマを返します。

### JSON経由での実行

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

stdinからJSONを受け取り、キーをコマンドの引数とオプションにマッピングし、JSON出力を強制して実行します。シェルコマンド文字列を構築せずに、エージェントからCLIへの構造化通信に便利です。

## パースの例

### Shell (jq)

```bash
status=$(rdc machine query prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'query', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
