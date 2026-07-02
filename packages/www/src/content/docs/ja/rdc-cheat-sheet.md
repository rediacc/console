---
title: RDC CLI チートシート
description: "rdc コマンドのクイックリファレンス：設定、リポジトリ、マシン、同期、コンテナ。全オプション一覧は任意のコマンドに --help を付けて確認できます。"
category: Guides
order: 3
language: ja
sourceHash: "8cde2c78200d226a"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# RDC CLI チートシート

ここでは全ての `rdc` コマンドをリストしているのではなく、デプロイ時に頻繁に使用されるコマンドのみを掲載しています。全オプションを確認するには、任意のコマンドに `--help` を付けて実行してください。エッジケースと滅多に使わないオプションは、完全なリファレンスに記載されています。

## リポジトリのライフサイクル

| コマンド | 説明 |
|---------|------|
| `rdc repo create --name <repo> -m <machine>` | マシン上に新しいリポジトリを作成する |
| `rdc repo up --name <repo> -m <machine>` | リポジトリをデプロイまたは更新する |
| `rdc repo down --name <repo> -m <machine>` | リポジトリを停止する |
| `rdc repo delete --name <repo> -m <machine>` | リポジトリを削除する |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | リポジトリをフォークする (ほぼ瞬時、BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | 既存リポジトリの所有権を取得する |
| `rdc config repository list` | 名前と GUID を含む全リポジトリを一覧表示する |

## リポジトリごとのシークレット

デプロイ時のみに使用される書き込み専用の認証情報です。`get` はダイジェストのみを返します。値は決して返されません。完全なガイドは [リポジトリ § シークレット](/ja/docs/repositories#secrets) を参照してください。

| コマンド | 説明 |
|---------|------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | 新しいシークレットを作成する (`--current ""` で初回書き込み) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | 既存シークレットを上書きする (パスワードスタイルの事前条件) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | 事前値を検証せずに上書きする (ローテーションとして監査される) |
| `rdc repo secret list --name <repo>` | シークレット名と配信モードを一覧表示する (値とダイジェストは表示されない) |
| `rdc repo secret get --name <repo> --key <KEY>` | シークレットダイジェストとモードを表示する (プレーンテキスト値は表示されない) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | シークレットを削除する |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | 事前値を検証せずに削除する |

> フォークはシークレットを継承しません。フォーク上で `rdc repo secret set --name <repo>:<tag>` で明示的に設定してください。

## バックアップと復元

| コマンド | 説明 |
|---------|------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | リポジトリのバックアップをストレージにプッシュする |
| `rdc repo push --to <storage> -m <machine>` | 全リポジトリをストレージにプッシュする |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | ストレージからリポジトリを復元する |
| `rdc repo pull --from <storage> -m <machine>` | ストレージから全リポジトリを復元する |
| `rdc repo push ... --bwlimit <limit>` | プッシュ時の rsync 帯域幅を制限する (例: `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | プル時の rsync 帯域幅を制限する |
| `rdc repo push ... --checkpoint` | プッシュ前にコンテナのチェックポイントを作成する |
| `rdc repo backup list --from <storage> -m <machine>` | ストレージ内の利用可能なバックアップを一覧表示する |
| `rdc storage browse --name <storage>` | ストレージの内容を参照する |

## リポジトリの移行

| コマンド | 説明 |
|---------|------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | マシン間でリポジトリを移動する |
| `rdc repo migrate ... --provision` | 転送前に移行先をプロビジョニングする |
| `rdc repo migrate ... --checkpoint` | 移行前にチェックポイントを作成する |
| `rdc repo migrate ... --skip-dns` | 移行後の DNS 更新をスキップする |
| `rdc repo migrate ... --bwlimit <limit>` | 転送帯域幅を制限する |

## バックアップ戦略

| コマンド | 説明 |
|---------|------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | 名前付きバックアップ戦略を作成または更新する |
| `rdc config backup-strategy list` | 定義済みバックアップ戦略を全て一覧表示する |
| `rdc config backup-strategy show --name <name>` | 戦略の詳細を表示する |
| `rdc config backup-strategy remove --name <name>` | 戦略を削除する |
| `rdc machine backup schedule -m <machine>` | 設定済みバックアップ戦略をマシンにデプロイする |

## バックアップ操作

| コマンド | 説明 |
|---------|------|
| `rdc machine backup schedule -m <machine>` | 紐付けられた戦略を systemd タイマーとしてデプロイする |
| `rdc machine backup schedule -m <machine> --dry-run` | デプロイせずにタイマーユニットをプレビューする (トークンはマスク済み) |
| `rdc machine backup now -m <machine>` | 紐付けられた全戦略を即時実行する |
| `rdc machine backup now -m <machine> --strategy <name>` | 特定の戦略を即時実行する |
| `rdc machine backup status -m <machine>` | タイマーの状態と最近のジョブ結果を表示する |
| `rdc machine backup status -m <machine> --strategy <name>` | 特定の戦略の状態を表示する |
| `rdc machine backup cancel -m <machine>` | 実行中のバックアップをキャンセルする |
| `rdc machine backup cancel -m <machine> --strategy <name>` | 特定の実行中バックアップをキャンセルする |

## マシン管理

| コマンド | 説明 |
|---------|------|
| `rdc machine query --name <machine>` | マシンの完全なステータス (システム、コンテナ、サービス、リポジトリ、ネットワーク) |
| `rdc machine query --name <machine> --system` | システム情報のみ |
| `rdc machine query --name <machine> --containers` | コンテナ一覧のみ |
| `rdc machine query --name <machine> --repositories` | リポジトリ一覧のみ |
| `rdc machine query --name <machine> --services` | サービス一覧のみ |
| `rdc machine query --name <machine> --network` | ネットワーク情報のみ |
| `rdc machine query --name <machine> --block-devices` | ブロックデバイス情報のみ |
| `rdc machine list` | 設定内の全マシンを一覧表示する |
| `rdc config machine setup --name <machine>` | マシンの初期プロビジョニングを実行する |
| `rdc machine prune --name <machine>` | マシンから未使用リソースを削除する |
| `rdc machine deprovision --name <machine>` | マシンを完全にデプロビジョニングする |

## ターミナルと同期

| コマンド | 説明 |
|---------|------|
| `rdc term connect -m <machine>` | マシンへの SSH ターミナルを開く |
| `rdc term connect -m <machine> -r <repo>` | リポジトリへの SSH ターミナルを開く (DOCKER_HOST を設定) |
| `rdc term connect -m <machine> -c "<command>"` | マシン上でコマンドを実行する |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | 1 つ以上のローカルファイル/ディレクトリをリポジトリにアップロードする |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | 単一のローカルファイルを明示的なリモートパスにアップロードする |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | リポジトリディレクトリをローカルにダウンロードする |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | 単一のリモートファイルをローカルディレクトリにダウンロードする |
| `rdc vscode connect -m <machine> -r <repo>` | VS Code Remote SSH セッションを開く |

## 設定

| コマンド | 説明 |
|---------|------|
| `rdc config init --name <name>` | 名前付き設定ファイルを作成する |
| `rdc config machine add --name <machine> --host <host> --user <user>` | 設定にマシンを追加する |
| `rdc config storage import --file rclone.conf` | rclone 設定からストレージプロバイダをインポートする |
| `rdc config storage list` | 設定済みストレージプロバイダを一覧表示する |
| `rdc config backup-strategy set ...` | 名前付きバックアップ戦略を定義する |
| `rdc --config <name> <command>` | 名前付き設定ファイルを使用する |

## デバッグと直接アクセス

| コマンド | 説明 |
|---------|------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | リポジトリ内のコンテナを一覧表示する |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | コンテナのログを取得する |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | コンテナ内でコマンドを実行する |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | コンテナを再起動する |
