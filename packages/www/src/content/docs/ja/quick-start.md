---
title: クイックスタート
description: 5分でサーバー上にコンテナ化されたサービスを実行。
category: Guides
order: -1
language: ja
sourceHash: b368b94e7064efe1
---

# クイックスタート

5分で自分のサーバーに暗号化された隔離コンテナ環境をデプロイしましょう。クラウドアカウントやSaaS依存は不要です。

## 前提条件

- LinuxまたはmacOSのワークステーション
- リモートサーバー（Ubuntu 24.04+、Debian 12+、またはFedora 43+）、SSH接続とsudo権限が必要
- SSHキーペア（例: `~/.ssh/id_ed25519`）

## 1. CLIのインストール

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. Configの作成

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. サーバーの追加

```bash
rdc config add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. サーバーのプロビジョニング

```bash
rdc config setup-machine server-1
```

このコマンドはサーバーにDocker、cryptsetup、renetバイナリをインストールします。

## 5. 暗号化リポジトリの作成

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. サービスのデプロイ

リポジトリをマウントし、その中に`docker-compose.yml`と`Rediaccfile`を作成してから起動します:

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. 確認

```bash
rdc machine containers server-1
```

コンテナが実行中であることを確認できるはずです。

## Rediaccとは？

Rediaccは、お客様が管理するリモートサーバー上にコンテナ化されたサービスをデプロイします。すべてのデータはLUKSで保存時に暗号化され、各リポジトリは独自の隔離されたDockerデーモンを持ち、すべてのオーケストレーションはワークステーションからSSH経由で行われます。

クラウドアカウント不要。SaaS依存なし。データはお客様のサーバーに保存されます。

## 次のステップ

- **[アーキテクチャ](/ja/docs/architecture)** — Rediaccの仕組みを理解する: アダプター検出、セキュリティモデル、Docker隔離
- **[rdc vs renet](/ja/docs/rdc-vs-renet)** — 日常業務と低レベルのリモート作業でどちらのCLIを使うべきかを理解する
- **[マシンセットアップ](/ja/docs/setup)** — 詳細なセットアップガイド: 設定、マシン、インフラ構成
- **[リポジトリ](/ja/docs/repositories)** — リポジトリの作成、管理、リサイズ、フォーク、検証
- **[サービス](/ja/docs/services)** — Rediaccfile、サービスネットワーク、デプロイ、自動起動
- **[バックアップと復元](/ja/docs/backup-restore)** — 外部ストレージへのバックアップと自動バックアップのスケジュール設定
- **[モニタリング](/ja/docs/monitoring)** — マシンの健全性、コンテナ、サービス、診断
- **[ツール](/ja/docs/tools)** — ファイル同期、SSHターミナル、VS Code統合
- **[移行ガイド](/ja/docs/migration)** — 既存のプロジェクトをRediaccリポジトリに移行
- **[トラブルシューティング](/ja/docs/troubleshooting)** — よくある問題の解決策
- **[CLIリファレンス](/ja/docs/cli-application)** — 完全なコマンドリファレンス
