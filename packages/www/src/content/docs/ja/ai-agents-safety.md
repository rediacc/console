---
title: AIエージェントの安全性とガードレール
description: >-
  RediaccがAIコーディングアシスタントによる秘密の漏えい、認証情報の上書き、
  権限昇格をどのように防ぐか。すべてのインターフェースに共通する1つの判断、
  オプトインとポリシー上限の両立、ナレッジゲート、秘匿化、ハッシュチェーン
  監査ログ。
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: ja
sourceHash: "90603fac1c7635d4"
sourceCommit: "29bdc2aca2ed2b968e47005622ff9cfbbb66e56a"
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
| `rdc config edit --dump --redacted`（秘匿化済み JSONC） | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（機密フィールド、`--current` なし） | 🔴 refused | `--current "<古い値>"` を指定する |
| `rdc repo secret set <repo> --rotate-secret`（`--current` なしのローテーション） | 🔴 refused | `--current` を指定する、または人間がターミナルでローテーションを実行 |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | 代わりに `--digest` を使用する |
| `rdc config show --reveal` | 🔴 refused | オプションなしの `rdc config show` を使用する |
| `rdc config edit`（インタラクティブエディタ） | 🔴 refused、オーバーライドなし | `--dump --redacted` で確認し、1つのフィールドは `config field set --current` で変更 |
| `rdc config edit --apply <file>` | 🔴 refused、オーバーライドなし | 同上。ドキュメント全体の編集はターミナル上の人間が適用 |
| `rdc config edit --reveal` | 🔴 refused、オーバーライドなし | 同上 |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | 人間がインタラクティブなターミナルで実行 |
| grand（本番）リポジトリの変更 | 🔴 refused | grand リポジトリの変更を許可するポリシーの範囲内で、そのリポジトリに対する人間のオプトイン（[下記](#one-decision-opt-in-and-policy-ceiling)） |
| クラスターまたはデータストアのライフサイクル操作 | 🔴 refused | クラスター操作を許可するポリシーの範囲内で、そのクラスターに対する人間のオプトイン |
| `rdc term connect <machine>`（マシンへの直接SSH） | 🔴 refused | 最初にリポジトリをフォークしてフォークに接続する |

エージェントに対する拒否はすべて、`outcome: refused` と理由とともに監査ログに書き込まれます。設定ドキュメント全体の編集には、エージェント向けの経路がまったくありません。設定にはすべてのリポジトリの LUKS 認証情報が含まれており、それを書き換えられるエージェントは、暗号化ボリュームを開くのに必要な認証情報を削除することもできてしまうからです。

## エージェントの検出方法

CLIは以下のいずれかに該当する場合、プロセスをエージェントとして扱います：

- `REDIACC_AGENT`、`CLAUDECODE`、`GEMINI_CLI`、`COPILOT_CLI` のいずれかが `"1"` に設定されている、または `CURSOR_TRACE_ID` が設定されている。
- Linux上：祖先チェーン上の親プロセスがそれらの変数のいずれかを環境変数として持っている（`/proc/<pid>/environ` 経由）。エージェントが `env -i` やラッパースクリプトで自分の変数を削除しても、親チェーンがCLIに誰が起動したかを伝えます。

検出はプロセスごとに1回実行され、キャッシュされます。無効にすることはできません。リモート MCP のグラントは、エグゼキューター側でその呼び出しをエージェント呼び出しとして扱うため、検出は不要です。

## 1つの判断: オプトインとポリシー上限の両立

`rdc` コマンドを実行するすべてのインターフェース（CLI、ローカル MCP サーバー、リモート MCP サーバー、`rdc --proxy`、Web コンソール）は同じ判断関数に問い合わせるため、拒否も許可もすべて同じ結果になります。判断関数は2つの条件を適用し、エージェントは両方が満たされる場所でのみ動作できます。

1. **ポリシー上限。** チームポリシーで絞り込まれた組織ポリシーが、呼び出し元の使用できるコマンド、マシン、リポジトリを決め、grand リポジトリの変更（`allowGrandRepos`）とクラスター操作（`allowClusterOps`）をそもそも許可するかどうかも決めます。ポリシーレコードのない設定は、ロールごとのデフォルトにフォールバックします。オーナーと管理者は操作でき、メンバーはできません。ポリシーはオーナーと管理者だけが書き込める独立した封印済みレコードで（[セキュリティモデル](/ja/docs/security-model#policy)）、どのエージェントも CLI コマンドもこれを編集できません。
2. **人間のオプトイン。** 上限の内側でも、エージェントには、変更してよい grand リポジトリまたはクラスターを人間が指名することが必要です。
   - **ローカルエージェント**（CLI とローカル MCP）: 人間がエージェントを起動する前にターミナルで `REDIACC_ALLOW_GRAND_REPO`（リポジトリ名、または `*`）または `REDIACC_ALLOW_CLUSTER_OPS`（クラスター名、または `*`）をエクスポートします。CLI はプロセスの祖先を確認するため、エージェントがセッション途中で設定した変数は無効です（[各 OS での確認方法](#how-a-local-opt-in-is-verified-on-each-os)）。
   - **リモートエージェント**（リモート MCP）: オプトインは、人間がアカウント画面で作成するグラントに含まれます（[リモートサーバー](/ja/docs/ai-agents-mcp#remote-server)）。

オプトインが上限を広げることはありません。ポリシーが閉じているリポジトリは、環境やグラントの内容にかかわらず閉じたままです。フォークにオプトインは不要です。CLI が識別できないリポジトリは grand として扱われます。

**破壊的な変更は先に確認を求めます。** エージェントが grand リポジトリへの破壊的な変更（たとえば `repo delete`）を許可されている場合、応答は `needs_confirmation` になります。MCP クライアントはユーザーに確認プロンプトを表示し、プロンプトを持たないクライアントには、ユーザーに確認したうえで送り返す `confirm` 引数が渡されます。CLI では、人間が `--confirm-grand <repo>` を付けてコマンドを再実行します。

すべての応答には安定したコード（`POLICY_DENIED`、`GRAND_REPO_DENIED`、`CLUSTER_OPS_DENIED`、`AGENT_OPT_IN_MISSING`、`FORK_BLOCKED`、`AGENT_BLOCKED`、`CONFIRMATION_REQUIRED`）が付くため、スクリプトやエージェントはメッセージではなくコードで分岐できます（[JSON 出力](/ja/docs/ai-agents-json-output)）。

## ナレッジゲートモデル

機密変更は `passwd(1)` の慣例に従います：シークレットを変更するには、すでに知っていたことを証明してください。**人間とエージェント両方に対して対称的です**。両者は同じゲートを通ります。キーボードにいるから特別扱いされるわけではありません。

- `/credentials/cfDnsApiToken` に保存されているAPIトークンをローテーションしたい場合
- CLIが「現在の値は何ですか？」と尋ねます
- エージェント（または人間）が `--current "$OLD"` でプレーンテキストを提供します。CLIは `$OLD` をSHA-256でハッシュ化し、現在保存されている値のダイジェストと比較します。一致 → 書き込み実行。不一致 → 拒否、監査記録。
- 以前の値を確認せずにローテーションするには、`--rotate-secret` を渡します（`--current` とは同時に指定できません）。これはローテーションとして明確に監査され、インタラクティブなターミナル上の人間にのみ有効です。エージェント、または stdin にターミナルのないスクリプトには、引き続き `--current` が必要です。

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
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**エージェントは、独自のコマンドを作り出すのではなく、`next.options[].run` を人間にそのまま伝えるべきです。** これにより、エージェントが存在しないコマンドをでっち上げる失敗を防ぎ、実際の操作の主導権をオペレーターが保てます。ローテーションの選択肢は人間がターミナルで実行するためのもので、エージェント自身には拒否されます。

### 実例

```bash
# 秘匿化スタブの短いダイジェストを取得する（エージェントに安全）。
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 証明なしに上書きを試みる：拒否。
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# 現在のプレーンテキストを提供する：許可。
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

エージェントが `$OLD_CF_TOKEN` を持っていなければ、前提条件を満たせず、ローテーションは拒否されます。値を知っている人は、自分のシェルから `--current` を渡すか、インタラクティブなターミナルで `rdc config field rotate` を使えば実行できます。

## デフォルトの秘匿化

機密状態を読む `rdc` コマンド：`config show`、`config field get`、`config machine list`、`config edit --dump --redacted`：はシークレットフィールドに対してプレーンテキストではなく **秘匿化スタブ** を返します：

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

スタブの8文字の16進サフィックスは `sha256(canonicalize(value))` の最初の8文字です。一見して2つの異なる値を区別するには十分ですが、逆算には不十分です。エージェントはスタブを使って、値を見ることなく値が変わったかどうかを追跡できます。

`--reveal` はインタラクティブなTTY上の人間に対して秘匿化を解除します。エージェントはTTYの状態に関係なく拒否されます。各許可は `reveal_granted` 監査エントリを書き込み、各拒否はアクターのエージェントシグナルが添付された `refused` エントリを書き込みます。

## ローカルのオプトインを各 OS でどう確認するか

`REDIACC_ALLOW_GRAND_REPO` と `REDIACC_ALLOW_CLUSTER_OPS` はいずれも、オプトインがエージェントによる注入ではなく人間によって設定されたことを証明するために、祖先確認に依存しています。確認は Linux、macOS、Windows で動作しますが、読み取る証拠はプラットフォームごとに異なり、保証の強さも異なります。

| プラットフォーム | ウィットネス | 強度 |
|---|---|---|
| Linux | チェーン上のすべてのプロセスに対する `/proc/<pid>/environ` | Exec時点のスナップショット。カーネルが提供。プロセスは起動時に設定された内容を遡及的に編集することはできない。 |
| macOS | `kern.procargs2` sysctl（`rdc` に含まれる小さなヘルパーで読み取られる） | Linuxと同じexec時点のスナップショット特性。ルートなしで自分のプロセスから読み取り可能。 |
| Windows | 各祖先プロセスのライブ環境ブロック（PEB）。同じヘルパーで読み取られ、PID再利用ガードあり | より弱い：Windowsはexec時点のスナップショットを保持していないため、チェックは現在のメモリを読み取る。祖先がエージェント側で通常実行するものでは上書きされないが、ウィットネスはLinuxやmacOSのようにカーネル固定ではない。 |

macOS と Windows では、CLI が同梱の `renet` バイナリを起動して読み取りを行います。ヘルパーは各祖先が監視対象のどの変数を持っているかを報告し、判断ロジックはすべて CLI に残ります。ヘルパーが見つからない、古い、またはなんらかの理由で失敗した場合、CLI はオプトインを確認できず、**安全側に倒して失敗します**。オプトインは拒否され、エラーには、何かが間違っていたのではなく確認が利用できなかったことが示されます。正常なインストールではこのメッセージは表示されません。`rdc` を再インストールするとヘルパーが復元されます。

どのプラットフォームでも変わらないこと: オプトインは、エージェントプロセスの起動時にその環境にすでに存在していなければなりません。ターミナルでエクスポートしてからエージェントを起動します。セッション途中で変数を設定したエージェントは拒否されます。

## 監査ログ

すべての変更、すべての拒否、すべての `--reveal` 許可は `~/.config/rediacc/audit.log.jsonl`（モード `0600`、10MBでローテーション）にJSONL行として書き込まれます。各行はハッシュ連鎖されています：その `prevHash` フィールドは `sha256("<前の行>")` です。いずれかの行を改ざんすると、以降のすべての行でチェーンが壊れます。

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
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

主な対策は組み込まれています：**[リポジトリごとのシークレット](/ja/docs/repositories#secrets)** は暗号化されたリポジトリイメージとは別の領域に保存され、フォーク境界を越えてコピーされません。フォークのコンテナは空のシークレットマップでブートし、親とは異なる外部プリンシパルとして自身を識別します。`rdc repo secret set` で設定してください（compose補間用のenvモード、tmpfs `secrets:` ブロック用のfileモード）。変更ゲートは対称的です。人間とエージェント両者が、既存の値を上書きまたは削除するには `--current`（passwd形式の前提条件）を供給する必要があります。`--rotate-secret`（監査対象のローテーション）は、ターミナル上の人間向けの代替手段です。

**リポジトリ間の分離は強制されます。** リポジトリBの悪意あるまたは不注意なcompose ファイルは、リポジトリAのシークレットディレクトリを参照することはできません。Renetのcompose バリデーターは、現在のリポジトリの `${REDIACC_NETWORK_ID}` ディレクトリの外を指す `secrets: file:`、`configs: file:`、または `env_file:` パスを厳しく拒否し、その拒否は `--unsafe` でもオーバーライド不可です。多層防御：Rediaccfile bashサブプロセスの周りのLandlockサンドボックスは、ファイルシステムの読み取りを現在のネットワークのシークレットディレクトリのみにスコープするため、悪意のあるRediaccfileからの `cat /var/run/rediacc/net-<other>/secrets/X` はカーネル層でEACCESで失敗します。Docker API でも同じです。各リポジトリのDockerソケットはrenetのポリシープロキシが受け持ち、`--privileged`、ホストの `pid`・`ipc`・`uts`、デバイスの要求、別のリポジトリのランタイムやデータに届くバインドを `403` で拒否します。そのため `${DOCKER_SOCKET}` を持つコンテナがAPIを使って別のリポジトリに到達することはできず、チェックの対象はcomposeファイルだけではありません。バインドのルールを、名前を指定したホストディレクトリに限って広げられるのはオペレーターだけで、その方法はどのコンテナも書き込めないroot所有の許可ファイルです。

さらに2つのパターンがエッジケースを塞ぎます：

1. **本番環境の認証情報をリポジトリのファイルシステム自体に焼き込まないでください。** コミットされた `.env` ファイルまたは `up()` 中にボリュームに保持された認証情報は、フォークにreflinkされます。リポジトリごとのシークレット機能は、シークレット領域に保持する値のみを保護します。LUKSイメージ内にすでに存在するバイトを遡及的に保護することはできません。焼き込まれた `.env` ファイルを含む既存のリポジトリについては、それらを手動でリポジトリごとのシークレットに移行してください。
2. **eBPFエグレスフィルタリングでフォークの送信ネットワークを制約し**、フォークがlocalhostと明示的なサンドボックスエンドポイントにのみ到達できるようにします。Rediaccのリポジトリごとのネットワーク分離はその基盤です。フォークごとのエグレス許可リストは現時点では構築されていませんが、その道は開かれています。

Rediaccはデプロイ時の注入、フォーク間の分離、リポジトリ間の分離を担当します。「イメージに焼き込まないこと」の部分はあなたの責任です。

## クイックレシピ

### エージェントに1つの grand リポジトリで作業させる

```bash
# 人間として、エージェントを起動する前に:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # または cursor、gemini など
```

エージェントは、ポリシーが grand リポジトリの変更を許可している範囲で `gitlab` を変更でき、ほかの grand リポジトリは変更できません。`repo delete gitlab` のような破壊的な変更では、引き続き確認が求められます。

### 古い値を知らずにクラウドトークンをローテーションする

```bash
# 人間として、インタラクティブなターミナルで:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

`--current` なしのローテーションは人間の担当です。現在の値を知っているエージェントは、代わりに `rdc config field set --current` を使います。

### エージェントが触れることのできるフィールドを確認する

```bash
rdc config field list --sensitive --output json
```

すべてのポインターテンプレート、その種類（`secret` / `credential` / `pii` / `identifier`）、およびサーバー側のHMACエンベロープにコミットされているかどうかを返します。

## 関連項目

- [AIエージェント統合の概要](/ja/docs/ai-agents-overview)：トップレベルのツアー
- [MCPサーバー](/ja/docs/ai-agents-mcp): ローカルとリモートの MCP、グラントとそのオプトイン
- [セキュリティモデル](/ja/docs/security-model): ポリシーレコードと、それを書き込める人
- [Claude Code のセットアップ](/ja/docs/ai-agents-claude-code)：統合テンプレート
- [JSON出力エンベロープ](/ja/docs/ai-agents-json-output)：マシン可読レスポンス
- [暗号化された設定ストア](/ja/docs/config-storage)：サーバー側の暗号学的強制
- [アカウントセキュリティ](/ja/docs/account-security)：オペレーター向けのセキュリティ体制
