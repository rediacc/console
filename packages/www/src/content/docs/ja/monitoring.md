---
title: モニタリング
description: マシンの健全性、コンテナ、サービス、リポジトリの監視と診断の実行。
category: Guides
tags:
  - operations
subcategory: operations
order: 9
language: ja
sourceHash: "acef592a7065cac7"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# モニタリング

Rediaccは、マシンの健全性、実行中のコンテナ、サービス、リポジトリの状態、システム診断を検査するための組み込みの監視コマンドを提供します。

## マシンの健全性

マシンのフルヘルスレポートを取得します：

```bash
rdc machine health server-1
```

レポート内容：
- **システム**: アップタイム、メモリ（80%超で警告、90%超でエラー）、ディスクとデータストアの使用量（85%超で警告、95%超でエラー）
- **コンテナ**: 実行中、正常、異常のコンテナ数。`Restarting` ループに入ったコンテナはクリティカルです
- **サービス**: 失敗したsystemdユニット（エラー）と再起動を繰り返すユニット（クリティカル）
- **ストレージ**: SMARTヘルスステータス（故障しかけのディスクはクリティカル）とディスク温度
- **リポジトリ**: マウントされていない自動起動リポジトリと、各リポジトリのファイルシステム使用量（85%超で警告、95%超でエラー）
- **バックアップ**: 10日以上バックアップされていない、スケジュールやターゲットに遅れている、または前回の検証に失敗したリポジトリ
- **ライセンス**: 期限切れ、欠落、不一致、無効なリポジトリライセンスと、更新が必要なライセンス
- **renetプロセス**: 置き換え済みのrenetバイナリをまだ実行しているデーモン
- **リポジトリの健全性**: マウント済みの各リポジトリ自身の `health()` の結果（下記参照）
- **証明書**: 期限が近いプロキシの証明書と、共有されているACMEチャレンジのCNAME
- **問題点**: 検出された問題

