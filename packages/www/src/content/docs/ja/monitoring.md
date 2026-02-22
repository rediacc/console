---
title: モニタリング
description: マシンの健全性、コンテナ、サービス、リポジトリの監視と診断の実行。
category: Guides
order: 9
language: ja
sourceHash: 72f77c1ae5a0dbce
---

# モニタリング

Rediaccは、マシンの健全性、実行中のコンテナ、サービス、リポジトリの状態、システム診断を検査するための組み込みの監視コマンドを提供します。

## マシンの健全性

マシンの包括的なヘルスレポートを取得します：

```bash
rdc machine health server-1
```

レポート内容：
- **System**: アップタイム、メモリ使用量、ディスク使用量
- **Datastore**: 容量と使用量
- **コンテナ**: 実行中、正常、異常のコンテナ数
- **サービス**: ステータスと再起動回数
- **ストレージ**: SMARTヘルスと温度
- **リポジトリ**: マウント状態とDocker daemonの状態
- **問題点**: 検出された問題

マシン可読な出力には `--output json` を使用してください。

## コンテナの一覧表示

マシン上のすべてのリポジトリにわたる実行中のコンテナをすべて表示します：

```bash
rdc machine containers server-1
```

| カラム | 説明 |
|--------|------|
| Name | コンテナ名 |
| Status | 実行中、停止中など |
| Health | 正常、異常、なし |
| CPU | CPU使用率 |
| Memory | メモリ使用量 |
| Repository | コンテナが属するリポジトリ |

オプション：
- `--health-check` — コンテナに対してアクティブなヘルスチェックを実行
- `--output json` — マシン可読なJSON出力

## サービスの一覧表示

マシン上のRediaccに関連するsystemdサービスを表示します：

```bash
rdc machine services server-1
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
- `--stability-check` — 不安定なサービスをフラグ付け（失敗、3回以上の再起動、自動再起動）
- `--output json` — マシン可読なJSON出力

## リポジトリの一覧表示

マシン上のリポジトリを詳細な統計情報とともに表示します：

```bash
rdc machine repos server-1
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
- `--search <text>` — 名前またはマウントパスでフィルタリング
- `--output json` — マシン可読なJSON出力

## Vaultステータス

デプロイ情報を含むマシンの完全な概要を取得します：

```bash
rdc machine vault-status server-1
```

提供される情報：
- ホスト名とアップタイム
- メモリ、ディスク、Datastoreの使用量
- リポジトリの総数、マウント数、Docker実行数
- リポジトリごとの詳細情報

マシン可読な出力には `--output json` を使用してください。

## 接続テスト

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
- `--port <number>` — SSHポート（デフォルト: 22）
- `--save -m server-1` — 検証済みホスト鍵をマシン設定に保存

## 診断 (doctor)

Rediacc環境の包括的な診断チェックを実行します：

```bash
rdc doctor
```

| カテゴリ | チェック内容 |
|----------|-------------|
| **環境** | Node.jsバージョン、CLIバージョン、SEAモード、Goインストール、Dockerの利用可否 |
| **Renet** | バイナリの場所、バージョン、CRIU、rsync、SEA埋め込みアセット |
| **設定** | アクティブなコンテキスト、モード、マシン、SSH鍵 |
| **認証** | ログイン状態、ユーザーメールアドレス |
| **Virtualization** | Checks if your system can run local virtual machines (`rdc ops`) |

各チェックは **OK**、**警告**、または **エラー** を報告します。問題のトラブルシューティングの最初のステップとしてこれを使用してください。

終了コード: `0` = すべて合格、`1` = 警告あり、`2` = エラーあり。
