---
title: AIエージェントの安全性とガードレール
description: 'RediaccのCLIがAIコーディングアシスタントによるシークレット漏洩、認証情報の上書き、権限昇格を防ぐ仕組み: ナレッジゲート、秘匿化、祖先検証済みオーバーライド、ハッシュ連鎖監査ログ。'
category: Concepts
order: 35
language: ja
sourceHash: "6a4f4ccd6ae806ee"
sourceCommit: "4bef9a170fb07db00a4ee2ef504aa27706bcd15a"
---

Claude Code、Cursor、Gemini CLI、Copilot CLI、またはその他のAIコーディングアシスタントが `rdc` を操作する場合、CLIはキーボードを操作する人間とは異なる扱いをします。このページでは、エージェントができること・できないこと、そしてエージェントがガードレールを回避しようとしても保護が機能する仕組みについて説明します。

## クイックリファレンス: エージェントができること・できないこと

| 操作 | エージェントのデフォルト | 特定のユースケースでの解除方法 |
|---|---|---|
| `rdc config show`（秘匿化済み） | ✅ allowed |  |
| `rdc config field get --pointer <pointer>`（秘匿化スタブまたはダイジェスト） | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（公開フィールド） | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（機密フィールド、**正しい `--current` あり**） | ✅ allowed |  |
| `rdc config edit --dump`（秘匿化済みJSONC） | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（機密フィールド、`--current` なし） | 🔴 refused | `--current "<古い値>"` を指定する |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | 代わりに `--digest` を使用する |
| `rdc config show --reveal` | 🔴 refused | オプションなしの `rdc config show` を使用する |
| `rdc config edit`（インタラクティブエディタ） | 🔴 refused | エージェント起動前に人間が `REDIACC_ALLOW_CONFIG_EDIT=*` を設定する |
| `rdc config edit --apply <file>` | 🔴 refused | 同じオーバーライド |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | 同じオーバーライド。インタラクティブ確認を使用 |
| `rdc term connect -m <machine>`（マシンへの直接SSH） | 🔴 refused | 最初にリポジトリをフォークしてフォークに接続する |

エージェントが拒否されたすべての操作は `outcome: refused` と理由とともに監査ログに記録されます。

## エージェントの検出方法

CLIは以下のいずれかに該当する場合、プロセスをエージェントとして扱います：

- `REDIACC_AGENT`、`CLAUDECODE`、`GEMINI_CLI`、`COPILOT_CLI` のいずれかが `"1"` に設定されている、または `CURSOR_TRACE_ID` が設定されている。
- Linux上：祖先チェーン上の親プロセスがそれらの変数のいずれかを環境変数として持っている（`/proc/<pid>/environ` 経由）。エージェントが `env -i` やラッパースクリプトで自分の変数を削除しても、親チェーンがCLIに誰が起動したかを伝えます。

検出はプロセスごとに一度実行されてキャッシュされます。無効化することはできません。

## ナレッジゲートモデル

機密変更は `passwd(1)` の慣例に従います：シークレットを変更するには、すでに知っていたことを証明してください。

- `/credentials/cfDnsApiToken` に保存されているAPIトークンをローテーションしたい場合
- CLIが「現在の値は何ですか？」と尋ねます
- エージェントは `--current "$OLD"` でプレーンテキストを提供します。CLIは `$OLD` をSHA-256でハッシュ化し、現在保存されている値のダイジェストと比較します。一致 → 書き込み実行。不一致 → 拒否、監査記録。

モデルはシンプルですが、3つの攻撃面を閉じます：

1. **サイレントローテーション**：`$OLD` への事前アクセスがないエージェントは、自分の値で置き換えることができません。
2. **プローブによる漏洩**：ダイジェストの応答にプレーンテキストは含まれません。侵害された監査ログでも `expected abc12345…, got deadbeef…` と表示され、基礎となる値は見えません。
3. **ユーザー設定の誤上書き**：毎回意図的な `--current` が必要です。`set` での自動上書きはありません。

### 実例