終了コードが判定結果です。`0` は検出事項なし（`health()` チェックのないリポジトリは「チェックなし」と表示され、正常とは数えません）、`1` は警告、`2` はエラー、`3` はクリティカル（故障しかけのディスク、または再起動ループ中のコンテナやサービス）です。マシン可読な出力には `--output json` を使用してください。出力には `repo_health`（リポジトリごとに1件のレポート）と `findings` が含まれ、各検出事項にはコード、重大度（`info`、`warning`、`error`、`critical`）、対象、詳細、修復方法がある場合は `fix` が付きます（[修復](#repair)を参照）。

## リポジトリの健全性

Rediaccfileには、リポジトリ自身のサービスを確認する `health()` 関数を定義できます（[サービス](/ja/docs/services)）。終了コード `0` は正常、`1` は警告、`2` はエラーです。1つのリポジトリに対して実行するには次のようにします：

```bash
rdc repo health my-app@server-1
```

コマンドは、リポジトリのRediaccfile全体で最も悪いレベルを終了コードにして終了します。どのRediaccfileも `health()` を定義していないリポジトリは**チェックなし**と表示して `0` で終了し、正常とは報告されません。タイムアウトした、強制終了された、またはそれ以外のコードで終了した `health()` はエラーです。マシンに接続できない場合も同様です（終了コード `2`）。

`rdc machine health` は、マウント済みの全リポジトリの `health()` を1回の呼び出しで実行し、最も悪いレベルを自身の終了コードに反映します。リポジトリごとに1件の検出事項が、警告（`repo.health.warning`）またはエラー（`repo.health.error`）として出力されます。チェックのないリポジトリは一覧に表示されるだけで、問題としては報告されません。マシンのrenetがリポジトリのヘルスチェックに対応する前のバージョンの場合、`rdc machine setup` で更新されるまで、警告 `renet.repo-health.unsupported` が1件だけ出力されます。

## 証明書の期限とACMEチャレンジ

`rdc machine health` はプロキシのACME証明書を読み取り、期限まで21日未満のものは警告、7日未満のものはエラーとして `cert.expiry.near` を報告します。プロキシは30日前に更新するため、21日を切った証明書は、更新が少なくとも9日間失敗し続けていることを意味します。

また、証明書名の `_acme-challenge.<name>` レコードが、それ自体は `_acme-challenge.` 名ではない名前へCNAMEでたどり着く場合、または2つの名前が同じ名前に行き着く場合に、`acme.challenge.cname-shared` を報告します。CNAMEであるワイルドカードレコードがあると、この形になります。すべてのチャレンジが1つの名前に集まり、更新が衝突します。意図的な委任（たとえば `_acme-challenge.mail.example.com` が `_acme-challenge.mail.example.io` を指す場合）は報告されません。それ以外の意図した委任は、プロキシの `config.env` にある `ACME_DELEGATED_NAMES`（証明書名のカンマ区切りリスト）に列挙してください。チャレンジのチェーンを解決できなかった名前（どのDNSリゾルバーからも応答がなかった）は、その名前に対するチェックが実行されなかったため、警告の `acme.challenge.unknown` として報告されます。

## 修復

すべての検出事項にはコードが付き、安全な修復方法がある場合は `action`、安全性の `class`、`window_only` を持つ `fix` が付きます。`rdc machine health` は読み取り専用のままで、実際に変更を行うのは `rdc machine repair` です：

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| クラス | 意味 |
|---|---|
| `auto-safe` | 既定で実行されます：コンテナやTraefikの再起動、trimとプルーン、ACMEアンカーの書き込み |
| `auto-with-backup` | `--with-backup` を付けた場合にのみ、リポジトリのスナップショットが成功した後で実行されます。スナップショットが失敗すると修復は中止されます |
| `operator-only` | 実行されません。コマンドは手動で実行すべき正確なコマンドを表示します。名前付きのデータを削除するもの、または費用が発生するものはすべてここに含まれます |

`window_only` はクラスに加わる条件です。修復はマシンのメンテナンスウィンドウ内、つまりUTCの `HH:MM-HH:MM`（日付をまたいでもかまいません）の間にのみ実行されます。ウィンドウのないマシンは、これらの修復を自動では実行しません。`--window-override` を付けると手動で実行できます。ウィンドウの設定と解除は次のとおりです：

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

各修復は最初に検出事項がまだ存在することを確認するため、2回目の実行では何もすることがないと報告されます。同じ対象に作用する修復は1回だけ実行されます（Traefikを1回再起動すれば、すべての証明書に効きます）。各修復は、タグ `rediacc-repair` でマシンのジャーナルに、またJSONの `actions`（`code`、`subject`、`action`、`class`、`result`、`before`、`after`）に記録され、実行の最後には全体の再チェックが行われます。終了コードは、何も残らなければ `0`、警告またはoperator-onlyの項目が残れば `1`、エラーまたはクリティカルな検出事項が残るか、修復が失敗した場合は `2` です。`rdc machine repair` は `3` で終了することはなく、`3` を返すのは `rdc machine health` だけです。

| 検出事項 | 修復 | クラス |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | trimの後、停止中のコンテナ、匿名の孤立ボリューム、未使用のイメージをプルーン | auto-safe |
| `container.unhealthy`, `container.restart-loop` | コンテナを再起動 | auto-safe |
| `renet.binary.replaced` | 影響を受けるリポジトリのスーパーバイザーを再起動（`rdc machine restart-services --include-docker`、対象に限定） | auto-safe、ウィンドウ内のみ |
| `cert.expiry.near` | Traefikを再起動して更新を再試行させる | auto-safe |
| `acme.challenge.cname-shared` | ACMEアンカーを書き込む（下記参照） | auto-safe（委任が宣言されていて、使えるCloudflareトークンがない場合は operator-only） |
| `repo.health.warning`, `repo.health.error` | リポジトリの `repair()` を実行（[サービス](/ja/docs/services)） | Rediaccfileが宣言したクラス |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | 実行すべきコマンドとして表示 | operator-only |

修復方法のない検出事項（SMARTの故障、温度、メモリ、システムディスク、検証の失敗）は報告され、オペレーターに委ねられます。

プルーンはハブには一切触れません。`rediacc.hub.*` ラベルのコンテナと、`rediacc.hub.user` ラベルまたは `rediacc-hub-home-*` という名前のボリュームは対象外なので、ハブユーザーのホームはどの領域回収でも残ります。trimとプルーンで解放できない残り（名前付きボリューム、大きなアプリケーションデータ）は、オペレーターの判断に委ねられます。

### リポジトリの修復

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` は、リポジトリの `repair()` 関数を同じクラスで実行します。`auto-safe` は実行され、`auto-with-backup` には `--with-backup` が必要で、宣言のない（`operator-only`）`repair()` は確認に答えた後か `--yes` を付けた場合にのみ実行されます。その後 `health()` が再実行され、終了コードは最終的なレベルに従います：`0` は正常またはチェックなし、`1` は警告、`2` はエラーまたは失敗した `repair()` です。

### ACMEアンカー

CNAMEであるワイルドカードDNSレコードがあると、すべての `_acme-challenge.<host>` 名がそれをたどり、すべてのチャレンジが1つの名前に集まって更新が衝突します（`acme.challenge.cname-shared`）。修復では、プロキシのCloudflareトークンを使って、衝突している各 `_acme-challenge.<name>` に値 `rediacc-acme-anchor` のTXTレコードを書き込み、その後Traefikを再起動します。明示的なレコードがあれば、その名前はワイルドカードの影響範囲から外れ、チャレンジは本来の場所に届きます。この修復はレコードを追加するだけで、既存のアンカーはそのまま残されます。それ自体がCNAMEであるチャレンジ名には、TXTレコードを並べて置けません。Cloudflareが書き込みを拒否し、修復はトークンで書き込めないゾーンの場合と同じフォールバックに進みます（次の段落）。

`ACME_DELEGATED_NAMES`（プロキシの `config.env` にある証明書名のカンマ区切りリスト）に列挙された名前は意図的な委任であり、アンカーが書き込まれることも報告されることもありません。プロキシに使えるCloudflareトークンがない場合、修復は `config.env` の `LEGO_DISABLE_CNAME_SUPPORT=true` にフォールバックしますが、これは委任された名前が1つも宣言されていない場合に限ります。この変数はすべての名前でCNAMEの追跡を無効にするためです。委任が宣言されている場合、検出事項はoperator-onlyのままです。同じ修復はプロキシのインストールごと（`rdc machine infra push`）に実行され、マシン上で `renet proxy acme-fix` を使って単独でも実行できます。

## コンテナの一覧表示

マシン上のすべてのリポジトリにわたる実行中のコンテナをすべて表示します：

```bash
rdc machine status server-1 --containers
```

| カラム | 説明 |
|--------|------|
| Name | コンテナ名 |
| Status | アップタイムまたは終了理由 |
| State | 実行中、終了済みなど |
| Health | 正常、異常、なし |
| CPU | CPU使用率 |
| Memory | メモリ使用量 / 上限 |
| Repository | コンテナが属するリポジトリ |

オプション：
- `--health-check`, コンテナに対してアクティブなヘルスチェックを実行
- `--output json`, マシン可読なJSON出力

JSON 出力には完全なコンテナ詳細（`labels`、`port_mappings`、`image`、`id`）に加え、`repository`（解決後の名前）、`repository_guid`（元の GUID）、`domain`、`autoRoute` が含まれます。

## サービスの一覧表示

マシン上のRediaccに関連するsystemdサービスを表示します：

```bash
rdc machine status server-1 --services
```

| カラム | 説明 |
|--------|------|
| Name | サービス名 |
| State | アクティブ、非アクティブ、失敗 |
| Sub-state | 実行中、停止など |
| Restarts | 再起動回数 |
| Memory | サービスのメモリ使用量 |
| Repository | 関連するリポジトリ |

オプション：
- `--stability-check`, 不安定なサービスをフラグ付け（失敗、3回以上の再起動、自動再起動）
- `--output json`, マシン可読なJSON出力

JSON 出力には、`repository`（解決後の名前）と `repository_guid`（元の GUID）を含む完全なサービス詳細が含まれます。

## リポジトリの一覧表示

マシン上のリポジトリを詳細な統計情報とともに表示します：

```bash
rdc machine status server-1 --repositories
```

| カラム | 説明 |
|--------|------|
| Name | リポジトリ名 |
| Size | ディスクイメージのサイズ |
| Mount | マウント済みまたは未マウント |
| Docker | Docker daemonが実行中または停止 |
| Containers | コンテナ数 |
| Disk Usage | リポジトリ内の実際のディスク使用量 |
| Modified | 最終更新日時 |

オプション：
- `--search <text>`, 名前またはマウントパスでフィルタリング
- `--output json`, マシン可読なJSON出力

JSON 出力には `name`（解決済み）と `guid`（元の GUID）が含まれ、各リポジトリの `containers`（`domain`、`autoRoute`、`repository`/`repository_guid` を含む）配列と `services` 配列がネストされます。

## ストレージの健全性

マシン上のすべてのリポジトリにわたる BTRFS の断片化と reflink 共有を検査します：

```bash
rdc machine status server-1 --storage-health
```

| カラム | 説明 |
|--------|------|
| Quota | リポジトリの最大サイズ（拡張の上限。作成時またはリサイズ/自動拡張によって設定） |
| Allocated | スパースイメージが現時点でプール内に実際に占有している容量 |
| Unique | このリポジトリのみが所有する実際の一意データ |
| Shared | BTRFS reflink を通じてリポジトリ間で再利用されるデータブロック（無償コピー） |
| Reclaimable | [`repo trim`](/ja/docs/repositories#reclaim-space-trim) でプールに返却できる、割り当て済みと使用済みの差分。未マウントのリポジトリには `-` が表示されます |
| Discards | 暗号化ボリュームがディスカードを透過的に通過させるか（現行バージョンでマウントされたリポジトリはすべて `on`） |
| Divergence | このリポジトリに固有のイメージの割合（共有されていない部分）（高いほど削除時に回収可能なデータが多い） |
| Frag | コピーオンライトイメージの GB あたりエクステント数（参考情報のみ） |

クォータと割り当て容量は意図的に異なる数値です。20 GB クォータのリポジトリが 6 GB のデータしか保存していない場合、プールには割り当て済みの容量のみコストがかかります。プールは物理容量より多くのトータルクォータを約束でき、Reclaimable カラムは各リポジトリの割り当て済み容量のうちもはや使用されておらずトリムで返却できる容量を示します。

テーブルの下に、データストアの充填率とバックアップスナップショットが確保している容量を報告するプールサマリーが表示されます。

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

バックアップの実行中は、そのスナップショットがライブリポジトリと共有するすべてのブロックを参照し続けるため、そのバックアップサイクルが完了してスナップショットが削除されるまで、削除やトリムによる空き容量の解放量が減ります。中断されたバックアップの古いスナップショットは、ストレージメンテナーによって数分以内に自動的に削除されます。

サマリーには BTRFS reflink による節約の合計が表示されます：

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **仮想サイズ**はすべてのリポジトリイメージサイズの合計です。これはリポジトリの見かけ上のサイズですが、reflink で共有されているブロックを二重にカウントします。
- **一意データ**は1つのリポジトリにのみ存在するリポジトリデータによって実際に消費されているストレージです。リポジトリを削除したときに解放される容量です。
- **共有**は BTRFS reflink を通じてリポジトリ間で再利用されるデータです。リポジトリをフォークすると、どちらかの側が新しいデータを書き込むまでブロックを共有する reflink コピーが作成され、その時点でブロックが分岐します。
- **効率**は reflink で再利用されるデータの割合です。高いほど良いです。同じ親から多くのフォークを持つマシンは 100% に近い効率を示します。

Frag カラムは参考情報です。アプリケーションが内部で読むファイルではなく、コピーオンライトイメージファイルのエクステントを数えるため、通常のランダム書き込みワークロード（データベース、コンテナレイヤー）では高い値を示しますが、SSD バックストレージにおける読み取りパフォーマンスを予測しません。Rediacc は意図的にデフラグコマンドを提供していません。`btrfs filesystem defragment` はreflinkされたフォークやスナップショットを非共有化し、ほぼ満杯のプールでは使用量が劇的に膨れ上がる一方、ベンチマークでは計測可能な読み取り改善は見られません。計測データと詳細については[断片化の数値が怖く見える。実際のコストを計測してみた。](/ja/blog/i-benchmarked-btrfs-fragmentation)をご覧ください。

スキャンは並列実行され、リポジトリの数とサイズによって 5〜15 秒かかります。`--storage-health` を指定しない場合、クエリ出力の後にリマインダーとして1行のヒントが表示されます。

## BTRFS スクラブ

Rediaccはすべてのマシンで毎週 BTRFS スクラブを自動的にスケジュールします。スクラブはデータストアのすべてのデータブロックを読み取り、チェックサムを検証し、破損を報告します。これにより、バックアップやフォークに伝播する前にサイレントなデータ破損（ビットロット）を検出します。

スクラブは毎週日曜日の 02:00 ローカルタイム（マシンのタイムゾーン）に最大1時間のランダムな遅延を加えて実行されます。最低の I/O 優先度（`ionice idle`、`nice 19`）で実行されるため、実行中のサービスに干渉しません。SSD ベースのマシンでは、データストア 100 GB あたり約 8 分を見込んでください。

スクラブタイマーは、renet のアップグレード後の最初のデーモン起動時に自動的にインストールされます。将来の renet バージョンでスクラブポリシーが変更された場合、次のデーモン起動時にユーザーのアクションなしで自動的に更新されます。

### スクラブのステータス

最後のスクラブの結果は BTRFS ボリュームの外部（`/var/lib/rediacc/scrub-last-result.json`）に保存されるため、ボリュームに問題があっても読み取り可能なままです。`rdc machine status --system` の出力には `scrub_status` フィールドが含まれます：

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| ステータス | 意味 |
|-----------|------|
| `ok` | 最後のスクラブがエラーなしで完了した |
| `never_run` | スクラブがまだ実行されていない（タイマーがインストールされたばかり） |
| `overdue` | 最後のスクラブが 14 日以上前だった |
| `errors_found` | スクラブがチェックサムの不一致を発見した（`total_errors` と `uncorrectable` のカウントを確認してください） |
| `failed` | スクラブプロセスが非ゼロのコードで終了した |

`uncorrectable` がゼロより大きい場合、影響を受けたブロックは自動的に修復できません（単一ディスクの BTRFS には冗長コピーがありません）。影響を受けたリポジトリを最新のバックアップから復元してください。

### 手動スクラブ

スクラブを即座に実行するには（例：電源障害またはディスク移行後）：

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

結果は同じ JSON ファイルに保存され、次の `rdc machine status --system` で即座に確認できます。

## マシン概要

デプロイ情報を含むマシンの完全な概要を取得します：

```bash
rdc machine status server-1
```

提供される情報：
- ホスト名とアップタイム
- メモリ、ディスク、データストアの使用量
- リポジトリの総数、マウント数、Docker daemonが応答しているリポジトリ数
- リポジトリごとの詳細情報

マシン可読な出力には `--output json` を使用してください。

## 接続テスト

マシンへのSSH接続を確認します：

```bash
rdc term connect server-1 -c "hostname"
```

このコマンドは成功時にリモートのホスト名を表示し、失敗時は接続エラーを表示します。これによりDNS、SSHポート、鍵認証を一度に確認できます。

## 診断 (doctor)

Rediacc環境のフル診断チェックを実行します：

```bash
rdc doctor
```

| カテゴリ | チェック内容 |
|----------|-------------|
| **環境** | Node.jsバージョン、CLIバージョン、SEAモード、Goインストール、Dockerの利用可否 |
| **Renet** | バイナリの場所、バージョン、CRIU、rsync、SEA埋め込みアセット |
| **設定** | アクティブな設定、アダプター、マシン、SSH鍵 |
| **仮想化** | ローカル仮想マシンを実行できるか確認（`rdc ops`） |

各チェックは **OK**、**警告**、または **エラー** を報告します。問題のトラブルシューティングの最初のステップとしてこれを使用してください。

終了コード: `0` = すべて合格、`1` = 警告あり、`2` = エラーあり。

## サービス準備完了チェック

`repo up` 実行中、renet は HTTP サービスが接続を受け入れるまで待機してから準備完了とみなします。この待機処理はヘルスチェックの状態を考慮します。

- Docker が **healthy** と報告するコンテナはそのまま信頼されます。TCP プローブは行いません。
- ヘルスチェックの `start_period` 内にあるコンテナは、警告ではなく情報ログを出力します。プロキシはバインドするまで再試行を続けます。
- 実行中のコンテナが存在しない Compose サービス（たとえば非アクティブなプロファイルの背後にあるもの）はスキップされます。
- それ以外はすべて TCP で最大 15 秒プローブします（`REDIACC_READINESS_TIMEOUT` 環境変数に秒数を設定することで変更できます）。

起動に時間のかかるサービスに [Docker ヘルスチェック](https://docs.docker.com/reference/dockerfile/#healthcheck)を定義すると、renet に信頼できる準備完了シグナルが伝わり、デプロイ出力のプローブノイズが減ります。
