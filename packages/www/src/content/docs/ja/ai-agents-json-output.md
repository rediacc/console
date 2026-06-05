---
title: JSON出力リファレンス
description: rdc CLIのJSON出力形式、エンベロープスキーマ、エラー処理、エージェント検出コマンドの完全なリファレンス。
category: Reference
order: 51
language: ja
sourceHash: "9f8d61df26b59757"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

すべての `rdc` コマンドは構造化されたJSONを出力します。スクリプトにパイプするか、エージェントに直接渡してください。

## JSON出力の有効化

### 明示的なフラグ

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### 自動検出

`rdc` が非TTY環境（パイプ、サブシェル、AIエージェントからの起動）で実行されると、出力は自動的にJSONに切り替わります。フラグは不要です。

```bash
# These all produce JSON automatically
result=$(rdc machine query --name prod-1)
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
| `code` | `string` | 機械可読なエラーコード（正規のリストは `ERROR_CODES` 定数を参照） |
| `message` | `string` | 人間が読める説明 |
| `retryable` | `boolean` | 同じコマンドの再試行で成功する可能性があるかどうか |
| `guidance` | `string` | 自由形式のヒント（旧仕様。構造化アクションデータには `next` を推奨） |
| `next` | `object?` | 構造化された次アクションのヒント（存在する場合）。以下を参照 |

### 構造化された `next` アクションヒント

`PRECONDITION_MISMATCH` などの重要なエラーコードでは、エラーオブジェクトにユーザーへ提示すべき正確なコマンドが含まれた `next` フィールドが付加されます。すべてのエラーコードにこのフィールドがあるわけではなく、回復パスが定義されているものにのみ存在します。**エージェントは `next.options[].run` をそのままユーザーに伝えるべきであり、自分でコマンドを合成すべきではありません。**これにより、エージェントが存在しないコマンドを作り出してしまう障害モードを防げます。思いのほか頻繁に起こる問題です。

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

スキーマ:

| フィールド | 型 | 説明 |
|-------|------|-------------|
| `next.summary` | `string` | ユーザーが判断すべき内容を一行で説明 |
| `next.options[]` | `array` | 具体的なアクション。各要素はユーザーが選択できる選択肢 |
| `next.options[].description` | `string` | この選択肢の人間向け説明 |
| `next.options[].run` | `string` | 正確なCLIコマンド。そのままユーザーに伝えること |

### リトライ可能なエラー

以下のエラータイプは `retryable: true` としてマークされます:

- **NETWORK_ERROR**, SSH接続またはネットワーク障害
- **RATE_LIMITED**, リクエスト過多、待機してからリトライ
- **API_ERROR**, 一時的なバックエンド障害

リトライ不可能なエラー（認証、未検出、無効な引数）は、リトライ前に修正アクションが必要です。

## 出力のフィルタリング

`--fields` を使用して出力を特定のキーに限定し、トークン使用量を削減できます:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## ドライラン出力

破壊的なコマンドは `--dry-run` をサポートし、実行前にプレビューできます:

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
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

`rdc agent` サブコマンドは、AIエージェントが実行時に利用可能な操作を発見するための構造化された手段を提供します。

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
rdc agent schema --command "machine query"
```

型やデフォルト値を含む、単一コマンドのすべての引数とオプションの詳細なスキーマを返します。

### JSON経由での実行

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

stdinからJSONを受け取り、キーをコマンドの引数とオプションにマッピングし、JSON出力を強制して実行します。エージェントからCLIへの呼び出しでシェルコマンド文字列を組み立てたくない場合に使用します。

## パースの例

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
