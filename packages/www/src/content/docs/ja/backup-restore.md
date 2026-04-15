---
title: バックアップと復元
description: 暗号化されたリポジトリを外部ストレージにバックアップし、バックアップから復元し、自動バックアップをスケジュールします。
category: Guides
order: 7
language: ja
sourceHash: "0c7ebc3efb8877c5"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# バックアップと復元

Rediaccは暗号化されたリポジトリを外部ストレージプロバイダにバックアップし、同じマシンまたは別のマシンで復元できます。バックアップは暗号化されており、復元にはリポジトリのLUKS認証情報が必要です。

## ストレージの設定

バックアップを送信する前に、ストレージプロバイダを登録します。Rediaccはrclone互換のストレージをすべてサポートしています：S3、B2、Google Driveなど。

### rcloneからのインポート

既にrcloneリモートが設定されている場合：

```bash
rdc config storage import --file rclone.conf
```

これにより、rclone設定ファイルからストレージ構成が現在の設定にインポートされます。サポートされているタイプ：S3、B2、Google Drive、OneDrive、Mega、Dropbox、Box、Azure Blob、Swift。

### ストレージの表示

```bash
rdc config storage list
```

## バックアップの送信

リポジトリのバックアップを外部ストレージに送信します：

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

プッシュは書き込み前に常にターゲットリポジトリがマウントされているか確認します。マウントされていない場合、操作は中止されます。

| オプション | 説明 |
|-----------|------|
| `--to <storage>` | ターゲットストレージの場所 |
| `--to-machine <machine>` | マシン間バックアップのターゲットマシン |
| `--dest <filename>` | カスタム宛先ファイル名 |
| `--checkpoint` | プッシュ前にCRIUチェックポイントを作成（`rediacc.checkpoint=true`ラベル付きコンテナ用）。ターゲットは`repo up`時に自動復元 |
| `--force` | 既存のバックアップを上書き |
| `--bwlimit <limit>` | rsync転送の帯域幅制限（例：`10M`、`500K`） |
| `--tag <tag>` | バックアップにタグを付ける |
| `-w, --watch` | 操作の進捗を監視 |
| `--debug` | 詳細出力を有効化 |
| `--skip-router-restart` | 操作後のルートサーバー再起動をスキップ |

## バックアップの取得 / 復元

外部ストレージからリポジトリのバックアップを取得します：

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

プルは書き込み前に常にターゲットリポジトリがマウントされているか確認します。マウントされていない場合、操作は中止されます。

| オプション | 説明 |
|-----------|------|
| `--from <storage>` | ソースストレージの場所 |
| `--from-machine <machine>` | マシン間復元のソースマシン |
| `--force` | 既存のローカルバックアップを上書き |
| `--bwlimit <limit>` | rsync転送の帯域幅制限（例：`10M`、`500K`） |
| `-w, --watch` | 操作の進捗を監視 |
| `--debug` | 詳細出力を有効化 |
| `--skip-router-restart` | 操作後のルートサーバー再起動をスキップ |

## バックアップの一覧表示

ストレージの場所にある利用可能なバックアップを表示します：

```bash
rdc repo backup list --from my-storage -m server-1
```

## 一括同期

すべてのリポジトリを一度に送信または取得します：

### すべてをストレージに送信

```bash
rdc repo push --to my-storage -m server-1
```

### すべてをストレージから取得

```bash
rdc repo pull --from my-storage -m server-1
```

| オプション | 説明 |
|-----------|------|
| `--to <storage>` | ターゲットストレージ（送信方向） |
| `--from <storage>` | ソースストレージ（取得方向） |
| `--repo <name>` | 特定のリポジトリを同期（繰り返し指定可能） |
| `--override` | 既存のバックアップを上書き |
| `--debug` | 詳細出力を有効化 |
| `--skip-router-restart` | 操作後のルートサーバー再起動をスキップ |

## スケジュールバックアップ

Rediaccは名前付きバックアップ戦略を使用します。各戦略はスケジュール、バックアップモード、オプションの帯域幅制限、ファイルフィルターを定義します。マシンは名前で戦略を参照し、実行するバックアップを決定します。

### バックアップモード

| モード | 動作 | ダウンタイム |
|--------|------|------------|
| `hot` | サービス稼働中にBTRFSスナップショットを取得（クラッシュ整合性） | なし |
| `cold` | サービス停止、スナップショット取得、サービス再起動、スナップショットアップロード（アプリケーション整合性） | 短時間 |

クラッシュ整合性スナップショットが許容されるサービスには`hot`を使用します。保証された整合性が必要で短い再起動を受け入れられる場合は`cold`を使用します。

### コールドバックアップのセマンティクス

コールドバックアップは、対象リポジトリごとに3つのフェーズで実行されます：**停止 -- スナップショット -- 起動**。保証の限界を理解することで、オペレーターが部分的な障害を早期に検出できます。

**コールドバックアップが保証すること：**

- スナップショット前に、各対象リポジトリで実行中のすべてのコンテナがRediaccfileの`down()`フックを通じて正常に停止され、リポジトリごとのDockerデーモンが静止されます。スナップショットはクラッシュ整合性だけでなく、アプリケーション整合性を持ちます。
- スナップショット前に実行されていたコンテナIDのセットが`/var/run/rediacc/cold-backup-<guid>.running.json`のサイドカーファイルに保持されます。これが「完了時に再び起動すべきもの」の真実の情報源です。
- スナップショット後、リポジトリのRediaccfileの`up()`フックが呼び出され、完全なcomposeスタックが復元されます。
- 実行ごとのステータスサイドカーファイル`/var/run/rediacc/cold-backup-<guid>.status.json`に、各試行のフェーズ、結果、エラーが記録されます。

