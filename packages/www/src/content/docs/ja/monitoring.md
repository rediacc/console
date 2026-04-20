---
title: モニタリング
description: マシンの健全性、コンテナ、サービス、リポジトリの監視と診断の実行。
category: Guides
order: 9
language: ja
sourceHash: "1b60f9a60324f737"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# モニタリング

Rediaccは、マシンの健全性、実行中のコンテナ、サービス、リポジトリの状態、システム診断を検査するための組み込みの監視コマンドを提供します。

## マシンの健全性

マシンの包括的なヘルスレポートを取得します：

```bash
rdc machine health --name server-1
```

レポート内容：
- **System**: アップタイム、ディスク使用量、データストア使用量
- **コンテナ**: 実行中、正常、異常のコンテナ数
- **ストレージ**: SMARTヘルスステータス
- **問題点**: 検出された問題

マシン可読な出力には `--output json` を使用してください。

## コンテナの一覧表示

マシン上のすべてのリポジトリにわたる実行中のコンテナをすべて表示します：

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
```

| カラム | 説明 |
|--------|------|
| Size | LUKS イメージファイルのサイズ（リポジトリの見かけ上のサイズ） |
| Unique | このリポジトリのみが所有する実際の一意データ |
| Shared | BTRFS reflink を通じてリポジトリ間で再利用されるデータブロック（無償コピー） |
| Extents | ファイルエクステントの数（多いほど断片化が進んでいる） |
| Frag | 断片化レベル：低、中、高 |

サマリーには BTRFS reflink による節約の合計が表示されます：

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **仮想サイズ**はすべてのリポジトリイメージサイズの合計です。これはリポジトリの見かけ上のサイズですが、reflink で共有されているブロックを二重にカウントします。
- **一意データ**は1つのリポジトリにのみ存在するリポジトリデータによって実際に消費されているストレージです。リポジトリを削除したときに解放される容量です。
- **共有**は BTRFS reflink を通じてリポジトリ間で再利用されるデータです。リポジトリをフォークすると、どちらかの側が新しいデータを書き込むまでブロックを共有する reflink コピーが作成され、その時点でブロックが分岐します。
- **効率**は reflink で再利用されるデータの割合です。高いほど良いです。同じ親から多くのフォークを持つマシンは 100% に近い効率を示します。

断片化が高く共有ブロックがゼロのリポジトリは `btrfs filesystem defragment` で安全にデフラグできます。共有ブロックを持つリポジトリはデフラグすべきではありません。デフラグは共有ブロックを一意のコピーに置き換えるためディスク使用量が増加します。

スキャンは並列実行され、リポジトリの数とサイズによって 5〜15 秒かかります。`--storage-health` を指定しない場合、クエリ出力の後にリマインダーとして1行のヒントが表示されます。

## BTRFS スクラブ

Rediaccはすべてのマシンで毎週 BTRFS スクラブを自動的にスケジュールします。スクラブはデータストアのすべてのデータブロックを読み取り、チェックサムを検証し、破損を報告します。これにより、バックアップやフォークに伝播する前にサイレントなデータ破損（ビットロット）を検出します。

スクラブは毎週日曜日の 02:00 ローカルタイム（マシンのタイムゾーン）に最大1時間のランダムな遅延を加えて実行されます。最低の I/O 優先度（`ionice idle`、`nice 19`）で実行されるため、実行中のサービスに干渉しません。SSD ベースのマシンでは、データストア 100 GB あたり約 8 分を見込んでください。

スクラブタイマーは、renet のアップグレード後の最初のデーモン起動時に自動的にインストールされます。将来の renet バージョンでスクラブポリシーが変更された場合、次のデーモン起動時にユーザーのアクションなしで自動的に更新されます。

### スクラブのステータス

最後のスクラブの結果は BTRFS ボリュームの外部（`/var/lib/rediacc/scrub-last-result.json`）に保存されるため、ボリュームに問題があっても読み取り可能なままです。`rdc machine query --system` の出力には `scrub_status` フィールドが含まれます：

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

結果は同じ JSON ファイルに保存され、次の `rdc machine query --system` で即座に確認できます。

## Vaultステータス

デプロイ情報を含むマシンの完全な概要を取得します：

```bash
rdc machine vault-status --name server-1
```

提供される情報：
- ホスト名とアップタイム
- メモリ、ディスク、データストアの使用量
- リポジトリの総数、マウント数、Docker実行数
- リポジトリごとの詳細情報

マシン可読な出力には `--output json` を使用してください。

## 接続テスト

> **クラウドアダプターのみ。** ローカルアダプターでは、`rdc term connect -m server-1 -c "hostname"` を使用して接続を確認してください。

マシンへのSSH接続を確認します：

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

レポート内容：
- 接続状態（成功/失敗）
- 使用された認証方法
- SSH鍵の設定
- 公開鍵のデプロイ状態
- Known hostsエントリ

オプション：
- `--port <number>`, SSHポート（デフォルト: 22）
- `--save -m server-1`, 検証済みホスト鍵をマシン設定に保存

## 診断 (doctor)

Rediacc環境の包括的な診断チェックを実行します：

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