```bash
# 秘匿化スタブの短いダイジェストを取得する（エージェントに安全）。
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 証明なしに上書きを試みる: 拒否。
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# 現在のプレーンテキストを提供する: 許可。
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

エージェントが `$OLD_CF_TOKEN` を持っていない場合、前提条件を満たすことができず、ローテーションは拒否されます。それを持っているユーザーは、エディタまたはシェルから `--current` を渡して操作できます。

## デフォルトの秘匿化

機密状態を読む `rdc` コマンド: `config show`、`config field get`、`config machine list`、`config edit --dump`: はシークレットフィールドに対してプレーンテキストではなく **秘匿化スタブ** を返します：

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

スタブの8文字の16進サフィックスは `sha256(canonicalize(value))` の最初の8文字です。一見して2つの異なる値を区別するには十分ですが、逆算には不十分です。エージェントはスタブを使って、値を見ることなく値が変わったかどうかを追跡できます。

`--reveal` はインタラクティブなTTY上の人間に対して秘匿化を解除します。エージェントはTTYの状態に関係なく拒否されます。各許可は `reveal_granted` 監査エントリを書き込み、各拒否はアクターのエージェントシグナルが添付された `refused` エントリを書き込みます。

## `REDIACC_ALLOW_CONFIG_EDIT` オーバーライド

インタラクティブエディタ、`--apply`、`field rotate` などの一部の操作は人間向けに存在し、エージェントに安全なパスがありません。エージェントにそれらを実行させたい場合は、次のように設定します：

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # 完全なバイパス
# または
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# （カンマ区切りのスコープグロブ: セグメントごとに * ワイルドカード使用可）
```

…エージェントはこれを継承します。

**重要な詳細**：オーバーライドは祖先チェーンでエージェントより **上** のプロセスに存在する必要があります。エージェントが自分の環境（またはスポーンしたサブシェル）に設定した場合、CLIは拒否してその旨を通知します：

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

効果：エージェントはセッション途中で `export REDIACC_ALLOW_CONFIG_EDIT='*'` を実行してガードレールを回避することはできません。親プロセス（エージェント起動前のあなたのターミナル）のみがそのドアを開けることができます。

## 監査ログ

すべての変更、すべての拒否、すべての `--reveal` 許可は `~/.config/rediacc/audit.log.jsonl`（モード `0600`、10MBでローテーション）にJSONL行として書き込まれます。各行はハッシュ連鎖されています：`prevHash` フィールドは `sha256("<前の行>")` です。いずれかの行を改ざんすると、以降のすべての行でチェーンが壊れます。

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### 検査

```bash
# 最近のエントリを一覧表示
rdc config audit log --since 24h

# ポインターグロブでフィルタリング
rdc config audit log --path '/credentials/*'

# エージェント発のエントリのみ
rdc config audit log --actor agent

# 新しいエントリをライブストリーミング（Ctrl+Cで停止）
rdc config audit tail

# ハッシュチェーンが完全かどうか確認
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   または
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### 監査ログに絶対に表示されないもの

- プレーンテキストのシークレット値
- パスフレーズ、トークン、SSHキー
- `--current` 前提条件の不一致での新旧値（8文字のダイジェストプレフィックスのみ）

ログはセキュリティレビュアーへの共有やバグレポートへの添付に安全に使用できます。

## 動作モデルの限界

エージェントのガードレールは**動作的なもので、暗号学的なものではありません**。設定ファイルと同じUIDで実行される決意のあるエージェントは常に `cat ~/.config/rediacc/rediacc.json` を実行してプレーンテキストを読むことができます。ファイルがプロセスから読み取れるためです。

実際の暗号学的強制には、[暗号化された設定ストア](/ja/docs/config-storage) を使用してください：シークレットはサーバー側に保存され、各機密フィールドはフィールドごとのHMACコミットメントを持ち、アカウントワーカーは `--current` 前提条件がストアのハッシュと一致しない書き込みを拒否します。サーバーはプレーンテキストを見ることはありません: ゼロ知識: ですが、ゲートは強制します。

ローカルファイルパスは「簡単な道は安全」。リモートストアパスは「難しい道も難しい」。

## クイックレシピ

### エージェントに単一のクラウドトークンのローテーションを許可する

```bash
# あなた自身として、エージェント起動前に：
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # または cursor、gemini など
```

これでエージェントは `config field rotate /credentials/cfDnsApiToken --new …` を実行できますが、`/credentials/ssh/privateKey` の編集やインタラクティブエディタの起動は引き続き不可能です。

### エージェントに幅広い設定編集セッションを許可する

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

エージェントは `rdc config edit` を開き、`--reveal` を使用して `field rotate` を実行できます。すべてのアクションは引き続き `actor.kind: agent` と `CLAUDECODE` シグナルとともに監査ログに記録されます。

### エージェントが触れることのできるフィールドを確認する

```bash
rdc config field list --sensitive --output json
```

すべてのポインターテンプレート、その種類（`secret` / `credential` / `pii` / `identifier`）、およびサーバー側のHMACエンベロープにコミットされているかどうかを返します。

## 関連項目

- [AIエージェント統合の概要](/ja/docs/ai-agents-overview): トップレベルのツアー
- [Claude Code のセットアップ](/ja/docs/ai-agents-claude-code): 統合テンプレート
- [JSON出力エンベロープ](/ja/docs/ai-agents-json-output): マシン可読レスポンス
- [暗号化された設定ストア](/ja/docs/config-storage): サーバー側の暗号学的強制
- [アカウントセキュリティ](/ja/docs/account-security): オペレーター向けのセキュリティ体制
