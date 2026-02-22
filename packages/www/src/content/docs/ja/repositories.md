---
title: リポジトリ
description: リモートマシン上のLUKS暗号化リポジトリの作成、管理、操作。
category: Guides
order: 4
language: ja
sourceHash: 04fe287348176b64
---

# リポジトリ

**リポジトリ**は、リモートサーバー上のLUKS暗号化ディスクイメージです。マウントすると以下が提供されます：
- アプリケーションデータ用の隔離されたファイルシステム
- 専用のDockerデーモン（ホストのDockerとは別）
- /26サブネット内の各サービスに対する一意のループバックIP

## リポジトリの作成

```bash
rdc repo create my-app -m server-1 --size 10G
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `-m, --machine <name>` | はい | リポジトリが作成されるターゲットマシン |
| `--size <size>` | はい | 暗号化ディスクイメージのサイズ（例：`5G`、`10G`、`50G`） |
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

出力には3つの自動生成された値が表示されます：

- **リポジトリGUID** -- サーバー上の暗号化ディスクイメージを識別するUUID。
- **クレデンシャル** -- LUKSボリュームの暗号化/復号化に使用されるランダムなパスフレーズ。
- **ネットワークID** -- このリポジトリのサービスのIPサブネットを決定する整数（2816から始まり、64ずつ増加）。

> **クレデンシャルは安全に保管してください。** これはリポジトリの暗号化鍵です。紛失した場合、データは復元できません。クレデンシャルはローカルの`config.json`に保存されますが、サーバーには保存されません。

## マウントとアンマウント

マウントはリポジトリファイルシステムを復号化してアクセス可能にします。アンマウントは暗号化ボリュームをクローズします。

```bash
rdc repo mount my-app -m server-1       # 復号化してマウント
rdc repo unmount my-app -m server-1     # アンマウントして再暗号化
```

| オプション | 説明 |
|--------|-------------|
| `--checkpoint` | マウント/アンマウント前にチェックポイントを作成 |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## ステータスの確認

```bash
rdc repo status my-app -m server-1
```

## リポジトリの一覧表示

```bash
rdc repo list -m server-1
```

## リサイズ

リポジトリを正確なサイズに設定するか、指定した量だけ拡張します：

```bash
rdc repo resize my-app -m server-1 --size 20G    # 正確なサイズに設定
rdc repo expand my-app -m server-1 --size 5G      # 現在のサイズに5Gを追加
```

> リサイズの前にリポジトリをアンマウントする必要があります。

## フォーク

既存のリポジトリの現在の状態のコピーを作成します：

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

これにより、独自のGUIDとネットワークIDを持つ新しい暗号化コピーが作成されます。フォークは親と同じLUKSクレデンシャルを共有します。

## 検証

リポジトリのファイルシステム整合性を確認します：

```bash
rdc repo validate my-app -m server-1
```

## 所有権

リポジトリ内のファイル所有権をユニバーサルユーザー（UID 7111）に設定します。通常、ワークステーションからアップロードされたファイルがローカルのUIDで到着した後に必要です。

```bash
rdc repo ownership my-app -m server-1
```

このコマンドはDockerコンテナのデータディレクトリ（書き込み可能なバインドマウント）を自動的に検出し、除外します。これにより、独自のUIDでファイルを管理するコンテナ（例：MariaDB=999、www-data=33）が壊れることを防ぎます。

| オプション | 説明 |
|--------|-------------|
| `--uid <uid>` | 7111の代わりにカスタムUIDを設定 |
| `--force` | Dockerボリューム検出をスキップしてすべてをchown |
| `--skip-router-restart` | Skip restarting the route server after the operation |

すべてのファイル（コンテナデータを含む）に所有権を強制するには：

```bash
rdc repo ownership my-app -m server-1 --force
```

> **警告：** 実行中のコンテナに`--force`を使用すると壊れる可能性があります。必要に応じて先に`rdc repo down`でサービスを停止してください。

所有権の使用方法の詳細なウォークスルーについては、[移行ガイド](/ja/docs/migration)を参照してください。

## テンプレート

テンプレートを適用してリポジトリをファイルで初期化します：

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## 削除

リポジトリとその中のすべてのデータを永久に破壊します：

```bash
rdc repo delete my-app -m server-1
```

> これにより、暗号化ディスクイメージが永久に破壊されます。この操作は取り消せません。
