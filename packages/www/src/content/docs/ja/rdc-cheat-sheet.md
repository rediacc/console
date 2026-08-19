---
title: RDC CLI チートシート
description: "rdc コマンドのクイックリファレンス：設定、リポジトリ、マシン、同期、コンテナ。全オプション一覧は任意のコマンドに --help を付けて確認できます。"
category: Guides
tags:
  - cli
order: 3
cardGrid: true
language: ja
sourceHash: "14ed5791afa44326"
sourceCommit: "45cd71f8a80949d4cd621f233377c48715bbf531"
---

# RDC CLI チートシート

ここでは全ての `rdc` コマンドをリストしているのではなく、デプロイ時に頻繁に使用されるコマンドのみを掲載しています。全オプションを確認するには、任意のコマンドに `--help` を付けて実行してください。エッジケースと滅多に使わないオプションは、完全なリファレンスに記載されています。

## リポジトリのライフサイクル

| コマンド | 説明 |
|---------|------|
| `rdc repo create <repo> -m <machine>` | マシン上に新しいリポジトリを作成する |
| `rdc repo up <repo>@<machine>` | リポジトリをデプロイまたは更新する |
| `rdc repo down <repo>@<machine>` | リポジトリを停止する |
| `rdc repo delete <repo>@<machine>` | リポジトリを削除する |
| `rdc repo fork <repo>@<machine> --tag <tag>` | リポジトリをフォークする (ほぼ瞬時、BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | 検証済みのフォークを親リポジトリの名前で本番環境に昇格する |
| `rdc repo list` | 名前と GUID を含む全リポジトリを一覧表示する |
| `rdc repo resize <repo> --size <size>` | 停止中のリポジトリのボリュームサイズを変更する |
| `rdc repo expand <repo> --size <size>` | 稼働中のリポジトリのボリュームをその場で拡張する |

## リポジトリごとのシークレット

デプロイ時のみに使用される書き込み専用の認証情報です。`get` はダイジェストのみを返します。値は決して返されません。完全なガイドは [リポジトリ § シークレット](/ja/docs/repositories#secrets) を参照してください。

| コマンド | 説明 |
|---------|------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | 新しいシークレットを作成する (`--current ""` で初回書き込み) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | 既存シークレットを上書きする (パスワードスタイルの事前条件) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | 事前値を検証せずに上書きする (ローテーションとして監査される) |
| `rdc repo secret list <repo>` | シークレット名と配信モードを一覧表示する (値とダイジェストは表示されない) |
| `rdc repo secret get <repo> --key <KEY>` | シークレットダイジェストとモードを表示する (プレーンテキスト値は表示されない) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | シークレットを削除する |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | 事前値を検証せずに削除する |

> フォークはシークレットを継承しません。フォーク上で `rdc repo secret set <repo>:<tag>` で明示的に設定してください。

## バックアップと復元

| コマンド | 説明 |
|---------|------|
| `rdc repo push ... --bwlimit <limit>` | プッシュ時の rsync 帯域幅を制限する (例: `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | プル時の rsync 帯域幅を制限する |
| `rdc repo push ... --checkpoint` | プッシュ前にコンテナのチェックポイントを作成する |
| `rdc backup manifests <repo-ref>` | チャンクストレージが保持するスナップショットを一覧表示する |
| `rdc backup browse <repo-ref>` | リポジトリが含むファイルを一覧表示する (ローカル、読み取り専用) |
| `rdc backup snapshot <repo>` | チャンクストレージスナップショットをアップロードする: 最初は全インベントリ、以降は変更されたセルのみ |
| `rdc backup snapshot <repo> --dry-run` | アップロードせずにスナップショットを計画する; 何が移動するかを報告する |
| `rdc backup verify <repo>` | リポジトリのバックアップアンカーをチャンクストレージと照合して検証する |
| `rdc backup usage` | チャンクストレージに保存されたバイト数をクォータと比較して表示する |
| `rdc backup manifests <repo>` | サーバーに記録されたスナップショットマニフェストを一覧表示する |
| `rdc storage browse <storage>` | ストレージの内容を参照する |

## リポジトリの移行

| コマンド | 説明 |
|---------|------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | マシン間でリポジトリを移動する |
| `rdc repo migrate ... --provision` | 転送前に移行先をプロビジョニングする |
| `rdc repo migrate ... --checkpoint` | 移行前にチェックポイントを作成する |
| `rdc repo migrate ... --skip-dns` | 移行後の DNS 更新をスキップする |
| `rdc repo migrate ... --bwlimit <limit>` | 転送帯域幅を制限する |

## バックアップ戦略

| コマンド | 説明 |
|---------|------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | 名前付きバックアップ戦略を作成または更新する |
| `rdc backup strategy list` | 定義済みバックアップ戦略を全て一覧表示する |
| `rdc backup strategy show <name>` | 戦略の詳細を表示する |
| `rdc backup strategy remove <name>` | 戦略を削除する |
| `rdc backup schedule -m <machine>` | 設定済みバックアップ戦略をマシンにデプロイする |

## バックアップ操作

| コマンド | 説明 |
|---------|------|
| `rdc backup schedule -m <machine>` | 紐付けられた戦略を systemd タイマーとしてデプロイする |
| `rdc backup schedule -m <machine> --dry-run` | デプロイせずにタイマーユニットをプレビューする (トークンはマスク済み) |
| `rdc backup run -m <machine>` | 紐付けられた全戦略を即時実行する |
| `rdc backup run <name> -m <machine>` | 特定の戦略を即時実行する |
| `rdc backup status -m <machine>` | タイマーの状態と最近のジョブ結果を表示する |
| `rdc backup status <name> -m <machine>` | 特定の戦略の状態を表示する |
| `rdc backup cancel -m <machine>` | 実行中のバックアップをキャンセルする |
| `rdc backup cancel <name> -m <machine>` | 特定の実行中バックアップをキャンセルする |

## マシン管理

| コマンド | 説明 |
|---------|------|
| `rdc machine status <machine>` | マシンの完全なステータス (システム、コンテナ、サービス、リポジトリ、ネットワーク) |
| `rdc machine status <machine> --system` | システム情報のみ |
| `rdc machine status <machine> --containers` | コンテナ一覧のみ |
| `rdc machine status <machine> --repositories` | リポジトリ一覧のみ |
| `rdc machine status <machine> --services` | サービス一覧のみ |
| `rdc machine status <machine> --network` | ネットワーク情報のみ |
| `rdc machine status <machine> --block-devices` | ブロックデバイス情報のみ |
| `rdc machine list` | 設定内の全マシンを一覧表示する |
| `rdc machine setup <machine>` | マシンの初期プロビジョニングを実行する |
| `rdc machine health <machine>` | マシンのヘルスチェックを実行する |
| `rdc machine scan-keys <machine>` | 再構築後に SSH ホストキーを更新する |
| `rdc machine prune <machine>` | マシンから未使用リソースを削除する |
| `rdc machine deprovision <machine>` | マシンを完全にデプロビジョニングする |

## ターミナルと同期

| コマンド | 説明 |
|---------|------|
| `rdc term connect <machine>` | マシンへの SSH ターミナルを開く |
| `rdc term connect <repo>@<machine>` | リポジトリへの SSH ターミナルを開く (DOCKER_HOST を設定) |
| `rdc term connect <machine> -c "<command>"` | マシン上でコマンドを実行する |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | 1 つ以上のローカルファイル/ディレクトリをリポジトリにアップロードする |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | 単一のローカルファイルを明示的なリモートパスにアップロードする |
| `rdc repo sync download <repo>@<machine> --local <dir>` | リポジトリディレクトリをローカルにダウンロードする |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | 単一のリモートファイルをローカルディレクトリにダウンロードする |
| `rdc vscode connect <repo>@<machine>` | VS Code Remote SSH セッションを開く |
| `rdc vscode list` | `vscode connect` が作成した SSH 設定を一覧表示する |
| `rdc vscode cleanup --all` | `vscode connect` が書き込んだ SSH 設定をすべて削除する |
| `rdc repo tunnel <repo> -c <container> --port <port>` | コンテナのポートを SSH 経由で転送する |

## 設定

| コマンド | 説明 |
|---------|------|
| `rdc config init <name>` | 名前付き設定ファイルを作成する |
| `rdc config list` | このマシン上のすべての設定を一覧表示する |
| `rdc config set machine <alias>` | エイリアスを別のマシンに向ける |
| `rdc machine add <machine> --ip <host> --user <user>` | 設定にマシンを追加する |
| `rdc storage import rclone.conf` | rclone 設定からストレージプロバイダをインポートする |
| `rdc storage list` | 設定済みストレージプロバイダを一覧表示する |
| `rdc backup strategy set ...` | 名前付きバックアップ戦略を定義する |
| `rdc --config <name> <command>` | 名前付き設定ファイルを使用する |

## デバッグと直接アクセス

| コマンド | 説明 |
|---------|------|
| `rdc repo logs <repo>@<machine> -c <container> --lines 200 --follow` | コンテナのログをストリーミングする (推奨) |
| `rdc repo exec <repo>@<machine> -c <container> -- <command>` | コンテナ内でコマンドを実行する (推奨) |
| `rdc repo exec <repo>@<machine> -c <container> -i -- bash` | インタラクティブなコンテナシェルに接続する |
| `rdc term connect <repo>@<machine> -c "docker ps"` | リポジトリ内のコンテナを一覧表示する |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | コンテナのログを取得する |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | コンテナ内でコマンドを実行する |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | コンテナを再起動する |
