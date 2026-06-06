---
title: AIエージェントの安全性とガードレール
description: >-
  RediaccのCLIがAIコーディングアシスタントによるシークレット漏洩、認証情報の上書き、権限昇格を防ぐ仕組み。ナレッジゲート、秘匿化、祖先検証済みオーバーライド、ハッシュ連鎖監査ログ。
category: Concepts
order: 35
language: ja
sourceHash: "ae23c9bc851ecfcd"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

あなたのインフラストラクチャを管理するAIコーディングアシスタントを使用しているとします。Claude Code、Cursor、Gemini CLI、Copilot CLIなど、AIアシスタントが `rdc` を操作する場合、CLIはキーボードを操作する人間とは異なるルールセットを適用します。このページでは、エージェントが何ができるか・できないか、そしてエージェントがガードレールを回避しようとしても保護が機能する仕組みについて説明します。

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

機密変更は `passwd(1)` の慣例に従います：シークレットを変更するには、すでに知っていたことを証明してください。**人間とエージェント両方に対して対称的です**。両者は同じゲートを通ります。キーボードにいるから特別扱いされるわけではありません。

- `/credentials/cfDnsApiToken` に保存されているAPIトークンをローテーションしたい場合
- CLIが「現在の値は何ですか？」と尋ねます
- エージェント（または人間）が `--current "$OLD"` でプレーンテキストを提供します。CLIは `$OLD` をSHA-256でハッシュ化し、現在保存されている値のダイジェストと比較します。一致 → 書き込み実行。不一致 → 拒否、監査記録。
- 事前の値検証なしでローテーションするには、`--rotate-secret` を渡します（`--current` と相互排他的）。これは監査ログに明示的に記録されます。

このモデルは3つの攻撃面を閉じます：

1. **サイレントローテーション**：呼び出し側（エージェントまたは人間）が `$OLD` への事前アクセスがない場合、それを自分の値で置き換えることはできません。
2. **プローブによる流出**：ダイジェストの応答にプレーンテキストは含まれません。侵害された監査ログでも `expected abc12345…, got deadbeef…` と表示され、基礎となる値は見えません。
3. **本番環境設定への誤上書き**：毎回意図的な `--current` が必要です。TTYでもそれ以外でも例外はありません。「STRIPE_TEST を設定するつもりでも本番シェルにいた」という誤りを防ぎます。

### 構造化された次ステップのヒント

前提条件が失敗した場合、JSONエンベロープ（`--output json`）は構造化された `errors[].next` フィールドを持ち、エージェントに人間が何をすべきか正確に示唆します：

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**エージェントは `next.options[].run` を人間に逐語的に中継すべきです。** これにより「エージェントが存在しないコマンドを作り出す」という失敗モードを避け、オペレーターが実際のアクションを制御できるようにします。

### 実例

```bash
# 秘匿化スタブの短いダイジェストを取得する（エージェントに安全）。
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 証明なしに上書きを試みる：拒否。
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# 現在のプレーンテキストを提供する：許可。
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

エージェントが `$OLD_CF_TOKEN` を持っていない場合、前提条件を満たすことができず、ローテーションは拒否されます。それを持っているユーザーは、エディタを通じて、またはシェルから `--current` を渡して操作できます。

## デフォルトの秘匿化

機密状態を読む `rdc` コマンド：`config show`、`config field get`、`config machine list`、`config edit --dump`：はシークレットフィールドに対してプレーンテキストではなく **秘匿化スタブ** を返します：

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
# （カンマ区切りのスコープグロブ：セグメントごとに * ワイルドカード使用可）
```

…エージェントはこれを継承します。

**重要な詳細**：オーバーライドは祖先チェーンでエージェントより **上** のプロセスに存在する必要があります。エージェントが自分の環境（またはスポーンしたサブシェル）に設定した場合、CLIは拒否してその旨を通知します：

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

効果：エージェントはセッション途中で `export REDIACC_ALLOW_CONFIG_EDIT='*'` を実行してガードレールを回避することはできません。親プロセス（エージェント起動前のあなたのターミナル）のみがそのドアを開けることができます。

## プラットフォームサポート：オーバーライドはLinuxのみ

`REDIACC_ALLOW_CONFIG_EDIT` と `REDIACC_ALLOW_GRAND_REPO` はいずれも、オーバーライドがエージェントによって注入されたものではなくあなた自身によって設定されたものであることを証明するために、祖先検証に依存しています。検証はチェーン上のすべてのプロセスについて `/proc/<pid>/environ` を読み取ります。このファイルはexec時にカーネルによって設定され、プロセス自身が変更することはできません。したがって、親シェルの環境は改ざん不可能な証人となります。

このファイルはmacOSやWindowsには存在しません。正当性を検証する手段がないため、CLIはフェイルクローズします。エージェントを起動する前にシェルでオーバーライドを正しく設定したとしても、オーバーライドは拒否されます。エラーメッセージは何をすべきかを正確に伝えます：

> `The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).`

Linux以外のユーザーはフォークファーストのワークフローからの脱出口を持ちません。これは意図的な設計です。エージェントはどのようにプロンプトされても、サンドボックスを通じて回り込むことはできません。オーバーライドが必要な場合は、WSL、Linuxコンテナ、またはLinux VM内でエージェントを実行してください。それ以外の場合はフォーク上で作業してください。

## 監査ログ