**コールドバックアップが保証しないこと：**

- `up()`はベストエフォートです。コールドバックアップの制御外の理由で失敗する可能性があります（`depends_on: service_healthy`条件の待機中、composeファイルの構文エラー、イメージプル中の一時的なネットワーク障害など）。失敗した場合、コールドバックアップはエラーレベルでログを記録し、ステータスサイドカーを書き込み、次のリポジトリに進みます。
- `up()`が失敗した場合、**直接フォールバック再起動**が実行されます：実行サイドカーが読み込まれ、記録された各コンテナIDがDocker APIを通じて直接再起動されます（composeなし）。composeフローに問題があっても、Rediaccfileフックを再実行せずにサービスを復帰させます。
- 一部のコンテナID（Dockerデーモン自体がダウンしているなど）のフォールバックが失敗した場合、サイドカーは**そのまま残され**、ルーターwatchdogが各ティックで再試行できるようにします。

**Watchdog回復：** 各ティックで、watchdogは実行サイドカーの存在を確認します。そこにリストされているコンテナIDのうち、現在停止しているものは、*コンテナの保存された`restart_policy`に関わらず*再起動されます。これにより、`restart: on-failure`（クリーンな停止後にDockerが再起動しない）のサービスも、コールドバックアップ後に復帰します。リストされたすべてのコンテナが実行中になると、サイドカーは削除されます。

**オペレーターが障害を検出する方法：**

- `rdc machine query --name <machine> --containers`で実行状態を確認します。期待されるセットと比較してください。
- マシン上の`/var/run/rediacc/cold-backup-<guid>.status.json`を確認します。`rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`で検査できます。`success: false`と古い`startedAt`は、最後のバックアップが正常に完了しなかったことを示します。
- renetバックアップ実行のログ（`journalctl -u renet-*`または直接の`rdc machine deploy-backup`呼び出し）は、`Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`の形式の最終サマリー行を出力します。空でない`failed_repos`がgrepのターゲットです。

### 戦略の定義

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name nightly-cold \
  --destination my-storage \
  --cron "0 2 * * *" \
  --mode cold \
  --include "*.db" \
  --exclude "tmp/**" \
  --enable
```

| オプション | 説明 |
|-----------|------|
| `--name <name>` | 戦略名（マシンバインディングに使用） |
| `--destination <storage>` | アップロード先のストレージプロバイダ |
| `--cron <expression>` | cron式（例：`"0 2 * * *"` で毎日午前2時） |
| `--mode <hot\|cold>` | バックアップモード |
| `--bwlimit <limit>` | アップロードの帯域幅制限（例：`10M`） |
| `--include <pattern>` | 包含フィルター（繰り返し指定可能） |
| `--exclude <pattern>` | 除外フィルター（繰り返し指定可能） |
| `--enable` / `--disable` | 戦略を有効化または無効化 |

### 戦略の表示

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name nightly-cold
```

### 戦略の削除

```bash
rdc config backup-strategy remove --name nightly-cold
```

### マシンへの戦略のバインド

設定内で、1つ以上の戦略名をマシンにバインドします：

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "nightly-cold"]
    }
  }
}
```

## バックアップ操作

### マシンへのスケジュールのデプロイ

バインドされた戦略をsystemdタイマーとしてマシンにプッシュします：

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

`--dry-run`は生成されたsystemdユニットファイルをデプロイせずに表示します。rcloneトークンはdry-run出力でマスクされます。

### 今すぐバックアップを実行

タイマーを待たずに即座にバックアップを開始します。タイマーがデプロイされていなくても、`systemd-run`によるアドホック実行が可能です：

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy nightly-cold
```

### バックアップ状態の表示

バックアップタイマーの現在の状態と最近のジョブ結果を表示します：

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### 実行中のバックアップのキャンセル

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy nightly-cold
```

## リポジトリの移行

リポジトリをあるマシンから別のマシンに移動します：

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| オプション | 説明 |
|-----------|------|
| `--name <repo>` | 移行するリポジトリ |
| `--from <machine>` | ソースマシン |
| `--to <machine>` | 宛先マシン |
| `--provision` | 転送前に宛先でリポジトリをプロビジョニング |
| `--checkpoint` | 移行前にCRIUチェックポイントを作成 |
| `--skip-dns` | 移行後のDNSレコード更新をスキップ |
| `--bwlimit <limit>` | 転送の帯域幅制限（例：`50M`） |

移行はrsyncを介して暗号化されたリポジトリデータを転送します。ソースリポジトリは明示的に削除するまで保持されます。

## ストレージの参照

ストレージの場所の内容を参照します：

```bash
rdc storage browse --name my-storage
```

## ベストプラクティス

- 重要なデータのアプリケーション整合性スナップショットのために毎日のコールドバックアップをスケジュールする
- ゼロダウンタイムが必要な高頻度スナップショットにはホットバックアップを使用する
- バックアップの整合性を確認するため、定期的に復元テストを実施する
- 重要なデータには複数のストレージプロバイダを使用する（例：S3 + B2）
- 認証情報を安全に保管する；バックアップは暗号化されているが、復元にはLUKS認証情報が必要