すべての変更、すべての拒否、すべての `--reveal` 許可は `~/.config/rediacc/audit.log.jsonl`（モード `0600`、10MBでローテーション）にJSONL行として書き込まれます。各行はハッシュ連鎖されています：その `prevHash` フィールドは `sha256("<前の行>")` です。いずれかの行を改ざんすると、以降のすべての行でチェーンが壊れます。

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

エージェントのガードレールは **動作的なもので、暗号学的なものではありません**。設定ファイルと同じUIDで実行される決意のあるエージェントは常に `cat ~/.config/rediacc/rediacc.json` を実行してプレーンテキストを読むことができます。ファイルがプロセスから読み取れるためです。

実際の暗号学的強制には、[暗号化された設定ストア](/ja/docs/config-storage) を使用してください：シークレットはサーバー側に保存され、各機密フィールドはフィールドごとのHMACコミットメントを持ち、アカウントワーカーは `--current` 前提条件がストアのハッシュと一致しない書き込みを拒否します。サーバーはプレーンテキストを見ることはありません（ゼロ知識）ですが、ゲートは強制します。

ローカルファイル：簡単な道は安全な道です。リモートストア：難しい道も暗号学的に難しくなります。

## Rediaccが分離しないもの

このページのエージェントガードレールは、Rediacc自身のインフラストラクチャを保護します：設定ファイル、リポジトリごとのDockerデーモン、LUKS暗号化されたリポジトリデータ、スコープ付きSSHサンドボックス。これらは、リポジトリが認証情報を保持している外部サービスを保護するものではありません。

リポジトリのフォークは親のボリュームのBTRFS reflinkです。親のディスク上にあるものは、フォーク内でもバイト単位で同一です。コード、データ、`.env` ファイルもすべて同様です。リポジトリに `STRIPE_LIVE_KEY`、`AWS_ACCESS_KEY_ID`、Railway APIトークン、その他のサードパーティサービス向けの長期的な認証情報が含まれている場合、フォークはそれを継承します。フォークのサンドボックス内で動作するエージェントは、そのファイルを読み取り、値を流出させ、サードパーティAPIを呼び出すために使用できます。サードパーティサービスは、その呼び出しが本番ではなくフォークから来たことを知る術がありません。

これが共有責任の境界線です：

| 境界 | 担当 |
|---|---|
| リポジトリデータ、マウント名前空間、Dockerスコープ、エージェントガード、監査ログ、デプロイ時のシークレット注入 | Rediacc |
| これらのシークレットを使用するアプリケーションコード、およびビルド時にイメージに焼き込まれた認証情報 | リポジトリ開発者 |

主な対策は組み込まれています：**[リポジトリごとのシークレット](/ja/docs/repositories#secrets)** は暗号化されたリポジトリイメージとは別の領域に保存され、フォーク境界を越えてコピーされません。フォークのコンテナは空のシークレットマップでブートし、親とは異なる外部プリンシパルとして自身を識別します。`rdc repo secret set` で設定してください（compose補間用のenvモード、tmpfs `secrets:` ブロック用のfileモード）。変更ゲートは対称的です。人間とエージェント両者が、既存の値を上書きまたは削除するには `--current`（passwd形式の前提条件）または `--rotate-secret`（監査対象のローテーション）を供給する必要があります。

**リポジトリ間の分離は強制されます。** リポジトリBの悪意あるまたは不注意なcompose ファイルは、リポジトリAのシークレットディレクトリを参照することはできません。Renetのcompose バリデーターは、現在のリポジトリの `${REDIACC_NETWORK_ID}` ディレクトリの外を指す `secrets: file:`、`configs: file:`、または `env_file:` パスを厳しく拒否し、その拒否は `--unsafe` でもオーバーライド不可です。多層防御：Rediaccfile bashサブプロセスの周りのLandlockサンドボックスは、ファイルシステムの読み取りを現在のネットワークのシークレットディレクトリのみにスコープするため、悪意のあるRediaccfileからの `cat /var/run/rediacc/secrets/<other>/X` はカーネル層でEACCESで失敗します。

さらに2つのパターンがエッジケースを塞ぎます：

1. **本番環境の認証情報をリポジトリのファイルシステム自体に焼き込まないでください。** コミットされた `.env` ファイルまたは `up()` 中にボリュームに保持された認証情報は、フォークにreflinkされます。リポジトリごとのシークレット機能は、シークレット領域に保持する値のみを保護します。LUKSイメージ内にすでに存在するバイトを遡及的に保護することはできません。焼き込まれた `.env` ファイルを含む既存のリポジトリについては、それらを手動でリポジトリごとのシークレットに移行してください。
2. **eBPFエグレスフィルタリングでフォークの送信ネットワークを制約し**、フォークがlocalhostと明示的なサンドボックスエンドポイントにのみ到達できるようにします。Rediaccのリポジトリごとのネットワーク分離はその基盤です。フォークごとのエグレス許可リストは現時点では構築されていませんが、その道は開かれています。

Rediaccはデプロイ時の注入、フォーク間の分離、リポジトリ間の分離を担当します。「イメージに焼き込まないこと」の部分はあなたの責任です。

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

- [AIエージェント統合の概要](/ja/docs/ai-agents-overview)：トップレベルのツアー
- [Claude Code のセットアップ](/ja/docs/ai-agents-claude-code)：統合テンプレート
- [JSON出力エンベロープ](/ja/docs/ai-agents-json-output)：マシン可読レスポンス
- [暗号化された設定ストア](/ja/docs/config-storage)：サーバー側の暗号学的強制
- [アカウントセキュリティ](/ja/docs/account-security)：オペレーター向けのセキュリティ体制
